import inspect
import json

from fastapi.testclient import TestClient

from app import main
from app.main import DownloadRequest
from app.main import app
from app.main import proxy_media_assets
from app.services import database


def test_health_endpoint_returns_ok():
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "free-video-downloader"}


def test_proxy_media_assets_rewrites_video_and_playlist_thumbnails():
    result = {
        "webpage_url": "https://www.bilibili.com/video/BV1root",
        "thumbnail": "https://i0.hdslb.com/root.jpg",
        "entries": [
            {
                "url": "https://www.bilibili.com/video/BV1child",
                "thumbnail": "https://i0.hdslb.com/child.jpg",
            }
        ],
    }

    rewritten = proxy_media_assets(result)

    assert rewritten["thumbnail"].startswith("/api/proxy/assets/")
    assert rewritten["entries"][0]["thumbnail"].startswith("/api/proxy/assets/")


def test_api_contract_has_no_manual_cookie_fields():
    analyze_signature = inspect.signature(main.analyze)

    assert "cookies_file" not in analyze_signature.parameters
    assert "cookie_ref" not in DownloadRequest.model_fields


def test_analyze_retries_transient_youtube_bot_check(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    database.initialize_database(tmp_path / "saveany.db")

    class FlakyService:
        def __init__(self):
            self.calls = 0

        def analyze(self, url):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("ERROR: [youtube] abc: Sign in to confirm you’re not a bot.")
            return {
                "kind": "video",
                "id": "abc",
                "title": "Recovered",
                "webpage_url": url,
                "thumbnail": None,
                "entries": [],
            }

    fake_service = FlakyService()
    monkeypatch.setattr(main, "service", fake_service)
    client = TestClient(app)

    response = client.post("/api/analyze", data={"url": "https://www.youtube.com/watch?v=abc"})

    assert response.status_code == 200
    assert response.json()["title"] == "Recovered"
    assert fake_service.calls == 2


def test_demo_analyze_result_is_env_gated(monkeypatch):
    monkeypatch.delenv("SAVEANY_DEMO_MODE", raising=False)

    assert main.demo_analyze_result("https://demo.saveany.local/video") is None

    monkeypatch.setenv("SAVEANY_DEMO_MODE", "true")

    result = main.demo_analyze_result("https://demo.saveany.local/video")

    assert result["title"] == "AI 视频总结演示课"
    assert result["extractor"] == "demo"


def test_demo_download_file_is_env_gated(monkeypatch, tmp_path):
    monkeypatch.delenv("SAVEANY_DEMO_MODE", raising=False)

    assert main.demo_download_file("https://demo.saveany.local/video", tmp_path) is None

    monkeypatch.setenv("SAVEANY_DEMO_MODE", "true")

    output = main.demo_download_file("https://demo.saveany.local/video", tmp_path)

    assert output is not None
    assert output.name == "saveany-demo-video.mp4"
    assert output.read_bytes().startswith(b"SaveAny demo video placeholder")


def test_frontend_dist_serves_geo_assets_and_real_404(monkeypatch, tmp_path):
    monkeypatch.delenv("SEO_CANONICAL_REDIRECTS", raising=False)
    dist = tmp_path / "dist"
    page_dir = dist / "video-summary"
    page_dir.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id='app'></div>", encoding="utf-8")
    (dist / "404.html").write_text("<!doctype html><h1>页面未找到</h1>", encoding="utf-8")
    (dist / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    (dist / "llms.txt").write_text("# 万能视频下载总结器\n", encoding="utf-8")
    (page_dir / "index.html").write_text("<h1>AI视频总结器</h1>", encoding="utf-8")
    (page_dir / "index.html.md").write_text("# AI视频总结器\n", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)
    client = TestClient(app)

    assert client.get("/robots.txt").status_code == 200
    assert client.get("/llms.txt").text.startswith("# 万能视频下载总结器")
    page_response = client.get("/video-summary/")
    assert page_response.headers["cache-control"] == "no-cache"
    assert "AI视频总结器" in page_response.text
    slash_response = client.get("/video-summary", follow_redirects=False)
    assert slash_response.status_code == 308
    assert slash_response.headers["location"].endswith("/video-summary/")
    assert client.get("/video-summary/index.html.md").headers["content-type"].startswith("text/markdown")
    missing_route = client.get("/client-side-route")
    assert missing_route.status_code == 404
    assert "页面未找到" in missing_route.text
    assert client.get("/missing.txt").status_code == 404


def test_frontend_can_enforce_canonical_https_host(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id='app'></div>", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)
    monkeypatch.setenv("SEO_CANONICAL_REDIRECTS", "true")
    monkeypatch.setenv("VITE_PUBLIC_SITE_URL", "https://www.saveany.example")
    client = TestClient(app)

    response = client.get(
        "/?utm_source=test",
        headers={"host": "saveany.example", "x-forwarded-proto": "http"},
        follow_redirects=False,
    )

    assert response.status_code == 308
    assert response.headers["location"] == "https://www.saveany.example/?utm_source=test"


def test_geo_access_monitor_logs_crawler_and_geo_assets(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><div id='app'></div>", encoding="utf-8")
    (dist / "llms.txt").write_text("# 万能视频下载总结器\n", encoding="utf-8")
    log_file = tmp_path / "geo-access.jsonl"
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)
    monkeypatch.setattr(main, "GEO_ACCESS_LOG", log_file)
    client = TestClient(app)

    response = client.get("/llms.txt?secret=not-logged", headers={"User-Agent": "OAI-SearchBot"})

    assert response.status_code == 200
    records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert records[0]["path"] == "/llms.txt"
    assert records[0]["crawler"] == "openai-search"
    assert "secret" not in json.dumps(records[0])


def test_analyze_returns_analysis_token(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_DEMO_MODE", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    response = client.post("/api/analyze", data={"url": "https://demo.saveany.local/video"})

    assert response.status_code == 200
    assert response.json()["analysis_token"].startswith("analysis_")
    assert response.json()["duration"] == 618


def test_blank_analyze_url_does_not_consume_anonymous_quota(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)
    client = TestClient(app)

    response = client.post("/api/analyze", data={"url": "   "})

    conn = database.connect(db_path)
    try:
        usage = conn.execute("select coalesce(sum(analyze_count), 0) as used from anonymous_usage").fetchone()
    finally:
        conn.close()

    assert response.status_code == 400
    assert int(usage["used"]) == 0


def test_anonymous_analyze_limit_blocks_fourth_request(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_DEMO_MODE", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    for _ in range(3):
        assert client.post("/api/analyze", data={"url": "https://demo.saveany.local/video"}).status_code == 200

    blocked = client.post("/api/analyze", data={"url": "https://demo.saveany.local/video"})

    assert blocked.status_code == 429
    assert "访客解析次数已用完" in blocked.json()["detail"]


def test_download_uses_analysis_token_and_anonymous_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVEANY_DB_PATH", str(tmp_path / "saveany.db"))
    monkeypatch.setenv("SAVEANY_DEMO_MODE", "true")
    database.initialize_database(tmp_path / "saveany.db")
    client = TestClient(app)

    analyzed = client.post("/api/analyze", data={"url": "https://demo.saveany.local/video"}).json()
    first = client.post(
        "/api/download",
        json={
            "url": analyzed["webpage_url"],
            "analysis_token": analyzed["analysis_token"],
            "format_id": "best",
            "entry_ids": [],
            "subtitle_langs": [],
            "write_auto_subs": False,
            "prefer_srt": True,
        },
    )
    second = client.post(
        "/api/download",
        json={
            "url": analyzed["webpage_url"],
            "analysis_token": analyzed["analysis_token"],
            "format_id": "best",
            "entry_ids": [],
            "subtitle_langs": [],
            "write_auto_subs": False,
            "prefer_srt": True,
        },
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert "访客下载次数已用完" in second.json()["detail"]


def test_anonymous_multi_entry_download_limit_is_atomic(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)
    client = TestClient(app)
    url = "https://example.com/playlist"
    token = main.analysis_store.create(
        url,
        {
            "kind": "playlist",
            "webpage_url": url,
            "entries": [
                {"id": "one", "url": "https://example.com/playlist/one"},
                {"id": "two", "url": "https://example.com/playlist/two"},
            ],
        },
    )

    response = client.post(
        "/api/download",
        json={
            "url": url,
            "analysis_token": token,
            "format_id": "best",
            "entry_ids": [],
            "subtitle_langs": [],
            "write_auto_subs": False,
            "prefer_srt": True,
        },
    )

    conn = database.connect(db_path)
    try:
        usage = conn.execute("select coalesce(sum(download_count), 0) as used from anonymous_usage").fetchone()
    finally:
        conn.close()

    assert response.status_code == 429
    assert "访客下载次数已用完" in response.json()["detail"]
    assert int(usage["used"]) == 0


def test_download_analysis_token_matches_canonical_webpage_url(monkeypatch, tmp_path):
    db_path = tmp_path / "saveany.db"
    monkeypatch.setenv("SAVEANY_DB_PATH", str(db_path))
    database.initialize_database(db_path)
    original_url = "https://example.com/watch?id=original"
    canonical_url = "https://example.com/watch/canonical"

    class CanonicalService:
        def __init__(self):
            self.analyze_calls = []

        def analyze(self, url):
            self.analyze_calls.append(url)
            return {
                "kind": "video",
                "id": "canonical",
                "title": "Canonical",
                "webpage_url": canonical_url,
                "thumbnail": None,
                "entries": [],
            }

        def download(
            self,
            url,
            output_dir,
            format_id,
            subtitle_langs,
            write_auto_subs,
            prefer_srt,
            progress_hook,
            entry_ids,
        ):
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / "canonical.mp4"
            output_file.write_bytes(b"canonical")
            return output_file

    fake_service = CanonicalService()
    monkeypatch.setattr(main, "service", fake_service)
    client = TestClient(app)

    analyzed = client.post("/api/analyze", data={"url": original_url}).json()
    response = client.post(
        "/api/download",
        json={
            "url": analyzed["webpage_url"],
            "analysis_token": analyzed["analysis_token"],
            "format_id": "best",
            "entry_ids": [],
            "subtitle_langs": [],
            "write_auto_subs": False,
            "prefer_srt": True,
        },
    )

    assert response.status_code == 200
    assert fake_service.analyze_calls == [original_url]
