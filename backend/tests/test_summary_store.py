from app.services.summary_store import SummaryStore


def test_summary_store_tracks_task_lifecycle_and_result():
    store = SummaryStore()

    task = store.create_task("https://example.com/watch", title="Demo")
    store.update_task(
        task.id,
        status="transcribing",
        stage="subtitle",
        progress=24.5,
        message="Extracting subtitles",
    )

    snapshot = store.get_task(task.id)

    assert snapshot is not None
    assert snapshot.url == "https://example.com/watch"
    assert snapshot.title == "Demo"
    assert snapshot.status == "transcribing"
    assert snapshot.stage == "subtitle"
    assert snapshot.progress == 24.5
    assert snapshot.message == "Extracting subtitles"


def test_summary_store_completes_with_markdown_url_without_exposing_path(tmp_path):
    store = SummaryStore()
    task = store.create_task("https://example.com/watch")
    markdown_path = tmp_path / "summary.md"
    markdown_path.write_text("# Demo", encoding="utf-8")

    store.complete_task(
        task.id,
        result={"overview": "Demo overview"},
        markdown_path=markdown_path,
    )

    snapshot = store.get_task(task.id)

    assert snapshot is not None
    assert snapshot.status == "completed"
    assert snapshot.progress == 100
    assert snapshot.result == {"overview": "Demo overview"}
    assert snapshot.markdown_url == f"/api/summaries/{task.id}/markdown"
    assert "/" not in task.id
    assert store.resolve_markdown(task.id) == markdown_path


def test_summary_store_failed_tasks_are_not_active():
    store = SummaryStore()
    active = store.create_task("https://example.com/active")
    failed = store.create_task("https://example.com/failed")
    store.fail_task(failed.id, "Provider unavailable")

    assert store.active_task_ids() == {active.id}
    assert store.get_task(failed.id).status == "failed"
    assert store.get_task(failed.id).error == "Provider unavailable"
