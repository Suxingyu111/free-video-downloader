from __future__ import annotations

import secrets
import threading
from pathlib import Path


class CookieStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._refs: dict[str, Path] = {}
        self._lock = threading.Lock()

    def save(self, contents: bytes) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        ref = secrets.token_urlsafe(18)
        path = self.root / f"{ref}.txt"
        path.write_bytes(contents)
        with self._lock:
            self._refs[ref] = path
        return ref

    def pop(self, ref: str | None) -> Path | None:
        if not ref:
            return None
        with self._lock:
            return self._refs.pop(ref, None)

