from pathlib import Path

from app.services.task_store import TaskStore


def test_task_store_creates_and_updates_task_snapshot():
    store = TaskStore()

    task = store.create_task("https://example.com/video")
    store.update_task(
        task.id,
        status="downloading",
        progress=37.5,
        message="Fetching media",
        speed=2048,
        eta=12,
    )

    snapshot = store.get_task(task.id)

    assert snapshot is not None
    assert snapshot.id == task.id
    assert snapshot.url == "https://example.com/video"
    assert snapshot.status == "downloading"
    assert snapshot.progress == 37.5
    assert snapshot.message == "Fetching media"
    assert snapshot.speed == 2048
    assert snapshot.eta == 12


def test_task_store_registers_file_tokens_without_exposing_paths(tmp_path: Path):
    store = TaskStore()
    output_file = tmp_path / "lesson.mp4"
    output_file.write_text("video", encoding="utf-8")

    token = store.register_file(output_file)
    resolved = store.resolve_file(token)

    assert token
    assert "/" not in token
    assert resolved == output_file


def test_task_store_reports_active_task_ids():
    store = TaskStore()
    queued = store.create_task("https://example.com/queued")
    completed = store.create_task("https://example.com/completed")
    store.update_task(completed.id, status="completed")

    assert store.active_task_ids() == {queued.id}
