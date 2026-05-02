from app.services.summary_store import SummaryStore, build_summary_cache_key, normalize_summary_url


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


def test_summary_store_persists_draft_result_before_final_summary(tmp_path):
    store = SummaryStore(tmp_path)
    task = store.create_task("https://example.com/watch", title="Demo")
    draft = {
        "overview": "快速版概览",
        "outline": [{"time": "00:00", "title": "开场", "summary": "先显示可读草稿"}],
        "key_points": ["先让用户看到内容"],
    }

    store.update_task(
        task.id,
        status="summarizing",
        stage="summary",
        progress=58,
        message="Draft summary ready",
        draft_result=draft,
    )

    restored = SummaryStore(tmp_path)
    snapshot = restored.get_task(task.id)

    assert snapshot is not None
    assert snapshot.draft_result == draft
    assert snapshot.as_dict()["draft_result"] == draft


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


def test_summary_store_restores_previous_completed_cache_after_forced_failure(tmp_path):
    store = SummaryStore(tmp_path)
    completed = store.create_task("https://example.com/watch", title="Demo")
    markdown_path = tmp_path / completed.id / "summary.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("# Demo", encoding="utf-8")
    store.complete_task(completed.id, result={"overview": "旧总结"}, markdown_path=markdown_path)

    forced = store.create_task("https://example.com/watch", title="Demo")
    assert store.get_cached_task("https://example.com/watch", language="zh-CN").id == completed.id

    store.fail_task(forced.id, "YouTube bot check")

    assert store.get_cached_task("https://example.com/watch", language="zh-CN").id == completed.id
    restored = SummaryStore(tmp_path)
    assert restored.get_cached_task("https://example.com/watch", language="zh-CN").id == completed.id


def test_summary_store_selects_cached_task_for_owner_when_index_points_elsewhere(tmp_path):
    store = SummaryStore(tmp_path)
    first = store.create_task("https://example.com/watch", owner_user_id="user_a")
    first_markdown = tmp_path / first.id / "summary.md"
    first_markdown.parent.mkdir(parents=True, exist_ok=True)
    first_markdown.write_text("# First", encoding="utf-8")
    store.complete_task(first.id, result={"overview": "A"}, markdown_path=first_markdown)

    second = store.create_task("https://example.com/watch", owner_user_id="user_b")
    second_markdown = tmp_path / second.id / "summary.md"
    second_markdown.parent.mkdir(parents=True, exist_ok=True)
    second_markdown.write_text("# Second", encoding="utf-8")
    store.complete_task(second.id, result={"overview": "B"}, markdown_path=second_markdown)

    assert store.get_cached_task("https://example.com/watch", owner_user_id="user_a").id == first.id
    assert store.get_cached_task("https://example.com/watch", owner_user_id="user_b").id == second.id


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


def test_summary_store_clones_completed_task_result_without_sharing_mutable_objects(tmp_path):
    store = SummaryStore(tmp_path)
    source = store.create_task(
        "https://example.com/shared-result",
        title="Demo",
        owner_user_id="user_source",
    )
    markdown_path = tmp_path / source.id / "summary.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("# Demo", encoding="utf-8")
    store.complete_task(
        source.id,
        result={"overview": "Demo", "key_points": ["初始要点"]},
        markdown_path=markdown_path,
    )

    cloned = store.clone_completed_task_for_owner(source.id, "user_clone")
    assert cloned is not None

    source_snapshot = store.get_task(source.id)
    cloned_snapshot = store.get_task(cloned.id)
    assert source_snapshot is not None
    assert cloned_snapshot is not None

    source_snapshot.result["key_points"].append("源任务修改")

    assert cloned_snapshot.result == {"overview": "Demo", "key_points": ["初始要点"]}
    assert cloned_snapshot.result is not source_snapshot.result
    assert cloned_snapshot.result["key_points"] is not source_snapshot.result["key_points"]


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


def test_summary_cache_key_normalizes_bilibili_tracking_query():
    first = "https://www.bilibili.com/video/BV14b411Z7QY/?spm_id_from=333.337.search-card.all.click&vd_source=abc"
    second = "https://www.bilibili.com/video/BV14b411Z7QY/"

    assert normalize_summary_url(first) == "https://www.bilibili.com/video/BV14b411Z7QY/"
    assert build_summary_cache_key(first, language="zh-CN") == build_summary_cache_key(second, language="zh-CN")
