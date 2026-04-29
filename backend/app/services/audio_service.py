from __future__ import annotations

from pathlib import Path

from yt_dlp import YoutubeDL

from app.services.ytdlp_service import build_http_headers, is_youtube_url, prepare_url


YOUTUBE_AUDIO_FORMAT = "worstaudio[ext=m4a]/bestaudio[ext=m4a]/worstaudio/bestaudio/best[ext=mp4][height<=360]/best"


class AudioExtractionService:
    def extract_audio(self, url: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        prepared_url = prepare_url(url)
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
        with YoutubeDL(options) as ydl:
            ydl.download([prepared_url])

        candidates = [
            path
            for path in set(output_dir.glob("*")) - before
            if path.is_file() and path.suffix.lower() in {".m4a", ".mp3", ".wav", ".webm", ".opus"}
        ]
        if not candidates:
            candidates = [
                path
                for path in output_dir.glob("*")
                if path.is_file() and path.suffix.lower() in {".m4a", ".mp3", ".wav", ".webm", ".opus"}
            ]
        if not candidates:
            raise RuntimeError("无法提取视频音频，语音转写无法继续。请确认 ffmpeg 已安装并重试。")
        return max(candidates, key=lambda item: item.stat().st_mtime)
