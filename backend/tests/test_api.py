from fastapi.testclient import TestClient

from app import main
from app.main import app
from app.main import proxy_media_assets


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


def test_analyze_retries_transient_youtube_bot_check(monkeypatch):
    class FlakyService:
        def __init__(self):
            self.calls = 0

        def analyze(self, url, cookie_path=None):
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
