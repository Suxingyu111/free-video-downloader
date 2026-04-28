from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


TEMPORARY_SUFFIXES = {".part", ".ytdl"}


@dataclass(frozen=True)
class DownloadDirectorySnapshot:
    path: Path
    completed_files: tuple[Path, ...]
    temporary_files: tuple[Path, ...]

    @property
    def has_completed_files(self) -> bool:
        return bool(self.completed_files)

    @property
    def has_temporary_files(self) -> bool:
        return bool(self.temporary_files)

    @property
    def last_updated(self) -> float:
        candidates = [self.path.stat().st_mtime]
        candidates.extend(file_path.stat().st_mtime for file_path in self.completed_files)
        candidates.extend(file_path.stat().st_mtime for file_path in self.temporary_files)
        return max(candidates)


def snapshot_download_dir(path: Path) -> DownloadDirectorySnapshot:
    completed_files: list[Path] = []
    temporary_files: list[Path] = []
    for child in path.iterdir():
        if not child.is_file():
            continue
        if child.suffix in TEMPORARY_SUFFIXES:
            temporary_files.append(child)
        else:
            completed_files.append(child)
    return DownloadDirectorySnapshot(
        path=path,
        completed_files=tuple(sorted(completed_files, key=lambda item: item.name)),
        temporary_files=tuple(sorted(temporary_files, key=lambda item: item.name)),
    )


def remove_temporary_download_files(path: Path) -> DownloadDirectorySnapshot:
    if not path.exists():
        return DownloadDirectorySnapshot(path=path, completed_files=(), temporary_files=())

    snapshot = snapshot_download_dir(path)
    for file_path in snapshot.temporary_files:
        file_path.unlink(missing_ok=True)
    return snapshot_download_dir(path)


def remove_directory_if_empty(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    if any(path.iterdir()):
        return False
    path.rmdir()
    return True


def cleanup_failed_download(path: Path) -> None:
    snapshot = remove_temporary_download_files(path)
    if not snapshot.has_completed_files:
        shutil.rmtree(path, ignore_errors=True)
        return
    remove_directory_if_empty(path)


def prune_download_directories(
    root: Path,
    *,
    keep_completed: int,
    exclude_task_ids: set[str] | None = None,
) -> list[Path]:
    if not root.exists():
        return []

    excluded = exclude_task_ids or set()
    candidates: list[DownloadDirectorySnapshot] = []
    removed: list[Path] = []

    for path in root.iterdir():
        if not path.is_dir() or path.name in excluded:
            continue

        snapshot = remove_temporary_download_files(path)
        if not snapshot.has_completed_files:
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path)
            continue
        candidates.append(snapshot)

    candidates.sort(key=lambda item: item.last_updated, reverse=True)
    for snapshot in candidates[keep_completed:]:
        shutil.rmtree(snapshot.path, ignore_errors=True)
        removed.append(snapshot.path)

    return removed