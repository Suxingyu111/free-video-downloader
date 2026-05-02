from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Literal
from urllib.parse import parse_qs, urlparse


SummaryStatus = Literal["queued", "transcribing", "summarizing", "completed", "failed"]
SummaryStage = Literal["queued", "subtitle", "speech_to_text", "summary", "completed", "failed"]
SUMMARY_PROMPT_VERSION = "2026-04-29-ai-video-summary-v1"
ACTIVE_SUMMARY_STATUSES = {"queued", "transcribing", "summarizing"}


def default_summary_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "runtime" / "summaries"


def normalize_summary_url(url: str) -> str:
    raw_url = str(url or "").strip()
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    host = parsed.netloc.lower()
    path = parsed.path or ""

    bilibili_match = re.search(r"/video/(?P<bvid>BV[0-9A-Za-z]+)/?", path, flags=re.IGNORECASE)
    if "bilibili.com" in host and bilibili_match:
        return f"https://www.bilibili.com/video/{bilibili_match.group('bvid')}/"

    if host in {"youtu.be", "www.youtu.be"}:
        video_id = path.strip("/").split("/", 1)[0]
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"

    if host.endswith("youtube.com"):
        video_id = parse_qs(parsed.query).get("v", [""])[0].strip()
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"

    return raw_url


def build_summary_cache_key(url: str, *, language: str = "zh-CN", prompt_version: str = SUMMARY_PROMPT_VERSION) -> str:
    payload = {
        "url": normalize_summary_url(url),
        "language": language or "zh-CN",
        "prompt_version": prompt_version,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class SummarySnapshot:
    id: str
    url: str
    title: str | None = None
    language: str = "zh-CN"
    cache_key: str | None = None
    status: SummaryStatus = "queued"
    stage: SummaryStage = "queued"
    progress: float = 0.0
    message: str = "Queued"
    result: dict | None = None
    draft_result: dict | None = None
    streamed_text: str = ""
    markdown_url: str | None = None
    error: str | None = None
    owner_user_id: str | None = None
    quota_user_id: str | None = None
    quota_refunded_at: float | None = None
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "language": self.language,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "draft_result": self.draft_result,
            "streamed_text": self.streamed_text,
            "markdown_url": self.markdown_url,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SummarySnapshot":
        return cls(
            id=str(data.get("id") or ""),
            url=str(data.get("url") or ""),
            title=data.get("title") if isinstance(data.get("title"), str) else None,
            language=str(data.get("language") or "zh-CN"),
            cache_key=data.get("cache_key") if isinstance(data.get("cache_key"), str) else None,
            status=data.get("status") if data.get("status") in {"queued", "transcribing", "summarizing", "completed", "failed"} else "queued",
            stage=data.get("stage") if data.get("stage") in {"queued", "subtitle", "speech_to_text", "summary", "completed", "failed"} else "queued",
            progress=float(data.get("progress") or 0.0),
            message=str(data.get("message") or "Queued"),
            result=data.get("result") if isinstance(data.get("result"), dict) else None,
            draft_result=data.get("draft_result") if isinstance(data.get("draft_result"), dict) else None,
            streamed_text=str(data.get("streamed_text") or ""),
            markdown_url=data.get("markdown_url") if isinstance(data.get("markdown_url"), str) else None,
            error=data.get("error") if isinstance(data.get("error"), str) else None,
            owner_user_id=data.get("owner_user_id") if isinstance(data.get("owner_user_id"), str) else None,
            quota_user_id=data.get("quota_user_id") if isinstance(data.get("quota_user_id"), str) else None,
            quota_refunded_at=float(data["quota_refunded_at"]) if data.get("quota_refunded_at") is not None else None,
            created_at=float(data.get("created_at") or time()),
            updated_at=float(data.get("updated_at") or time()),
        )


class SummaryStore:
    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else default_summary_dir()
        self._index_file = self.base_dir / "index.json"
        self._tasks: dict[str, SummarySnapshot] = {}
        self._markdown_files: dict[str, Path] = {}
        self._cache_index: dict[str, str] = {}
        self._lock = threading.Lock()
        self._load_from_disk()

    def create_task(
        self,
        url: str,
        *,
        title: str | None = None,
        language: str = "zh-CN",
        cache_key: str | None = None,
        owner_user_id: str | None = None,
        quota_user_id: str | None = None,
        task_id: str | None = None,
    ) -> SummarySnapshot:
        task = SummarySnapshot(
            id=task_id or f"summary_{secrets.token_urlsafe(10)}",
            url=url,
            title=title,
            language=language or "zh-CN",
            cache_key=cache_key or build_summary_cache_key(url, language=language),
            owner_user_id=owner_user_id,
            quota_user_id=quota_user_id,
        )
        with self._lock:
            self._tasks[task.id] = task
            self._cache_index[task.cache_key] = task.id
            self._save_task_locked(task)
            self._save_index_locked()
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
            self._save_task_locked(task)
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
            self._save_task_locked(task, markdown_path=markdown_path)
            self._save_index_locked()
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
            self._save_task_locked(task)
            self._save_index_locked()
            return task

    def get_task(self, task_id: str) -> SummarySnapshot | None:
        with self._lock:
            return self._tasks.get(task_id)

    def get_cached_task(
        self,
        url: str,
        *,
        language: str = "zh-CN",
        owner_user_id: str | None = None,
    ) -> SummarySnapshot | None:
        cache_key = build_summary_cache_key(url, language=language)
        with self._lock:
            if owner_user_id is not None:
                owned_tasks = [
                    task
                    for task in self._tasks.values()
                    if (
                        task.cache_key == cache_key
                        and task.status == "completed"
                        and task.owner_user_id == owner_user_id
                    )
                ]
                if owned_tasks:
                    return max(owned_tasks, key=lambda task: task.updated_at)
            task_id = self._cache_index.get(cache_key)
            if not task_id:
                return None
            task = self._tasks.get(task_id)
            if task is None or task.status != "completed":
                return None
            return task

    def clone_completed_task_for_owner(
        self,
        source_task_id: str,
        owner_user_id: str,
        *,
        task_id: str | None = None,
    ) -> SummarySnapshot | None:
        with self._lock:
            source = self._tasks.get(source_task_id)
            if source is None or source.status != "completed":
                return None
            clone_id = task_id or f"summary_{secrets.token_urlsafe(10)}"
            cloned = SummarySnapshot(
                id=clone_id,
                url=source.url,
                title=source.title,
                language=source.language,
                cache_key=source.cache_key,
                status="completed",
                stage="completed",
                progress=100.0,
                message=source.message,
                result=source.result,
                draft_result=source.draft_result,
                streamed_text=source.streamed_text,
                markdown_url=f"/api/summaries/{clone_id}/markdown",
                error=None,
                owner_user_id=owner_user_id,
            )
            markdown_path = self._markdown_files.get(source_task_id)
            self._tasks[cloned.id] = cloned
            if markdown_path is not None:
                self._markdown_files[cloned.id] = markdown_path
            self._save_task_locked(cloned, markdown_path=markdown_path)
            self._save_index_locked()
            return cloned

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

    def pending_quota_refunds(self) -> list[SummarySnapshot]:
        with self._lock:
            return [
                task
                for task in self._tasks.values()
                if task.status == "failed" and task.quota_user_id and task.quota_refunded_at is None
            ]

    def mark_quota_refunded(self, task_id: str) -> SummarySnapshot | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.quota_refunded_at is not None:
                return task
            task.quota_refunded_at = time()
            task.updated_at = time()
            self._save_task_locked(task)
            return task

    def _task_dir(self, task_id: str) -> Path:
        return self.base_dir / task_id

    def _snapshot_file(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "snapshot.json"

    def _load_from_disk(self) -> None:
        if not self.base_dir.exists():
            return

        self._cache_index = self._load_json_file(self._index_file) or {}
        for snapshot_file in sorted(self.base_dir.glob("summary_*/snapshot.json")):
            record = self._load_json_file(snapshot_file)
            if not isinstance(record, dict):
                continue
            task = SummarySnapshot.from_dict(record)
            if not task.id:
                continue
            markdown_path = self._resolve_record_markdown_path(task.id, record)
            if markdown_path:
                self._markdown_files[task.id] = markdown_path
            if task.status in ACTIVE_SUMMARY_STATUSES:
                task.status = "failed"
                task.stage = "failed"
                task.progress = 0.0
                task.message = "Summary failed"
                task.error = "后端服务重启后，未完成的 AI 总结任务已中断，请重新总结。"
                task.updated_at = time()
                self._save_task_unlocked(task, markdown_path=markdown_path)
            self._tasks[task.id] = task
            if task.cache_key:
                self._cache_index.setdefault(task.cache_key, task.id)
        self._save_index_unlocked()

    def _save_task_locked(self, task: SummarySnapshot, *, markdown_path: Path | None = None) -> None:
        self._save_task_unlocked(task, markdown_path=markdown_path or self._markdown_files.get(task.id))

    def _save_task_unlocked(self, task: SummarySnapshot, *, markdown_path: Path | None = None) -> None:
        task_dir = self._task_dir(task.id)
        task_dir.mkdir(parents=True, exist_ok=True)
        record = {
            **task.as_dict(),
            "cache_key": task.cache_key,
            "prompt_version": SUMMARY_PROMPT_VERSION,
            "owner_user_id": task.owner_user_id,
            "quota_refunded_at": task.quota_refunded_at,
            "quota_user_id": task.quota_user_id,
        }
        if markdown_path is not None:
            record["markdown_path"] = self._serialize_markdown_path(task.id, markdown_path)
        self._write_json(self._snapshot_file(task.id), record)

    def _save_index_locked(self) -> None:
        self._save_index_unlocked()

    def _save_index_unlocked(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        live_index: dict[str, str] = {}
        for task in self._tasks.values():
            if not task.cache_key or task.status == "failed":
                continue
            current_id = live_index.get(task.cache_key)
            current = self._tasks.get(current_id) if current_id else None
            if current is None or _cache_index_sort_key(task) >= _cache_index_sort_key(current):
                live_index[task.cache_key] = task.id
        self._cache_index = live_index
        self._write_json(self._index_file, live_index)

    def _resolve_record_markdown_path(self, task_id: str, record: dict) -> Path | None:
        markdown_path = record.get("markdown_path")
        if isinstance(markdown_path, str) and markdown_path:
            path = Path(markdown_path)
            return path if path.is_absolute() else self._task_dir(task_id) / path
        default_path = self._task_dir(task_id) / "summary.md"
        return default_path if default_path.exists() else None

    def _serialize_markdown_path(self, task_id: str, markdown_path: Path) -> str:
        path = Path(markdown_path)
        try:
            return str(path.relative_to(self._task_dir(task_id)))
        except ValueError:
            return str(path)

    def _load_json_file(self, path: Path) -> dict | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)


def _cache_index_sort_key(task: SummarySnapshot) -> tuple[int, float]:
    status_priority = {
        "queued": 3,
        "transcribing": 3,
        "summarizing": 3,
        "completed": 2,
    }.get(task.status, 0)
    return status_priority, task.updated_at


summary_store = SummaryStore()
