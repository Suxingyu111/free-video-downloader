import json

from app.services.geo_monitor import build_geo_access_record
from app.services.geo_monitor import classify_crawler
from app.services.geo_monitor import is_geo_surface_path
from app.services.geo_monitor import should_log_geo_access
from app.services.geo_monitor import summarize_geo_access


def test_geo_monitor_classifies_ai_crawlers_and_surfaces():
    assert classify_crawler("Mozilla/5.0 AppleWebKit OAI-SearchBot") == "openai-search"
    assert classify_crawler("Claude-SearchBot") == "anthropic-search"
    assert classify_crawler("regular browser") is None

    assert is_geo_surface_path("/llms.txt")
    assert is_geo_surface_path("/video-summary/index.html.md")
    assert is_geo_surface_path("/facts/")
    assert is_geo_surface_path("/.well-known/ai.json")
    assert is_geo_surface_path("/features/")
    assert is_geo_surface_path("/platforms/youtube/")
    assert is_geo_surface_path("/use-cases/course-learning/index.html.md")
    assert is_geo_surface_path("/pricing/")
    assert not is_geo_surface_path("/api/health")


def test_geo_monitor_logs_only_safe_geo_or_crawler_events():
    assert should_log_geo_access("GET", "/llms.txt", 200, "regular browser")
    assert should_log_geo_access("GET", "/api/health", 200, "OAI-SearchBot")
    assert should_log_geo_access("GET", "/missing-page", 404, "regular browser")
    assert not should_log_geo_access("POST", "/api/analyze", 400, "regular browser")
    assert not should_log_geo_access("GET", "/api/missing", 404, "regular browser")


def test_geo_monitor_records_no_query_or_ip_data():
    record = build_geo_access_record("get", "/facts/", 200, "PerplexityBot")
    encoded = json.dumps(record, ensure_ascii=False)

    assert record["method"] == "GET"
    assert record["path"] == "/facts/"
    assert record["crawler"] == "perplexity-search"
    assert "ip" not in record
    assert "query" not in encoded.lower()


def test_geo_monitor_summary_counts_paths_crawlers_and_404s():
    summary = summarize_geo_access(
        [
            {"path": "/llms.txt", "crawler": "openai-search", "status": 200},
            {"path": "/llms.txt", "crawler": "openai-search", "status": 200},
            {"path": "/missing", "crawler": None, "status": 404},
        ]
    )

    assert summary["total"] == 3
    assert summary["by_path"]["/llms.txt"] == 2
    assert summary["by_crawler"]["openai-search"] == 2
    assert summary["not_found_paths"]["/missing"] == 1
