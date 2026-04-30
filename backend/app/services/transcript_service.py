from __future__ import annotations

import re
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from yt_dlp import YoutubeDL

from app.services.ytdlp_service import build_http_headers, prepare_url


TranscriptSource = Literal["subtitle", "auto_subtitle", "speech_to_text"]


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcript:
    source: TranscriptSource
    language: str
    segments: list[TranscriptSegment]


TIMESTAMP_PATTERN = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{3}|\d{1,2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{3}|\d{1,2}:\d{2}[,.]\d{3})"
)
TAG_PATTERN = re.compile(r"<[^>]+>")


def parse_timestamp(value: str) -> float:
    value = value.replace(",", ".")
    parts = value.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        hours = "0"
        minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def clean_caption_text(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    text = TAG_PATTERN.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_srt(content: str) -> list[TranscriptSegment]:
    blocks = re.split(r"\n\s*\n", content.strip())
    segments: list[TranscriptSegment] = []
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        timestamp_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if timestamp_index is None:
            continue
        match = TIMESTAMP_PATTERN.search(lines[timestamp_index])
        if not match:
            continue
        text = clean_caption_text(lines[timestamp_index + 1 :])
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=parse_timestamp(match.group("start")),
                end=parse_timestamp(match.group("end")),
                text=text,
            )
        )
    return segments


def parse_vtt(content: str) -> list[TranscriptSegment]:
    content = re.sub(r"^WEBVTT[^\n]*\n", "", content.strip())
    return parse_srt(content)


def parse_subtitle_file(path: Path) -> list[TranscriptSegment]:
    content = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".srt":
        return parse_srt(content)
    if path.suffix.lower() == ".vtt":
        return parse_vtt(content)
    return []


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    rest = total % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{rest:02d}"
    return f"{minutes:02d}:{rest:02d}"


def transcript_to_text(segments: list[TranscriptSegment]) -> str:
    return "\n".join(f"[{format_timestamp(segment.start)}] {segment.text}" for segment in segments)


class TranscriptService:
    def __init__(
        self,
        *,
        subtitle_languages: list[str] | None = None,
        cookie_file: str | Path | None = None,
        cookies_from_browser: str | tuple[str, str | None, str | None, str | None] | None = None,
    ) -> None:
        self.subtitle_languages = subtitle_languages or ["zh-CN", "zh-Hans", "zh-Hant", "zh", "zho", "cmn", "en", "en-US", "eng", "ja", "ko"]
        env_cookie_file = os.getenv("BILIBILI_COOKIE_FILE")
        env_cookies_from_browser = os.getenv("BILIBILI_COOKIES_FROM_BROWSER")
        self.cookie_file = Path(cookie_file or env_cookie_file) if (cookie_file or env_cookie_file) else None
        self.cookies_from_browser = parse_cookies_from_browser(cookies_from_browser or env_cookies_from_browser)

    def fetch_transcript(self, url: str, output_dir: Path) -> Transcript | None:
        output_dir.mkdir(parents=True, exist_ok=True)
        prepared_url = prepare_url(url)
        before = set(output_dir.glob("*"))
        options = build_transcript_ytdlp_options(
            prepared_url=prepared_url,
            output_dir=output_dir,
            subtitle_languages=self.subtitle_languages,
            cookie_file=self.cookie_file,
            cookies_from_browser=self.cookies_from_browser,
        )
        with YoutubeDL(options) as ydl:
            ydl.download([prepared_url])

        subtitle_files = [
            path
            for path in set(output_dir.glob("*")) - before
            if path.suffix.lower() in {".srt", ".vtt"}
        ]
        if not subtitle_files:
            subtitle_files = [path for path in output_dir.glob("*") if path.suffix.lower() in {".srt", ".vtt"}]
        for path in sorted(subtitle_files, key=_subtitle_priority):
            segments = parse_subtitle_file(path)
            if segments:
                return Transcript(source=_infer_source(path), language=_infer_language(path), segments=segments)
        return None


def parse_cookies_from_browser(
    value: str | tuple[str, str | None, str | None, str | None] | None,
) -> tuple[str, str | None, str | None, str | None] | None:
    if value is None or value == "":
        return None
    if isinstance(value, tuple):
        return value
    match = re.fullmatch(
        r"(?x)"
        r"(?P<name>[^+:]+)"
        r"(?:\s*\+\s*(?P<keyring>[^:]+))?"
        r"(?:\s*:\s*(?!:)(?P<profile>.+?))?"
        r"(?:\s*::\s*(?P<container>.+))?",
        value.strip(),
    )
    if match is None:
        raise RuntimeError("BILIBILI_COOKIES_FROM_BROWSER 格式错误，例如：chrome、chrome:Default 或 firefox:release::Personal。")
    browser_name, keyring, profile, container = match.group("name", "keyring", "profile", "container")
    return (browser_name.lower(), profile, keyring.upper() if keyring else None, container)


def build_transcript_ytdlp_options(
    *,
    prepared_url: str,
    output_dir: Path,
    subtitle_languages: list[str],
    cookie_file: str | Path | None = None,
    cookies_from_browser: tuple[str, str | None, str | None, str | None] | None = None,
) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": subtitle_languages,
        "subtitlesformat": "srt/vtt/best",
        "outtmpl": str(output_dir / "%(title).120s-%(id)s.%(ext)s"),
        "http_headers": build_http_headers(prepared_url),
    }
    if cookie_file:
        options["cookiefile"] = str(cookie_file)
    if cookies_from_browser:
        options["cookiesfrombrowser"] = cookies_from_browser
    return options


def _subtitle_priority(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    auto = 1 if ".auto." in name or ".automatic." in name else 0
    zh = 0 if ".zh" in name else 1
    return auto, zh, name


def _infer_source(path: Path) -> TranscriptSource:
    name = path.name.lower()
    return "auto_subtitle" if ".auto." in name or ".automatic." in name else "subtitle"


def _infer_language(path: Path) -> str:
    parts = path.name.split(".")
    if len(parts) >= 3:
        return parts[-2]
    return "unknown"
