from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


AI_CRAWLER_PATTERNS = {
    "OAI-SearchBot": "openai-search",
    "ChatGPT-User": "openai-user",
    "Claude-SearchBot": "anthropic-search",
    "Claude-User": "anthropic-user",
    "PerplexityBot": "perplexity-search",
    "Perplexity-User": "perplexity-user",
    "Googlebot": "googlebot",
    "Bingbot": "bingbot",
    "GPTBot": "openai-training",
    "ClaudeBot": "anthropic-training",
    "CCBot": "common-crawl",
}

GEO_ROOT_PATHS = {
    "/",
    "/robots.txt",
    "/sitemap.xml",
    "/llms.txt",
    "/llms-full.txt",
    "/.well-known/ai.json",
    "/index.html.md",
    "/sitemap/",
}

GEO_PAGE_PREFIXES = {
    "/video-summary/",
    "/youtube-video-downloader/",
    "/bilibili-video-downloader/",
    "/douyin-video-downloader/",
    "/tiktok-video-downloader/",
    "/subtitle-extractor/",
    "/facts/",
    "/how-to-video-summary/",
    "/how-to-extract-bilibili-subtitles/",
    "/public-video-to-mind-map/",
    "/public-video-archive-workflow/",
    "/saveany-vs-online-video-downloader/",
    "/ai-video-summary-tool-comparison/",
    "/youtube-video-summary-tool/",
    "/bilibili-course-summary-tool/",
    "/youtube-to-mp4/",
    "/youtube-subtitle-downloader/",
    "/bilibili-course-downloader/",
    "/douyin-public-video-download/",
    "/video-to-text/",
    "/video-to-mindmap/",
    "/ai-video-notes/",
    "/online-video-downloader/",
    "/features/",
    "/features/video-download/",
    "/features/ai-video-summary/",
    "/features/subtitle-extraction/",
    "/features/mind-map/",
    "/articles/",
    "/platforms/",
    "/platforms/youtube/",
    "/platforms/bilibili/",
    "/platforms/douyin/",
    "/platforms/tiktok/",
    "/use-cases/",
    "/use-cases/course-learning/",
    "/use-cases/content-archive/",
    "/use-cases/meeting-review/",
    "/compare/",
    "/pricing/",
    "/faq/",
    "/privacy/",
    "/terms/",
}


def classify_crawler(user_agent: str | None) -> str | None:
    value = user_agent or ""
    for pattern, family in AI_CRAWLER_PATTERNS.items():
        if pattern.lower() in value.lower():
            return family
    return None


def is_geo_surface_path(path: str) -> bool:
    normalized = path if path.startswith("/") else f"/{path}"
    if normalized in GEO_ROOT_PATHS:
        return True
    return any(normalized == prefix or normalized.startswith(prefix) for prefix in GEO_PAGE_PREFIXES)


def is_private_runtime_path(path: str) -> bool:
    normalized = path if path.startswith("/") else f"/{path}"
    return normalized in {"/api", "/files"} or normalized.startswith(("/api/", "/files/"))


def should_log_geo_access(method: str, path: str, status_code: int, user_agent: str | None) -> bool:
    normalized_method = method.upper()
    if normalized_method not in {"GET", "HEAD"}:
        return False
    if is_private_runtime_path(path):
        return False
    if classify_crawler(user_agent):
        return True
    if is_geo_surface_path(path):
        return True
    if status_code == 404 and not path.startswith(("/api/", "/files/")):
        return True
    return False


def build_geo_access_record(method: str, path: str, status_code: int, user_agent: str | None) -> dict:
    crawler = classify_crawler(user_agent)
    return {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "method": method.upper(),
        "path": path,
        "status": status_code,
        "crawler": crawler,
        "surface": "geo" if is_geo_surface_path(path) else "other",
    }


def append_geo_access_log(log_file: Path, record: dict) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        file.write("\n")


def read_geo_access_records(log_file: Path) -> list[dict]:
    if not log_file.exists():
        return []
    records = []
    with log_file.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def summarize_geo_access(records: Iterable[dict]) -> dict:
    by_path = Counter()
    by_crawler = Counter()
    status_counts = Counter()
    not_found_paths = Counter()

    for record in records:
        path = str(record.get("path") or "")
        crawler = record.get("crawler") or "human-or-unknown"
        status = int(record.get("status") or 0)
        by_path[path] += 1
        by_crawler[crawler] += 1
        status_counts[str(status)] += 1
        if status == 404 and path:
            not_found_paths[path] += 1

    return {
        "total": sum(by_path.values()),
        "by_path": dict(by_path.most_common(30)),
        "by_crawler": dict(by_crawler.most_common()),
        "status": dict(status_counts.most_common()),
        "not_found_paths": dict(not_found_paths.most_common(30)),
    }
