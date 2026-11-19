from __future__ import annotations

import base64
import random
import re
import threading
import time
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

import requests


class TursoError(Exception):
    """Turso/libSQL HTTP katmanı hatası."""


_HOST_RE = re.compile(r"^(?:libsql|https?)://", re.IGNORECASE)


def _pipeline_url(database_url: str) -> str:
    value = str(database_url or "").strip()
    if not value:
        raise TursoError("Turso database URL boş.")
    if _HOST_RE.match(value):
        parts = urlsplit(value)
        scheme = "https" if parts.scheme.lower() == "libsql" else parts.scheme.lower()
        return urlunsplit((scheme, parts.netloc, "/v2/pipeline", "", ""))
    return f"https://{value}/v2/pipeline"


def _pad_base64(value: str) -> str:
    return value + "=" * (-len(value) % 4)


class TursoClient:
    """D1Client arayüzünü Turso SQL-over-HTTP ile gerçekleştirir.

    Her çağrı tek HTTP isteğidir ve stream açıkça kapatılır. Böylece uzun
    süreli Hrana transaction'larının idle timeout sorunu oluşmaz; ``batch``
    birden fazla ifadeyi tek istekte, tek transaction'da çalıştırır.
    """

    def __init__(
        self,
        database_url: str,
        auth_token: str,
        *,
        timeout: tuple[float, float] | None = None,
        max_retries: int = 4,
    ) -> None:
        token = str(auth_token or "").strip()
        if not token:
            raise TursoError("Turso auth token boş.")
        self._url = _pipeline_url(database_url)
        self._token = token
        self._timeout = float(timeout[1]) if timeout else 300.0
        self._max_retries = max(0, int(max_retries))
        self._local = threading.local()


    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
            )
            self._local.session = session
        return session

    @staticmethod
    def _encode_arg(value: Any) -> dict[str, Any]:
        if value is None:
            return {"type": "null"}
        if isinstance(value, bool):
            return {"type": "integer", "value": "1" if value else "0"}
        if isinstance(value, int):
            return {"type": "integer", "value": str(value)}
        if isinstance(value, float):
            return {"type": "float", "value": value}
        if isinstance(value, (bytes, bytearray, memoryview)):
            raw = bytes(value)
            return {
                "type": "blob",
                "base64": base64.b64encode(raw).decode("ascii"),
            }
        return {"type": "text", "value": str(value)}

    @staticmethod
    def _decode_value(item: dict[str, Any]) -> Any:
        kind = str(item.get("type") or "null")
        if kind == "integer":
            return int(item.get("value") or 0)
        if kind == "float":
            return float(item.get("value") or 0.0)
        if kind == "text":
            return item.get("value")
        if kind == "blob":
            encoded = str(item.get("base64") or "")
            if not encoded:
                return b""
            return base64.b64decode(_pad_base64(encoded))
        return None

    @classmethod
    def _rows(cls, result: dict[str, Any]) -> list[dict[str, Any]]:
        columns = [str(col.get("name") or "") for col in result.get("cols") or []]
        if not columns:
            return []
        return [
            {
                column: cls._decode_value(value)
                for column, value in zip(columns, row)
            }
            for row in result.get("rows") or []
        ]

    def _post(self, requests_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload = {
            "baton": None,
            "requests": [*requests_list, {"type": "close"}],
        }
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            retryable = False
            try:
                response = self._session().post(
                    self._url, json=payload, timeout=self._timeout
                )
            except requests.RequestException as exc:
                last_error = exc
                retryable = True
            else:
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = TursoError(f"Turso HTTP {response.status_code}")
                    retryable = True
                else:
                    try:
                        body = response.json()
                    except ValueError as exc:
                        raise TursoError("Turso geçersiz JSON döndürdü.") from exc
                    if not isinstance(body, dict):
                        raise TursoError("Turso beklenmedik yanıt döndürdü.")
                    if body.get("error"):
                        raise TursoError(str(body["error"]))
                    results = list(body.get("results") or [])
                    for item in results:
                        if item.get("type") == "error":
                            error = item.get("error") or {}
                            raise TursoError(
                                str(error.get("message") or error or "Turso isteği başarısız.")
                            )
                    return results
            if not retryable or attempt >= self._max_retries:
                break
            delay = min(8.0, 0.5 * (2**attempt)) + random.random() * 0.25
            time.sleep(delay)
        raise TursoError(str(last_error) or "Turso isteği başarısız.") from last_error


    def query(self, sql: str, params: Iterable[Any] | None = None) -> list[dict]:
        stmt: dict[str, Any] = {"sql": sql.strip()}
        values = list(params or [])
        if values:
            stmt["args"] = [self._encode_arg(value) for value in values]
        results = self._post([{"type": "execute", "stmt": stmt}])
        if not results:
            return []
        result = results[0].get("response", {}).get("result") or {}
        return self._rows(result)

    def query_one(self, sql: str, params: Iterable[Any] | None = None) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> int:
        stmt: dict[str, Any] = {"sql": sql.strip()}
        values = list(params or [])
        if values:
            stmt["args"] = [self._encode_arg(value) for value in values]
        results = self._post([{"type": "execute", "stmt": stmt}])
        if not results:
            return 0
        result = results[0].get("response", {}).get("result") or {}
        return int(result.get("affected_row_count") or 0)

    def batch(self, statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not statements:
            return []
        steps: list[dict[str, Any]] = []
        for item in statements:
            stmt: dict[str, Any] = {"sql": str(item.get("sql") or "").strip()}
            values = list(item.get("params") or [])
            if values:
                stmt["args"] = [self._encode_arg(value) for value in values]
            steps.append({"type": "execute", "stmt": stmt})
        results = self._post([{"type": "batch", "batch": {"steps": steps}}])
        if not results:
            return []
        batch = results[0].get("response", {}).get("result") or {}
        errors = [error for error in batch.get("step_errors") or [] if error]
        if errors:
            raise TursoError(str(errors[0].get("message") or errors[0]))
        output: list[dict[str, Any]] = []
        for result in batch.get("step_results") or []:
            output.append(
                {
                    "success": True,
                    "results": self._rows(result),
                    "meta": {
                        "changes": int(result.get("affected_row_count") or 0)
                    },
                }
            )
        return output

    def ping(self) -> bool:
        row = self.query_one("SELECT 1 AS ok")
        return bool(row and int(row.get("ok") or 0) == 1)

    def close(self) -> None:
        session = getattr(self._local, "session", None)
        if session is not None:
            session.close()
            self._local.session = None


def _statement(sql: str, params: Iterable[Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"sql": sql.strip()}
    values = list(params or [])
    if values:
        item["params"] = values
    return item


D1Client = TursoClient
D1Error = TursoError

__all__ = [
    "TursoClient",
    "TursoError",
    "D1Client",
    "D1Error",
]
