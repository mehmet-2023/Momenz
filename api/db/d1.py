from __future__ import annotations

import random
import re
import threading
import time
from typing import Any, Iterable

import requests


class D1Error(Exception):
    """Cloudflare D1 REST katmanı hatası."""


class D1Client:
    """D1 REST API için genel, bağımlılıksız istemci.

    ``core.d1_store.D1Store`` ile aynı taşıma kurallarını kullanır ama tablo
    şemasına bağlı değildir; API repository'leri ham SQL için bunu kullanır.
    """

    _MAX_BOUND_PARAMS = 100

    def __init__(
        self,
        account_id: str,
        database_id: str,
        api_token: str,
        *,
        timeout: tuple[float, float] = (10.0, 90.0),
        max_retries: int = 4,
    ) -> None:
        if not (account_id and database_id and api_token):
            raise D1Error("D1 ayarları eksik (account_id, database_id, api_token).")
        self._api_token = api_token
        self._url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{account_id}/d1/database/{database_id}/query"
        )
        self._timeout = timeout
        self._max_retries = max(0, int(max_retries))
        self._local = threading.local()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "Authorization": f"Bearer {self._api_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
            )
            self._local.session = session
        return session

    def _post(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            retryable = False
            try:
                response = self._session().post(self._url, json=payload, timeout=self._timeout)
            except requests.RequestException as exc:
                last_error = exc
                retryable = True
            else:
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = D1Error(f"D1 HTTP {response.status_code}")
                    retryable = True
                else:
                    try:
                        body = response.json()
                    except ValueError as exc:
                        raise D1Error("D1 geçersiz JSON döndürdü.") from exc
                    if body.get("success") is not True:
                        errors = body.get("errors") or []
                        detail = "; ".join(
                            str(item.get("message") or item)
                            if isinstance(item, dict)
                            else str(item)
                            for item in errors
                        )
                        raise D1Error(detail or "D1 isteği başarısız.")
                    return list(body.get("result") or [])
            if not retryable or attempt >= self._max_retries:
                break
            delay = min(8.0, 0.5 * (2**attempt)) + random.random() * 0.25
            time.sleep(delay)
        if isinstance(last_error, D1Error):
            raise last_error
        raise D1Error(str(last_error) or "D1 isteği başarısız.")

    @staticmethod
    def _safe_params(params: Iterable[Any] | None) -> list[Any]:
        values = list(params or [])
        if len(values) > D1Client._MAX_BOUND_PARAMS:
            raise D1Error("D1 sorgu başına en fazla 100 bound parameter destekler.")
        return values

    def query(self, sql: str, params: Iterable[Any] | None = None) -> list[dict]:
        payload: dict[str, Any] = {"sql": sql.strip()}
        values = self._safe_params(params)
        if values:
            payload["params"] = values
        result = self._post(payload)
        if not result:
            return []
        first = result[0]
        if not first.get("success", True):
            raise D1Error(str(first.get("error") or "D1 sorgusu başarısız."))
        return list(first.get("results") or [])

    def query_one(self, sql: str, params: Iterable[Any] | None = None) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> int:
        """Yazma sorgusu; etkilenen satır sayısını döndürür."""
        payload: dict[str, Any] = {"sql": sql.strip()}
        values = self._safe_params(params)
        if values:
            payload["params"] = values
        result = self._post(payload)
        first = result[0] if result else {}
        if not first.get("success", True):
            raise D1Error(str(first.get("error") or "D1 yazma sorgusu başarısız."))
        meta = first.get("meta") or {}
        if isinstance(meta, dict) and meta.get("changes") is not None:
            return int(meta["changes"])
        return 0

    def batch(self, statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not statements:
            return []
        output: list[dict[str, Any]] = []
        for start in range(0, len(statements), 50):
            chunk = statements[start : start + 50]
            result = self._post({"batch": chunk})
            for item in result:
                if not item.get("success", True):
                    raise D1Error(str(item.get("error") or "D1 batch başarısız."))
            output.extend(result)
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
    values = D1Client._safe_params(params)
    item: dict[str, Any] = {"sql": sql.strip()}
    if values:
        item["params"] = values
    return item
