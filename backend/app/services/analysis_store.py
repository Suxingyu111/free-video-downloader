from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from time import time


ANALYSIS_TOKEN_TTL_SECONDS = 30 * 60


@dataclass
class AnalysisSnapshot:
    token: str
    url: str
    result: dict
    created_at: float


class AnalysisStore:
    def __init__(self) -> None:
        self._items: dict[str, AnalysisSnapshot] = {}
        self._lock = threading.Lock()

    def create(self, url: str, result: dict) -> str:
        token = f"analysis_{secrets.token_urlsafe(18)}"
        now = time()
        with self._lock:
            self._prune_locked(now)
            self._items[token] = AnalysisSnapshot(token=token, url=url, result=dict(result), created_at=now)
        return token

    def get(self, token: str | None) -> AnalysisSnapshot | None:
        if not token:
            return None
        now = time()
        with self._lock:
            self._prune_locked(now)
            return self._items.get(token)

    def find_by_url(self, url: str | None) -> AnalysisSnapshot | None:
        if not url:
            return None
        now = time()
        with self._lock:
            self._prune_locked(now)
            for item in reversed(list(self._items.values())):
                if item.url == url or item.result.get("webpage_url") == url:
                    return item
        return None

    def _prune_locked(self, now: float) -> None:
        expired = [token for token, item in self._items.items() if now - item.created_at > ANALYSIS_TOKEN_TTL_SECONDS]
        for token in expired:
            self._items.pop(token, None)


analysis_store = AnalysisStore()
