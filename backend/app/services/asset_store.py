from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteAsset:
    url: str
    referer: str | None = None


class AssetStore:
    def __init__(self) -> None:
        self._assets: dict[str, RemoteAsset] = {}
        self._lock = threading.Lock()

    def register(self, url: str, referer: str | None = None) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._assets[token] = RemoteAsset(url=url, referer=referer)
        return token

    def resolve(self, token: str) -> RemoteAsset | None:
        with self._lock:
            return self._assets.get(token)


asset_store = AssetStore()
