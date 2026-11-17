from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any


def sql_now() -> str:
    """D1/SQLite `datetime('now')` ile string karşılaştırılabilir UTC zaman."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def sql_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))


def loads(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default
