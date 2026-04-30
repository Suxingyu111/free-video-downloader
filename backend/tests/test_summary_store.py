from app.services.summary_store import SummaryStore, build_summary_cache_key


def test_summary_store_tracks_task_lifecycle_and_result(tmp_path):
    store = SummaryStore(tmp_path)

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


def test_summary_store_exposes_streamed_text_during_generation(tmp_path):
    store = SummaryStore(tmp_path)
    task = store.create_task("https://example.com/watch", title="Demo")

    store.update_task(
        task.id,
        status="summarizing",
        stage="summary",
        progress=78,
        message="Streaming structured summary",
        streamed_text="一句话概览：正在生成内容\n- 核心知识点：第一条",
    )

    snapshot = store.get_task(task.id)

    assert snapshot is not None
    assert snapshot.streamed_text == "一句话概览：正在生成内容\n- 核心知识点：第一条"
    assert snapshot.as_dict()["streamed_text"] == "一句话概览：正在生成内容\n- 核心知识点：第一条"


def test_summary_store_completes_with_markdown_url_without_exposing_path(tmp_path):
    store = SummaryStore(tmp_path / "summaries")
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


def test_summary_store_failed_tasks_are_not_active(tmp_path):
    store = SummaryStore(tmp_path)
    active = store.create_task("https://example.com/active")
    failed = store.create_task("https://example.com/failed")
    store.fail_task(failed.id, "Provider unavailable")

    assert store.active_task_ids() == {active.id}
    assert store.get_task(failed.id).status == "failed"
    assert store.get_task(failed.id).error == "Provider unavailable"


def test_summary_store_recovers_completed_snapshots_from_disk(tmp_path):
    store = SummaryStore(tmp_path)
    task = store.create_task("https://example.com/watch", title="Demo", language="zh-CN")
    markdown_path = tmp_path / task.id / "summary.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("# Demo", encoding="utf-8")

    store.complete_task(task.id, result={"overview": "Demo overview"}, markdown_path=markdown_path)

    restored = SummaryStore(tmp_path)
    snapshot = restored.get_task(task.id)

    assert snapshot is not None
    assert snapshot.status == "completed"
    assert snapshot.result == {"overview": "Demo overview"}
    assert snapshot.markdown_url == f"/api/summaries/{task.id}/markdown"
    assert restored.resolve_markdown(task.id) == markdown_path
    assert restored.get_cached_task("https://example.com/watch", language="zh-CN").id == task.id


def test_summary_store_marks_active_disk_snapshots_failed_after_restart(tmp_path):
    store = SummaryStore(tmp_path)
    task = store.create_task("https://example.com/watch", title="Demo")
    store.update_task(task.id, status="summarizing", stage="summary", progress=82, message="Generating structured summary")

    restored = SummaryStore(tmp_path)
    snapshot = restored.get_task(task.id)

    assert snapshot is not None
    assert snapshot.status == "failed"
    assert "重启" in snapshot.error
    assert restored.get_cached_task("https://example.com/watch", language="zh-CN") is None


def test_summary_cache_key_includes_language():
    assert build_summary_cache_key("https://example.com/watch", language="zh-CN") != build_summary_cache_key(
        "https://example.com/watch",
        language="en-US",
    )
