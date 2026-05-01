from fastapi.testclient import TestClient
import pytest

from app.main import app
from app import summary_routes
from app.services import database
from app.services.summary_store import SummaryStore


class FakeSummaryService:
    def __init__(self):
        self.calls = []
        self.questions = []
        self.seed_results = []

    def generate_summary(self, *, url, title, language, output_dir, progress_hook=None, seed_result=None):
        self.calls.append((url, title, language, output_dir))
        self.seed_results.append(seed_result)
        if progress_hook:
            progress_hook(
                "summary",
                72,
                "Streaming structured summary",
                streamed_text="一句话概览：测试概览\n- 测试要点",
            )
        markdown_path = output_dir / "summary.md"
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text("# Demo\n\n## 一句话概览\n测试概览\n", encoding="utf-8")
        return (
            {
                "overview": "测试概览",
                "outline": [],
                "key_points": ["测试要点"],
                "highlights": [],
                "terms": [],
                "questions": [],
                "mind_map": {"title": "测试概览", "children": []},
                "qa_pairs": [],
                "transcript_text": "[00:01] 测试字幕",
                "transcript_segments": [{"start": 1, "end": 2, "time": "00:01", "text": "测试字幕"}],
                "transcript_source": "subtitle",
            },
            markdown_path,
        )

    def answer_question(self, *, title, transcript, summary, question, language):
        self.questions.append((title, transcript, summary, question, language))
        return f"回答：{question}"


class FailingSummaryService:
    def generate_summary(self, **_kwargs):
        raise RuntimeError("summary boom")


@pytest.fixture()
def isolated_summary_store(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    store = SummaryStore(tmp_path / "summaries")
    monkeypatch.setattr(summary_routes, "summary_store", store)
    monkeypatch.setattr(summary_routes, "SUMMARY_DIR", store.base_dir)
    return store


def login(client):
    client.post(
        "/api/auth/register",
        json={"email": "summary@example.com", "password": "summary-password"},
    )


def wait_for_status(client, summary_id, status):
    for _ in range(20):
        snapshot = client.get(f"/api/summaries/{summary_id}").json()
        if snapshot["status"] == status:
            return snapshot
    return snapshot


def test_create_summary_requires_login(isolated_summary_store):
    client = TestClient(app)

    response = client.post(
        "/api/summaries",
        json={"url": "https://example.com/video", "title": "Demo", "language": "zh-CN"},
    )

    assert response.status_code == 401


def test_create_summary_task_runs_summary_and_exposes_markdown(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    login(client)

    response = client.post(
        "/api/summaries",
        json={"url": "https://example.com/video", "title": "Demo", "language": "zh-CN"},
    )

    assert response.status_code == 200
    summary_id = response.json()["summary_id"]

    snapshot = wait_for_status(client, summary_id, "completed")

    assert snapshot["status"] == "completed"
    assert snapshot["streamed_text"] == "一句话概览：测试概览\n- 测试要点"
    assert snapshot["result"]["overview"] == "测试概览"
    assert snapshot["markdown_url"] == f"/api/summaries/{summary_id}/markdown"
    assert fake.calls[0][0] == "https://example.com/video"

    markdown = client.get(f"/api/summaries/{summary_id}/markdown")
    assert markdown.status_code == 200
    assert "测试概览" in markdown.text

    answer = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "这一段讲了什么？", "language": "zh-CN"},
    )
    assert answer.status_code == 200
    assert answer.json() == {"answer": "回答：这一段讲了什么？"}
    assert fake.questions[0][1] == "[00:01] 测试字幕"


def test_create_summary_reuses_completed_file_cache(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    login(client)

    first = client.post(
        "/api/summaries",
        json={"url": "https://example.com/cached-video", "title": "Demo", "language": "zh-CN"},
    )
    summary_id = first.json()["summary_id"]

    wait_for_status(client, summary_id, "completed")

    second = client.post(
        "/api/summaries",
        json={"url": "https://example.com/cached-video", "title": "Demo", "language": "zh-CN"},
    )

    assert second.status_code == 200
    assert second.json()["summary_id"] == summary_id
    assert second.json()["cache_hit"] is True
    assert len(fake.calls) == 1


def test_cache_hit_does_not_consume_summary_quota(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    login(client)

    first = client.post(
        "/api/summaries",
        json={"url": "https://example.com/quota-cache", "title": "Demo", "language": "zh-CN"},
    )
    summary_id = first.json()["summary_id"]
    assert first.json()["usage"]["used_today"] == 1
    assert first.json()["usage"]["remaining_today"] == 2

    wait_for_status(client, summary_id, "completed")

    cached = client.post(
        "/api/summaries",
        json={"url": "https://example.com/quota-cache", "title": "Demo", "language": "zh-CN"},
    )

    assert cached.status_code == 200
    assert cached.json()["cache_hit"] is True
    assert cached.json()["usage"]["used_today"] == 1
    assert cached.json()["usage"]["remaining_today"] == 2
    assert len(fake.calls) == 1


def test_cached_summary_remains_accessible_after_free_quota_exhausted(monkeypatch, isolated_summary_store):
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "1")
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    login(client)

    first = client.post(
        "/api/summaries",
        json={"url": "https://example.com/only-free-summary", "title": "Demo", "language": "zh-CN"},
    )
    summary_id = first.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")

    uncached = client.post(
        "/api/summaries",
        json={"url": "https://example.com/second-summary", "title": "Demo", "language": "zh-CN"},
    )
    cached = client.post(
        "/api/summaries",
        json={"url": "https://example.com/only-free-summary", "title": "Demo", "language": "zh-CN"},
    )

    assert uncached.status_code == 402
    assert cached.status_code == 200
    assert cached.json()["cache_hit"] is True
    assert cached.json()["usage"]["used_today"] == 1
    assert cached.json()["usage"]["remaining_today"] == 0
    assert len(fake.calls) == 1


def test_create_summary_force_skips_completed_cache(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    login(client)

    first = client.post(
        "/api/summaries",
        json={"url": "https://example.com/force-video", "title": "Demo", "language": "zh-CN"},
    )
    first_summary_id = first.json()["summary_id"]

    wait_for_status(client, first_summary_id, "completed")

    second = client.post(
        "/api/summaries",
        json={"url": "https://example.com/force-video", "title": "Demo", "language": "zh-CN", "force": True},
    )

    assert second.status_code == 200
    assert second.json()["summary_id"] != first_summary_id
    assert second.json()["cache_hit"] is False
    assert second.json()["usage"]["used_today"] == 2
    assert second.json()["usage"]["remaining_today"] == 1

    wait_for_status(client, second.json()["summary_id"], "completed")

    assert fake.seed_results[1]["transcript_text"] == "[00:01] 测试字幕"


def test_failed_summary_refunds_consumed_quota(monkeypatch, isolated_summary_store):
    monkeypatch.setattr(summary_routes, "summary_service", FailingSummaryService())
    client = TestClient(app)
    login(client)

    response = client.post(
        "/api/summaries",
        json={"url": "https://example.com/failing-video", "title": "Demo", "language": "zh-CN"},
    )
    summary_id = response.json()["summary_id"]

    snapshot = wait_for_status(client, summary_id, "failed")
    usage = client.get("/api/me").json()["usage"]

    assert response.status_code == 200
    assert snapshot["status"] == "failed"
    assert usage["used_today"] == 0
    assert usage["remaining_today"] == 3


def test_create_summary_quota_exhaustion_returns_upgrade_message(monkeypatch, isolated_summary_store):
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "1")
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    login(client)

    first = client.post(
        "/api/summaries",
        json={"url": "https://example.com/one", "title": "Demo", "language": "zh-CN"},
    )
    wait_for_status(client, first.json()["summary_id"], "completed")

    second = client.post(
        "/api/summaries",
        json={"url": "https://example.com/two", "title": "Demo", "language": "zh-CN"},
    )

    assert second.status_code == 402
    assert second.json()["detail"] == "今日免费 AI 总结额度已用完，请开通专业版继续使用。"


def test_summary_question_requires_completed_task(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    login(client)

    response = client.post(
        "/api/summaries",
        json={"url": "https://example.com/video", "title": "Demo", "language": "zh-CN"},
    )
    summary_id = response.json()["summary_id"]

    wait_for_status(client, summary_id, "completed")

    summary_routes.summary_store.update_task(summary_id, status="summarizing", result=None)

    answer = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "能回答吗？", "language": "zh-CN"},
    )

    assert answer.status_code == 409


def test_unknown_summary_task_returns_404():
    client = TestClient(app)

    response = client.get("/api/summaries/missing")

    assert response.status_code == 404


def test_summary_errors_localize_youtube_bot_check_without_cookie_prompt():
    message = summary_routes._friendly_summary_error(
        "ERROR: [youtube] DXVHmGoCTco: Sign in to confirm you’re not a bot. "
        "Use --cookies-from-browser or --cookies for the authentication."
    )

    assert "YouTube 要求登录验证" in message
    assert "公开视频" in message
    assert "--cookies" not in message
