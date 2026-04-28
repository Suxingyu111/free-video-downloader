from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Literal


TaskStatus = Literal["queued", "downloading", "processing", "completed", "failed"]


@dataclass
class TaskSnapshot:
    id: str
    url: str
    status: TaskStatus = "queued"
    progress: float = 0.0
    message: str = "Queued"
    speed: float | None = None
    eta: float | None = None
    download_url: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "speed": self.speed,
            "eta": self.eta,
            "download_url": self.download_url,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskSnapshot] = {}
        self._files: dict[str, Path] = {}
        self._lock = threading.Lock()

    def create_task(self, url: str) -> TaskSnapshot:
        task = TaskSnapshot(id=f"task_{secrets.token_urlsafe(10)}", url=url)
        with self._lock:
            self._tasks[task.id] = task
        return task

    def update_task(self, task_id: str, **changes: object) -> TaskSnapshot | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            for key, value in changes.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            task.updated_at = time()
            return task

    def get_task(self, task_id: str) -> TaskSnapshot | None:
        with self._lock:
            return self._tasks.get(task_id)

    def active_task_ids(self) -> set[str]:
        with self._lock:
            return {
                task_id
                for task_id, task in self._tasks.items()
                if task.status in {"queued", "downloading", "processing"}
            }

    def register_file(self, path: Path) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._files[token] = path
        return token

    def resolve_file(self, token: str) -> Path | None:
        with self._lock:
            return self._files.get(token)


task_store = TaskStore()
