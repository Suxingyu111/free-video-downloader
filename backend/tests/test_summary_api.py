from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app import summary_routes
from app.services import database, summary_service as summary_service_module
from app.services.auth_service import create_user, get_user_by_id
from app.services.billing_service import activate_mock_subscription
from app.services.entitlements import get_usage_summary, reserve_summary_quota
from app.services.analysis_store import analysis_store
from app.services.plan_catalog import MeterType
from app.services.summary_store import SummaryStore
from app.services.usage_meter import entitlement_status, reserve_user_meter


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
                "duration": 120,
                "transcript_text": "[00:01] 测试字幕",
                "transcript_segments": [{"start": 1, "end": 2, "time": "00:01", "text": "测试字幕"}],
                "transcript_source": "subtitle",
            },
            markdown_path,
        )

    def answer_question(self, *, title, transcript, summary, question, language):
        self.questions.append((title, transcript, summary, question, language))
        return f"回答：{question}"


class SpeechToTextSummaryService(FakeSummaryService):
    def __init__(self, transcription_seconds=125):
        super().__init__()
        self.transcription_seconds = transcription_seconds

    def generate_summary(self, *, url, title, language, output_dir, progress_hook=None, seed_result=None):
        if progress_hook:
            progress_hook(
                "speech_to_text",
                30,
                "Extracting audio for speech-to-text",
                transcription_seconds=self.transcription_seconds,
            )
        return super().generate_summary(
            url=url,
            title=title,
            language=language,
            output_dir=output_dir,
            progress_hook=progress_hook,
            seed_result=seed_result,
        )


class SpeechToTextFailingSummaryService(FakeSummaryService):
    def __init__(self, transcription_seconds=125):
        super().__init__()
        self.transcription_seconds = transcription_seconds

    def generate_summary(self, *, url, title, language, output_dir, progress_hook=None, seed_result=None):
        if progress_hook:
            progress_hook(
                "speech_to_text",
                30,
                "Extracting audio for speech-to-text",
                transcription_seconds=self.transcription_seconds,
            )
        raise RuntimeError("summary boom")


class FailingSummaryService:
    def generate_summary(self, **_kwargs):
        raise RuntimeError("summary boom")


class FailingOnceQuestionService(FakeSummaryService):
    def __init__(self):
        super().__init__()
        self.fail_next_question = True

    def answer_question(self, *, title, transcript, summary, question, language):
        if self.fail_next_question:
            self.fail_next_question = False
            raise RuntimeError("question boom")
        return super().answer_question(
            title=title,
            transcript=transcript,
            summary=summary,
            question=question,
            language=language,
        )


class StartFailingThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        raise RuntimeError("thread start boom")


class NoTranscriptService:
    def fetch_transcript(self, url, output_dir):
        return None


class FakeAudioService:
    def extract_audio(self, url, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_path = output_dir / "audio.wav"
        audio_path.write_bytes(b"fake audio")
        return audio_path


class CountingTranscriptionProvider:
    def __init__(self):
        self.calls = []

    def transcribe_audio(self, audio_path, language):
        self.calls.append((Path(audio_path).name, language))
        return "[00:01] 测试转写"


class FakeAIProvider:
    def summarize_transcript(self, *, title, transcript, language, stream_hook=None):
        return {
            "overview": "测试概览",
            "outline": [],
            "key_points": ["测试要点"],
            "highlights": [],
            "terms": [],
            "questions": [],
            "mind_map": {"title": "测试概览", "children": []},
            "qa_pairs": [],
        }

    def answer_question(self, *, title, transcript, summary, question, language):
        return f"回答：{question}"


@pytest.fixture()
def isolated_summary_store(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")
    store = SummaryStore(tmp_path / "summaries")
    monkeypatch.setattr(summary_routes, "summary_store", store)
    monkeypatch.setattr(summary_routes, "SUMMARY_DIR", store.base_dir)
    return store


def csrf_headers(client):
    response = client.get("/api/csrf")
    return {"x-csrf-token": response.json()["csrf_token"], "origin": "http://localhost:5173"}


def login(client, email="summary@example.com"):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "summary-password"},
        headers=csrf_headers(client),
    )
    return {"x-csrf-token": response.json()["csrf_token"], "origin": "http://localhost:5173"}


def register(client, email):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "summary-password"},
        headers=csrf_headers(client),
    )
    return {"x-csrf-token": response.json()["csrf_token"], "origin": "http://localhost:5173"}


def seed_analysis_snapshot(url, *, duration=120, webpage_url=None):
    analysis_store.create(
        url,
        {
            "kind": "video",
            "id": "summary-test-video",
            "title": "Demo",
            "webpage_url": webpage_url or url,
            "duration": duration,
            "entries": [],
        },
    )


def summary_payload(url, *, server_duration=120, webpage_url=None, **overrides):
    seed_analysis_snapshot(url, duration=server_duration, webpage_url=webpage_url)
    payload = {"url": url, "title": "Demo", "language": "zh-CN"}
    payload.update(overrides)
    return payload


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
        json=summary_payload("https://example.com/video"),
    )

    assert response.status_code == 401


def test_create_summary_requires_session_csrf_after_login(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client, "summary-csrf@example.com")

    missing_csrf = client.post(
        "/api/summaries",
        json={"url": "https://example.com/csrf-video", "title": "Demo", "language": "zh-CN"},
        headers={"origin": "http://localhost:5173"},
    )

    assert missing_csrf.status_code == 403
    assert fake.calls == []

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/csrf-video"),
        headers=session_headers,
    )

    assert response.status_code == 200
    assert response.json()["cache_hit"] is False
    wait_for_status(client, response.json()["summary_id"], "completed")
    assert len(fake.calls) == 1


def test_create_summary_task_runs_summary_and_exposes_markdown(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/video"),
        headers=session_headers,
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
        headers=session_headers,
    )
    assert answer.status_code == 200
    assert answer.json() == {"answer": "回答：这一段讲了什么？"}
    assert fake.questions[0][1] == "[00:01] 测试字幕"


def test_create_summary_reuses_completed_file_cache(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    first = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/cached-video"),
        headers=session_headers,
    )
    summary_id = first.json()["summary_id"]

    wait_for_status(client, summary_id, "completed")

    second = client.post(
        "/api/summaries",
        json={"url": "https://example.com/cached-video", "title": "Demo", "language": "zh-CN"},
        headers=session_headers,
    )

    assert second.status_code == 200
    assert second.json()["summary_id"] == summary_id
    assert second.json()["cache_hit"] is True
    assert len(fake.calls) == 1


def test_summary_result_is_private_to_owner(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    owner_client = TestClient(app)
    intruder_client = TestClient(app)
    owner_headers = login(owner_client, "summary-owner@example.com")
    intruder_headers = login(intruder_client, "summary-intruder@example.com")

    response = owner_client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/private-summary"),
        headers=owner_headers,
    )
    summary_id = response.json()["summary_id"]
    snapshot = wait_for_status(owner_client, summary_id, "completed")
    snapshot_file = isolated_summary_store.base_dir / summary_id / "snapshot.json"

    assert snapshot["status"] == "completed"
    assert "owner_user_id" not in snapshot
    assert "owner_user_id" in snapshot_file.read_text(encoding="utf-8")
    assert intruder_client.get(f"/api/summaries/{summary_id}").status_code == 404
    assert intruder_client.get(f"/api/summaries/{summary_id}/markdown").status_code == 404
    assert intruder_client.get(f"/api/summaries/{summary_id}/events").status_code == 404

    answer = intruder_client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "能看到吗？", "language": "zh-CN"},
        headers=intruder_headers,
    )

    assert answer.status_code == 404


def test_cached_summary_creates_owned_task_for_second_user(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    first_client = TestClient(app)
    second_client = TestClient(app)
    first_headers = login(first_client, "summary-cache-owner@example.com")
    second_headers = login(second_client, "summary-cache-second@example.com")

    first = first_client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/shared-cache"),
        headers=first_headers,
    )
    first_summary_id = first.json()["summary_id"]
    wait_for_status(first_client, first_summary_id, "completed")

    second = second_client.post(
        "/api/summaries",
        json={"url": "https://example.com/shared-cache", "title": "Demo", "language": "zh-CN"},
        headers=second_headers,
    )
    second_summary_id = second.json()["summary_id"]

    assert second.status_code == 200
    assert second.json()["cache_hit"] is True
    assert second_summary_id != first_summary_id
    assert len(fake.calls) == 1
    assert first_client.get(f"/api/summaries/{second_summary_id}").status_code == 404

    second_snapshot = second_client.get(f"/api/summaries/{second_summary_id}")
    second_markdown = second_client.get(f"/api/summaries/{second_summary_id}/markdown")
    second_answer = second_client.post(
        f"/api/summaries/{second_summary_id}/questions",
        json={"question": "缓存内容是什么？", "language": "zh-CN"},
        headers=second_headers,
    )

    assert second_snapshot.status_code == 200
    assert second_snapshot.json()["markdown_url"] == f"/api/summaries/{second_summary_id}/markdown"
    assert second_markdown.status_code == 200
    assert "测试概览" in second_markdown.text
    assert second_answer.status_code == 200
    assert second_answer.json() == {"answer": "回答：缓存内容是什么？"}


def test_force_cross_account_cache_hit_clones_without_regenerating(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    first_client = TestClient(app)
    second_client = TestClient(app)
    first_headers = login(first_client, "summary-force-owner@example.com")
    second_headers = login(second_client, "summary-force-second@example.com")

    first = first_client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/force-shared-cache"),
        headers=first_headers,
    )
    first_summary_id = first.json()["summary_id"]
    wait_for_status(first_client, first_summary_id, "completed")

    second = second_client.post(
        "/api/summaries",
        json={
            "url": "https://example.com/force-shared-cache",
            "title": "Demo",
            "language": "zh-CN",
            "force": True,
        },
        headers=second_headers,
    )
    second_summary_id = second.json()["summary_id"]

    assert second.status_code == 200
    assert second.json()["cache_hit"] is True
    assert second_summary_id != first_summary_id
    assert len(fake.calls) == 1
    assert second_client.get(f"/api/summaries/{second_summary_id}").status_code == 200
    assert first_client.get(f"/api/summaries/{second_summary_id}").status_code == 404


def test_completed_cache_survives_active_task_index_for_third_user(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    first_client = TestClient(app)
    third_client = TestClient(app)
    first_headers = login(first_client, "summary-active-cache-owner@example.com")
    third_headers = login(third_client, "summary-active-cache-third@example.com")
    url = "https://example.com/completed-cache-behind-active"

    first = first_client.post(
        "/api/summaries",
        json=summary_payload(url),
        headers=first_headers,
    )
    first_summary_id = first.json()["summary_id"]
    wait_for_status(first_client, first_summary_id, "completed")

    active = isolated_summary_store.create_task(
        url,
        title="Demo",
        language="zh-CN",
        owner_user_id="user_active_cache_shadow",
        task_id="summary_active_cache_shadow",
    )
    isolated_summary_store.update_task(active.id, status="summarizing", stage="summary")

    third = third_client.post(
        "/api/summaries",
        json={"url": url, "title": "Demo", "language": "zh-CN"},
        headers=third_headers,
    )
    third_summary_id = third.json()["summary_id"]

    assert third.status_code == 200
    assert third.json()["cache_hit"] is True
    assert third_summary_id not in {first_summary_id, active.id}
    assert len(fake.calls) == 1
    assert third_client.get(f"/api/summaries/{third_summary_id}").status_code == 200


def test_create_summary_reuses_completed_task_for_equivalent_bilibili_url(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    first = client.post(
        "/api/summaries",
        json=summary_payload(
            "https://www.bilibili.com/video/BV14b411Z7QY/?spm_id_from=333.337.search-card.all.click&vd_source=abc"
        ),
        headers=session_headers,
    )
    first_summary_id = first.json()["summary_id"]
    wait_for_status(client, first_summary_id, "completed")

    second = client.post(
        "/api/summaries",
        json={"url": "https://www.bilibili.com/video/BV14b411Z7QY/", "title": "Demo", "language": "zh-CN"},
        headers=session_headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["summary_id"] == first_summary_id
    assert second.json()["cache_hit"] is True
    assert len(fake.calls) == 1


def test_create_summary_does_not_reuse_active_task(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    active = isolated_summary_store.create_task(
        "https://example.com/active-cache-video",
        title="Demo",
        language="zh-CN",
        task_id="summary_active_cache_video",
    )
    isolated_summary_store.update_task(active.id, status="summarizing", stage="summary")

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/active-cache-video"),
        headers=session_headers,
    )

    assert response.status_code == 200
    assert response.json()["summary_id"] != active.id
    assert response.json()["cache_hit"] is False
    assert response.json()["usage"]["used_today"] == 1
    assert response.json()["usage"]["remaining_today"] == 2
    assert len(fake.calls) == 1


def test_cache_hit_does_not_consume_summary_quota(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    first = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/quota-cache"),
        headers=session_headers,
    )
    summary_id = first.json()["summary_id"]
    assert first.json()["usage"]["used_today"] == 1
    assert first.json()["usage"]["remaining_today"] == 2

    wait_for_status(client, summary_id, "completed")

    cached = client.post(
        "/api/summaries",
        json={"url": "https://example.com/quota-cache", "title": "Demo", "language": "zh-CN"},
        headers=session_headers,
    )

    assert cached.status_code == 200
    assert cached.json()["cache_hit"] is True
    assert cached.json()["usage"]["used_today"] == 1
    assert cached.json()["usage"]["remaining_today"] == 2
    assert len(fake.calls) == 1


def test_uncached_summary_without_duration_returns_400_without_consuming_quota(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json={"url": "https://example.com/missing-duration", "title": "Demo", "language": "zh-CN"},
        headers=session_headers,
    )
    usage = client.get("/api/me").json()["usage"]

    assert response.status_code == 400
    assert response.json()["detail"] == "请先解析视频后再生成 AI 总结。"
    assert usage["used_today"] == 0
    assert usage["remaining_today"] == 3
    assert fake.calls == []


def test_summary_uses_server_analysis_duration_not_client_duration(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload(
            "https://example.com/spoofed-short-duration",
            server_duration=31 * 60,
            duration=1,
        ),
        headers=session_headers,
    )
    usage = client.get("/api/me").json()["usage"]

    assert response.status_code == 402
    assert "30 分钟" in response.json()["detail"]
    assert usage["used_today"] == 0
    assert usage["remaining_today"] == 3
    assert fake.calls == []


def test_summary_can_use_canonical_url_from_analysis_snapshot_without_duration(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)
    submitted_url = "https://example.com/watch?id=raw"
    canonical_url = "https://example.com/watch/canonical"
    seed_analysis_snapshot(submitted_url, duration=120, webpage_url=canonical_url)

    response = client.post(
        "/api/summaries",
        json={"url": canonical_url, "title": "Demo", "language": "zh-CN"},
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")

    assert response.status_code == 200
    assert response.json()["cache_hit"] is False
    assert fake.calls[0][0] == canonical_url


def test_cached_summary_remains_accessible_after_free_quota_exhausted(monkeypatch, isolated_summary_store):
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "1")
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    first = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/only-free-summary"),
        headers=session_headers,
    )
    summary_id = first.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")

    uncached = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/second-summary"),
        headers=session_headers,
    )
    cached = client.post(
        "/api/summaries",
        json={"url": "https://example.com/only-free-summary", "title": "Demo", "language": "zh-CN"},
        headers=session_headers,
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
    session_headers = login(client)

    first = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/force-video"),
        headers=session_headers,
    )
    first_summary_id = first.json()["summary_id"]

    wait_for_status(client, first_summary_id, "completed")

    second = client.post(
        "/api/summaries",
        json={"url": "https://example.com/force-video", "title": "Demo", "language": "zh-CN", "force": True},
        headers=session_headers,
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
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/failing-video"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]

    snapshot = wait_for_status(client, summary_id, "failed")
    usage = client.get("/api/me").json()["usage"]

    assert response.status_code == 200
    assert snapshot["status"] == "failed"
    assert usage["used_today"] == 0
    assert usage["remaining_today"] == 3


def test_failed_pro_summary_refunds_metered_quota(monkeypatch, isolated_summary_store):
    monkeypatch.setattr(summary_routes, "summary_service", FailingSummaryService())
    client = TestClient(app)
    session_headers = login(client)
    user = get_user_by_id(client.get("/api/me").json()["user"]["id"])
    assert user is not None
    activate_mock_subscription(user)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/failing-pro-video"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]

    snapshot = wait_for_status(client, summary_id, "failed")
    status = client.get("/api/entitlements/status").json()

    assert response.status_code == 200
    assert snapshot["status"] == "failed"
    assert status["plan"] == "pro"
    assert status["meters"]["summary"]["used"] == 0
    assert status["meters"]["summary"]["remaining"] == 120


def test_task_creation_failure_after_reservation_refunds_quota(monkeypatch, isolated_summary_store):
    def fail_create_task(*args, **kwargs):
        raise RuntimeError("create task boom")

    monkeypatch.setattr(summary_routes.summary_store, "create_task", fail_create_task)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/create-task-fails"),
        headers=session_headers,
    )
    usage = client.get("/api/me").json()["usage"]

    assert response.status_code == 500
    assert response.json()["detail"] == "AI 总结任务创建失败，请稍后重试。"
    assert usage["used_today"] == 0
    assert usage["remaining_today"] == 3


def test_worker_start_failure_after_task_creation_refunds_quota(monkeypatch, isolated_summary_store):
    monkeypatch.setattr(summary_routes.threading, "Thread", StartFailingThread)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/worker-start-fails"),
        headers=session_headers,
    )
    usage = client.get("/api/me").json()["usage"]

    assert response.status_code == 500
    assert response.json()["detail"] == "AI 总结任务创建失败，请稍后重试。"
    assert usage["used_today"] == 0
    assert usage["remaining_today"] == 3


def test_interrupted_summary_task_refunds_quota_on_startup(monkeypatch, isolated_summary_store):
    user = create_user("restart@example.com", "summary-password")
    summary_id = "summary_interrupted_video"
    reserve_summary_quota(user, summary_id)

    task = isolated_summary_store.create_task(
        "https://example.com/interrupted-video",
        title="Demo",
        language="zh-CN",
        quota_user_id=user.id,
        task_id=summary_id,
    )
    isolated_summary_store.update_task(task.id, status="summarizing", stage="summary")

    restarted_store = SummaryStore(isolated_summary_store.base_dir)
    monkeypatch.setattr(summary_routes, "summary_store", restarted_store)
    summary_routes.refund_interrupted_summary_quotas()

    usage = get_usage_summary(user)
    restarted_task = restarted_store.get_task(task.id)

    assert restarted_task.status == "failed"
    assert restarted_task.quota_refunded_at is not None
    assert usage.used_today == 0
    assert usage.remaining_today == 3
    with database.connect() as conn:
        reservation = conn.execute(
            "select refunded_at from summary_quota_reservations where reservation_id = ?",
            (summary_id,),
        ).fetchone()
    assert reservation["refunded_at"] is not None


def test_interrupted_summary_quota_refund_is_idempotent(monkeypatch, isolated_summary_store):
    user = create_user("restart-idempotent@example.com", "summary-password")
    summary_id = "summary_interrupted_idempotent_video"
    reserve_summary_quota(user, summary_id)

    task = isolated_summary_store.create_task(
        "https://example.com/interrupted-idempotent-video",
        title="Demo",
        language="zh-CN",
        quota_user_id=user.id,
        task_id=summary_id,
    )
    isolated_summary_store.update_task(task.id, status="summarizing", stage="summary")

    restarted_store = SummaryStore(isolated_summary_store.base_dir)
    monkeypatch.setattr(summary_routes, "summary_store", restarted_store)

    summary_routes.refund_interrupted_summary_quotas()
    summary_routes.refund_interrupted_summary_quotas()

    usage = get_usage_summary(user)
    refunded_tasks = restarted_store.pending_quota_refunds()

    assert usage.used_today == 0
    assert usage.remaining_today == 3
    assert refunded_tasks == []
    with database.connect() as conn:
        reservation = conn.execute(
            "select summary_count, refunded_at from summary_quota_reservations "
            "join usage_daily using (user_id, usage_date) "
            "where reservation_id = ?",
            (summary_id,),
        ).fetchone()
    assert reservation["summary_count"] == 0
    assert reservation["refunded_at"] is not None


def test_interrupted_summary_refunds_transcription_reservation_idempotently(monkeypatch, isolated_summary_store):
    user = create_user("restart-transcription@example.com", "summary-password")
    summary_id = "summary_interrupted_transcription_video"
    transcription_reservation_id = f"{summary_id}_transcription"
    reserve_summary_quota(user, summary_id)
    reserve_user_meter(
        user,
        MeterType.TRANSCRIPTION_MINUTES,
        4,
        reservation_id=transcription_reservation_id,
    )

    task = isolated_summary_store.create_task(
        "https://example.com/interrupted-transcription-video",
        title="Demo",
        language="zh-CN",
        quota_user_id=user.id,
        task_id=summary_id,
    )
    isolated_summary_store.update_task(task.id, status="summarizing", stage="summary")

    restarted_store = SummaryStore(isolated_summary_store.base_dir)
    monkeypatch.setattr(summary_routes, "summary_store", restarted_store)

    summary_routes.refund_interrupted_summary_quotas()
    summary_routes.refund_interrupted_summary_quotas()

    status = entitlement_status(user)
    restarted_task = restarted_store.get_task(task.id)

    assert restarted_task.quota_refunded_at is not None
    assert status["meters"]["summary"]["used"] == 0
    assert status["meters"]["transcription_minutes"]["used"] == 0
    assert status["meters"]["transcription_minutes"]["remaining"] == 30
    with database.connect() as conn:
        reservation = conn.execute(
            "select status, refunded_at from meter_reservations where reservation_id = ?",
            (transcription_reservation_id,),
        ).fetchone()
    assert reservation["status"] == "refunded"
    assert reservation["refunded_at"] is not None


def test_summary_response_hides_internal_quota_metadata(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/private-quota-metadata"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    snapshot = wait_for_status(client, summary_id, "completed")

    assert "quota_user_id" not in snapshot
    assert "quota_refunded_at" not in snapshot


def test_summary_owner_is_persisted_but_not_exposed(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)
    user_id = client.get("/api/me").json()["user"]["id"]

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/owner-persisted"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    snapshot = wait_for_status(client, summary_id, "completed")
    restored_store = SummaryStore(isolated_summary_store.base_dir)
    restored = restored_store.get_task(summary_id)

    assert isolated_summary_store.get_task(summary_id).owner_user_id == user_id
    assert restored is not None
    assert restored.owner_user_id == user_id
    assert "owner_user_id" not in snapshot


def test_create_summary_quota_exhaustion_returns_upgrade_message(monkeypatch, isolated_summary_store):
    monkeypatch.setenv("FREE_SUMMARY_DAILY_LIMIT", "1")
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    first = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/one"),
        headers=session_headers,
    )
    wait_for_status(client, first.json()["summary_id"], "completed")

    second = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/two"),
        headers=session_headers,
    )

    assert second.status_code == 402
    assert second.json()["detail"] == "今日免费 AI 总结额度已用完，请开通专业版继续使用。"


def test_summary_question_requires_completed_task(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/video"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]

    wait_for_status(client, summary_id, "completed")

    summary_routes.summary_store.update_task(summary_id, status="summarizing", result=None)

    answer = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "能回答吗？", "language": "zh-CN"},
        headers=session_headers,
    )

    assert answer.status_code == 409


def test_summary_task_records_owner_and_question_requires_login(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/owned-video"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")
    client.post("/api/auth/logout", headers=session_headers)

    answer = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "这一段讲了什么？", "language": "zh-CN"},
    )

    assert answer.status_code == 401


def test_second_user_cannot_ask_question_on_owned_summary(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/owned-by-first-user"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")
    client.post("/api/auth/logout", headers=session_headers)
    other_headers = register(client, "summary-other@example.com")

    answer = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "能访问吗？", "language": "zh-CN"},
        headers=other_headers,
    )

    assert answer.status_code == 404
    assert answer.json()["detail"] == "Summary task not found"


def test_second_user_receives_owned_clone_from_first_users_cached_summary(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)
    url = "https://example.com/shared-owned-cache"

    first = client.post(
        "/api/summaries",
        json=summary_payload(url),
        headers=session_headers,
    )
    first_summary_id = first.json()["summary_id"]
    wait_for_status(client, first_summary_id, "completed")
    client.post("/api/auth/logout", headers=session_headers)
    other_headers = register(client, "summary-cache-other@example.com")

    second = client.post(
        "/api/summaries",
        json={"url": url, "title": "Demo", "language": "zh-CN"},
        headers=other_headers,
    )
    second_summary_id = second.json()["summary_id"]
    wait_for_status(client, second_summary_id, "completed")

    assert second.status_code == 200
    assert second.json()["cache_hit"] is True
    assert second_summary_id != first_summary_id
    assert len(fake.calls) == 1


def test_owner_cache_returns_original_user_task_after_another_user_updates_index(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    url = "https://example.com/shared-owned-cache-roundtrip"
    client_a = TestClient(app)
    client_b = TestClient(app)
    client_a_headers = register(client_a, "summary-cache-a@example.com")

    first = client_a.post(
        "/api/summaries",
        json=summary_payload(url),
        headers=client_a_headers,
    )
    first_summary_id = first.json()["summary_id"]
    wait_for_status(client_a, first_summary_id, "completed")
    usage_after_first = client_a.get("/api/me").json()["usage"]

    client_b_headers = register(client_b, "summary-cache-b@example.com")
    second = client_b.post(
        "/api/summaries",
        json=summary_payload(url),
        headers=client_b_headers,
    )
    second_summary_id = second.json()["summary_id"]
    wait_for_status(client_b, second_summary_id, "completed")

    third = client_a.post(
        "/api/summaries",
        json={"url": url, "title": "Demo", "language": "zh-CN"},
        headers=client_a_headers,
    )
    usage_after_third = client_a.get("/api/me").json()["usage"]

    assert second.status_code == 200
    assert second.json()["cache_hit"] is True
    assert second_summary_id != first_summary_id
    assert third.status_code == 200
    assert third.json()["cache_hit"] is True
    assert third.json()["summary_id"] == first_summary_id
    assert usage_after_third["used_today"] == usage_after_first["used_today"]
    assert len(fake.calls) == 1


def test_free_user_summary_duration_limit(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/long-free-video", server_duration=31 * 60),
        headers=session_headers,
    )

    assert response.status_code == 402
    assert "30 分钟" in response.json()["detail"]


def test_free_user_question_limit(monkeypatch, isolated_summary_store):
    fake = FakeSummaryService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app)
    session_headers = login(client)
    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/questions"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")

    for index in range(3):
        assert client.post(
            f"/api/summaries/{summary_id}/questions",
            json={"question": f"问题 {index}", "language": "zh-CN"},
            headers=session_headers,
        ).status_code == 200

    blocked = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "第四个问题", "language": "zh-CN"},
        headers=session_headers,
    )

    assert blocked.status_code == 402
    assert "追问次数" in blocked.json()["detail"]


def test_failed_question_refunds_question_limit(monkeypatch, isolated_summary_store):
    fake = FailingOnceQuestionService()
    monkeypatch.setattr(summary_routes, "summary_service", fake)
    client = TestClient(app, raise_server_exceptions=False)
    session_headers = login(client)
    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/question-refund"),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")

    failed = client.post(
        f"/api/summaries/{summary_id}/questions",
        json={"question": "失败的问题", "language": "zh-CN"},
        headers=session_headers,
    )

    assert failed.status_code >= 400
    for index in range(3):
        assert client.post(
            f"/api/summaries/{summary_id}/questions",
            json={"question": f"成功问题 {index}", "language": "zh-CN"},
            headers=session_headers,
        ).status_code == 200


def test_speech_to_text_reserves_transcription_minutes(monkeypatch, isolated_summary_store):
    monkeypatch.setattr(summary_routes, "summary_service", SpeechToTextSummaryService())
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/no-subtitles", server_duration=125),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")
    usage = client.get("/api/entitlements/status").json()

    assert usage["meters"]["transcription_minutes"]["used"] == 3
    assert usage["meters"]["transcription_minutes"]["remaining"] == 27


def test_speech_to_text_fractional_seconds_round_up_minutes(monkeypatch, isolated_summary_store):
    monkeypatch.setattr(summary_routes, "summary_service", SpeechToTextSummaryService(60.1))
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/fractional-transcription", server_duration=60.1),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    wait_for_status(client, summary_id, "completed")
    usage = client.get("/api/entitlements/status").json()

    assert usage["meters"]["transcription_minutes"]["used"] == 2
    assert usage["meters"]["transcription_minutes"]["remaining"] == 28


def test_speech_to_text_quota_failure_blocks_preview_and_full_transcription(monkeypatch, isolated_summary_store):
    transcription_provider = CountingTranscriptionProvider()
    service = summary_service_module.SummaryService(
        transcript_service=NoTranscriptService(),
        audio_service=FakeAudioService(),
        ai_provider=FakeAIProvider(),
        transcription_provider=transcription_provider,
    )

    def create_preview(audio_path, output_dir, *, seconds=None):
        output_dir.mkdir(parents=True, exist_ok=True)
        preview_path = output_dir / "preview.wav"
        preview_path.write_bytes(b"fake preview")
        return preview_path

    monkeypatch.setattr(summary_routes, "summary_service", service)
    monkeypatch.setattr(summary_service_module, "create_audio_preview_clip", create_preview)
    monkeypatch.setattr(summary_service_module, "estimate_audio_duration_seconds", lambda audio_path: 31 * 60)
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/stt-quota-exceeded-before-preview", server_duration=120),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    snapshot = wait_for_status(client, summary_id, "failed")
    status = client.get("/api/entitlements/status").json()

    assert response.status_code == 200
    assert snapshot["status"] == "failed"
    assert transcription_provider.calls == []
    assert status["meters"]["summary"]["used"] == 0
    assert status["meters"]["transcription_minutes"]["used"] == 0
    with database.connect() as conn:
        reservation = conn.execute(
            "select status from meter_reservations where reservation_id = ?",
            (f"{summary_id}_transcription",),
        ).fetchone()
    assert reservation is None


def test_speech_to_text_summary_failure_refunds_summary_and_transcription_minutes(monkeypatch, isolated_summary_store):
    monkeypatch.setattr(summary_routes, "summary_service", SpeechToTextFailingSummaryService(125))
    client = TestClient(app)
    session_headers = login(client)

    response = client.post(
        "/api/summaries",
        json=summary_payload("https://example.com/stt-summary-fails-after-reservation", server_duration=125),
        headers=session_headers,
    )
    summary_id = response.json()["summary_id"]
    snapshot = wait_for_status(client, summary_id, "failed")
    status = client.get("/api/entitlements/status").json()

    assert response.status_code == 200
    assert snapshot["status"] == "failed"
    assert status["meters"]["summary"]["used"] == 0
    assert status["meters"]["transcription_minutes"]["used"] == 0
    assert status["meters"]["transcription_minutes"]["remaining"] == 30
    with database.connect() as conn:
        reservation = conn.execute(
            "select status, refunded_at from meter_reservations where reservation_id = ?",
            (f"{summary_id}_transcription",),
        ).fetchone()
    assert reservation["status"] == "refunded"
    assert reservation["refunded_at"] is not None


@pytest.mark.parametrize("raw_duration", ["nan", "inf"])
def test_transcription_duration_estimate_non_finite_values_fall_back_to_one_minute(
    monkeypatch,
    tmp_path,
    raw_duration,
):
    class Result:
        stdout = raw_duration

    monkeypatch.setattr(
        summary_service_module.subprocess,
        "run",
        lambda *args, **kwargs: Result(),
    )

    seconds = summary_service_module.estimate_audio_duration_seconds(tmp_path / "audio.wav")

    assert seconds == 1.0
    assert summary_routes._transcription_minutes_from_seconds(seconds) == 1


def test_unknown_summary_task_returns_404(isolated_summary_store):
    client = TestClient(app)
    login(client, "summary-missing@example.com")

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
