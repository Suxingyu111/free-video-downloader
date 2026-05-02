from __future__ import annotations

import subprocess
from pathlib import Path

from yt_dlp import YoutubeDL

from app.services.douyin_browser_service import is_douyin_url
from app.services.douyin_public_resolver import DouyinPublicResolver, is_douyin_public_only_enabled
from app.services.ytdlp_service import build_extractor_args, build_http_headers, is_youtube_url, prepare_url


YOUTUBE_AUDIO_FORMAT = "worstaudio[ext=m4a]/bestaudio[ext=m4a]/worstaudio/bestaudio/best[ext=mp4][height<=360]/best"
AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".webm", ".opus"}


class AudioExtractionService:
    def __init__(self, *, douyin_service: DouyinPublicResolver | None = None) -> None:
        self.douyin_service = douyin_service

    def extract_audio(self, url: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        prepared_url = prepare_url(url)
        if is_douyin_url(prepared_url) and is_douyin_public_only_enabled():
            return self._extract_douyin_public_audio(prepared_url, output_dir)

        before = set(output_dir.glob("*"))
        options = {
            "format": YOUTUBE_AUDIO_FORMAT if is_youtube_url(prepared_url) else "bestaudio/best",
            "outtmpl": str(output_dir / "%(title).120s-%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "http_headers": build_http_headers(prepared_url),
            "continuedl": True,
            "file_access_retries": 3,
            "fragment_retries": 10,
            "retries": 10,
            "extractor_retries": 5,
            "socket_timeout": 30,
            "source_address": "0.0.0.0",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "128",
                }
            ],
        }
        if is_youtube_url(prepared_url):
            options["http_chunk_size"] = 1024 * 1024
            options["js_runtimes"] = {"node": {}}
        extractor_args = build_extractor_args(prepared_url)
        if extractor_args:
            options["extractor_args"] = extractor_args
        with YoutubeDL(options) as ydl:
            ydl.download([prepared_url])

        candidates = [
            path
            for path in set(output_dir.glob("*")) - before
            if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
        ]
        if not candidates:
            candidates = [
                path
                for path in output_dir.glob("*")
                if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
            ]
        if not candidates:
            raise RuntimeError("无法提取视频音频，语音转写无法继续。请确认 ffmpeg 已安装并重试。")
        return max(candidates, key=lambda item: item.stat().st_mtime)

    def _extract_douyin_public_audio(self, prepared_url: str, output_dir: Path) -> Path:
        resolver = self.douyin_service or DouyinPublicResolver()
        media_path = resolver.download(
            url=prepared_url,
            output_dir=output_dir / "source",
            format_id="best",
        )
        if media_path.suffix.lower() in AUDIO_SUFFIXES:
            return media_path
        return extract_audio_from_media_file(media_path, output_dir)


def extract_audio_from_media_file(media_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / f"{media_path.stem}.m4a"
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(media_path),
        "-vn",
        "-acodec",
        "aac",
        "-b:a",
        "128k",
        str(audio_path),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg 未安装，无法从抖音公开视频提取音频。") from exc
    except subprocess.SubprocessError as exc:
        raise RuntimeError("抖音公开视频已解析，但音频提取失败。请确认视频包含可读取的音轨。") from exc
    if not audio_path.exists() or audio_path.stat().st_size <= 0:
        raise RuntimeError("抖音公开视频音频提取完成但未生成有效文件。")
    return audio_path
