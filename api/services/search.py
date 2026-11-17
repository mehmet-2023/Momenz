from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

from core.pipeline import search_embeddings

from ..config import Settings
from ..db import D1Client
from ..repositories import folders as folder_repo
from ..repositories import index as index_repo


@dataclass(slots=True)
class _Entry:
    version: int
    matrix: np.ndarray
    metas: list[dict]
    last_used: float


class SearchService:
    """Klasör başına sıcak matris cache'i.

    D1 her zaman source of truth'tur. Worker indexlemeyi bitirdiğinde
    ``folder_index_versions`` artar; cache bunu tek bir D1 sorgusuyla kontrol
    eder ve gerekirse matrisi yeniden kurar. Böylece her aramada tüm
    embedding'leri D1'den çekmeyiz.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._entries: dict[str, _Entry] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, folder_key: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(folder_key)
            if lock is None:
                lock = threading.Lock()
                self._locks[folder_key] = lock
            return lock

    def _evict_if_needed(self) -> None:
        max_entries = max(1, self.settings.search_cache_max_folders)
        if len(self._entries) <= max_entries:
            return
        overflow = len(self._entries) - max_entries
        oldest = sorted(self._entries.items(), key=lambda kv: kv[1].last_used)[:overflow]
        for key, _ in oldest:
            self._entries.pop(key, None)
            self._locks.pop(key, None)

    def invalidate(self, folder_key: str) -> None:
        with self._guard:
            self._entries.pop(folder_key, None)
            self._locks.pop(folder_key, None)

    def _get_matrix(self, db: D1Client, folder_key: str) -> tuple[np.ndarray, list[dict]]:
        version = folder_repo.get_version(db, folder_key)
        entry = self._entries.get(folder_key)
        if entry is not None and entry.version == version:
            entry.last_used = time.monotonic()
            return entry.matrix, entry.metas

        with self._lock_for(folder_key):
            version = folder_repo.get_version(db, folder_key)
            entry = self._entries.get(folder_key)
            if entry is not None and entry.version == version:
                entry.last_used = time.monotonic()
                return entry.matrix, entry.metas
            matrix, metas = index_repo.fetch_matrix(db, folder_key)
            self._entries[folder_key] = _Entry(
                version=version,
                matrix=matrix,
                metas=metas,
                last_used=time.monotonic(),
            )
            self._evict_if_needed()
            return matrix, metas

    def search(
        self,
        db: D1Client,
        folder_key: str,
        probe: np.ndarray,
        *,
        threshold: float | None = None,
        max_results: int | None = None,
    ) -> tuple[list[dict], float]:
        started = time.perf_counter()
        matrix, metas = self._get_matrix(db, folder_key)
        if matrix.size == 0:
            return [], 0.0
        results = search_embeddings(
            matrix,
            metas,
            [probe],
            threshold=(
                self.settings.search_default_threshold if threshold is None else threshold
            ),
            max_results=max_results or self.settings.search_max_results,
        )
        return results, (time.perf_counter() - started) * 1000.0
