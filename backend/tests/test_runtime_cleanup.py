from pathlib import Path

from app.services.runtime_cleanup import cleanup_failed_download
from app.services.runtime_cleanup import prune_download_directories
from app.services.runtime_cleanup import remove_temporary_download_files


def test_remove_temporary_download_files_keeps_completed_files(tmp_path: Path):
    task_dir = tmp_path / "task_123"
    task_dir.mkdir()
    partial = task_dir / "video.mp4.part"
    completed = task_dir / "video.mp4"
    partial.write_bytes(b"partial")
    completed.write_bytes(b"complete")

    snapshot = remove_temporary_download_files(task_dir)

    assert not partial.exists()
    assert completed.exists()
    assert snapshot.completed_files == (completed,)
    assert snapshot.temporary_files == ()


def test_cleanup_failed_download_removes_partial_only_directory(tmp_path: Path):
    task_dir = tmp_path / "task_123"
    task_dir.mkdir()
    (task_dir / "video.mp4.part").write_bytes(b"partial")

    cleanup_failed_download(task_dir)

    assert not task_dir.exists()


def test_prune_download_directories_keeps_recent_completed_and_excludes_active(tmp_path: Path):
    keep_dir = tmp_path / "task_keep"
    keep_dir.mkdir()
    keep_file = keep_dir / "keep.mp4"
    keep_file.write_bytes(b"keep")

    remove_dir = tmp_path / "task_remove"
    remove_dir.mkdir()
    remove_file = remove_dir / "remove.mp4"
    remove_file.write_bytes(b"remove")

    active_dir = tmp_path / "task_active"
    active_dir.mkdir()
    active_file = active_dir / "active.mp4.part"
    active_file.write_bytes(b"active")

    keep_file.touch()
    removed = prune_download_directories(
        tmp_path,
        keep_completed=1,
        exclude_task_ids={"task_active"},
    )

    assert keep_dir.exists()
    assert not remove_dir.exists()
    assert active_dir.exists()
    assert active_file.exists()
    assert removed == [remove_dir]