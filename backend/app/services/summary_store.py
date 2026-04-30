from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Literal


SummaryStatus = Literal["queued", "transcribing", "summarizing", "completed", "failed"]
SummaryStage = Literal["queued", "subtitle", "speech_to_text", "summary", "completed", "failed"]


@dataclass
class SummarySnapshot:
    id: str
    url: str
    title: str | None = None
    status: SummaryStatus = "queued"
    stage: SummaryStage = "queued"
    progress: float = 0.0
    message: str = "Queued"
    result: dict | None = None
    streamed_text: str = ""
    markdown_url: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "streamed_text": self.streamed_text,
            "markdown_url": self.markdown_url,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SummaryStore:
    def __init__(self) -> None:
        self._tasks: dict[str, SummarySnapshot] = {}
        self._markdown_files: dict[str, Path] = {}
        self._lock = threading.Lock()

    def create_task(self, url: str, *, title: str | None = None) -> SummarySnapshot:
        task = SummarySnapshot(id=f"summary_{secrets.token_urlsafe(10)}", url=url, title=title)
        with self._lock:
            self._tasks[task.id] = task
        return task

    def update_task(self, task_id: str, **changes: object) -> SummarySnapshot | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            for key, value in changes.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            task.updated_at = time()
            return task

    def complete_task(self, task_id: str, *, result: dict, markdown_path: Path) -> SummarySnapshot | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task.status = "completed"
            task.stage = "completed"
            task.progress = 100.0
            task.message = "Summary complete"
            task.result = result
            task.markdown_url = f"/api/summaries/{task_id}/markdown"
            task.error = None
            task.updated_at = time()
            self._markdown_files[task_id] = markdown_path
            return task

    def fail_task(self, task_id: str, error: str) -> SummarySnapshot | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task.status = "failed"
            task.stage = "failed"
            task.progress = 0.0
            task.message = "Summary failed"
            task.error = error
            task.updated_at = time()
            return task

    def get_task(self, task_id: str) -> SummarySnapshot | None:
        with self._lock:
            return self._tasks.get(task_id)

    def resolve_markdown(self, task_id: str) -> Path | None:
        with self._lock:
            return self._markdown_files.get(task_id)

    def active_task_ids(self) -> set[str]:
        with self._lock:
            return {
                task_id
                for task_id, task in self._tasks.items()
                if task.status in {"queued", "transcribing", "summarizing"}
            }


summary_store = SummaryStore()
