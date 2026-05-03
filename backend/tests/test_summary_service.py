from pathlib import Path

from app.services import summary_service as summary_service_module
from app.services.summary_service import SummaryService, render_markdown
from app.services.transcript_service import Transcript, TranscriptSegment


class FakeTranscriptService:
    def __init__(self, transcript=None):
        self.transcript = transcript
        self.calls = []

    def fetch_transcript(self, url: str, output_dir: Path):
        self.calls.append((url, output_dir))
        return self.transcript


class FakeAudioService:
    def __init__(self, output: Path):
        self.output = output
        self.calls = []

    def extract_audio(self, url: str, output_dir: Path):
        self.calls.append((url, output_dir))
        self.output.write_bytes(b"audio")
        return self.output


class FailingTranscriptService:
    def fetch_transcript(self, url: str, output_dir: Path):
        raise AssertionError("summary should reuse analyzed subtitle URLs instead of extracting subtitles again")


class FakeSubtitleResponse:
    text = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n直接使用分析阶段的字幕\n\n00:00:04.000 --> 00:00:06.000\n马上进入 AI 大模型总结\n"

    def raise_for_status(self):
        return None


class FakeSubtitleHttpx:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeSubtitleResponse()


class FakeAIProvider:
    def __init__(self):
        self.transcribed = []
        self.summarized = []

    def transcribe_audio(self, audio_path: Path, language: str) -> str:
        self.transcribed.append((audio_path, language))
        return "[00:00] 语音转写内容"

    def summarize_transcript(self, *, title: str, transcript: str, language: str, stream_hook=None) -> dict:
        self.summarized.append((title, transcript, language))
        return {
            "overview": "课程概览",
            "outline": [{"time": "00:00", "title": "开场", "summary": "介绍主题"}],
            "key_points": ["核心观点"],
            "highlights": [{"time": "00:01", "text": "重要片段"}],
            "terms": [{"term": "模型", "explanation": "从数据中学习规律"}],
            "questions": ["如何实践？"],
            "mind_map": {
                "title": "课程概览",
                "children": [{"title": "开场", "children": [{"title": "介绍主题"}]}],
            },
            "qa_pairs": [{"question": "如何实践？", "answer": "先复盘章节，再选择重点回看。"}],
        }

    def answer_question(self, *, title: str, transcript: str, summary: dict, question: str, language: str) -> str:
        return f"基于《{title}》回答：{question}"


def test_render_markdown_outputs_learning_note_sections():
    markdown = render_markdown(
        {
            "readable_summary": "一句话结论：这是一份流式可读总结。\n核心要点：\n- 用户先看到最终总结。",
            "overview": "课程概览",
            "topic": "AI 课程总结",
            "audience": "想快速复盘视频内容的学习者",
            "main_thread": ["先交代课程主题", "再拆解核心观点", "最后给出实践方向"],
            "examples": [{"time": "00:01", "text": "用重要片段解释模型学习规律"}],
            "action_items": ["回看开场章节", "整理自己的实践问题"],
            "limitations": ["字幕没有展开模型训练细节"],
            "outline": [{"time": "00:00", "title": "开场", "summary": "介绍主题"}],
            "key_points": ["核心观点"],
            "highlights": [{"time": "00:01", "text": "重要片段"}],
            "terms": [{"term": "模型", "explanation": "从数据中学习规律"}],
            "questions": ["如何实践？"],
            "transcript_source": "subtitle",
        },
        title="AI 课程",
    )

    assert "# AI 课程" in markdown
    assert "| 项目 | 内容 |" in markdown
    assert "## 快速导读" in markdown
    assert "### 流式可读总结" in markdown
    assert "一句话结论：这是一份流式可读总结。" in markdown
    assert "### 一句话概览" in markdown
    assert "## 完整理解" in markdown
    assert "| 主题 | AI 课程总结 |" in markdown
    assert "### 主线脉络" in markdown
    assert "- 先交代课程主题" in markdown
    assert "### 例子和证据" in markdown
    assert "| 00:01 | 用重要片段解释模型学习规律 |" in markdown
    assert "### 行动清单" in markdown
    assert "- 整理自己的实践问题" in markdown
    assert "### 边界和限制" in markdown
    assert "- 字幕没有展开模型训练细节" in markdown
    assert "1. [00:00] **开场**：介绍主题" in markdown
    assert "- 核心观点" in markdown
    assert "| 模型 | 从数据中学习规律 |" in markdown
    assert "## 思维导图" in markdown
    assert "## AI 问答" in markdown
    assert "<details>" in markdown


def test_summary_service_uses_analyzed_subtitle_url_without_extracting_subtitles(tmp_path: Path, monkeypatch):
    httpx = FakeSubtitleHttpx()
    monkeypatch.setattr(summary_service_module, "httpx", httpx, raising=False)
    ai = FakeAIProvider()
    service = SummaryService(
        transcript_service=FailingTranscriptService(),
        ai_provider=ai,
    )

    result, markdown_path = service.generate_summary(
        url="https://example.com/video",
        title="AI 课程",
        language="zh-CN",
        output_dir=tmp_path,
        seed_result={
            "subtitles": [
                {"lang": "zh-CN", "ext": "vtt", "url": "https://example.com/caption.vtt", "automatic": False}
            ]
        },
    )

    assert httpx.calls[0][0] == "https://example.com/caption.vtt"
    assert "直接使用分析阶段的字幕" in ai.summarized[0][1]
    assert "马上进入 AI 大模型总结" in ai.summarized[0][1]
    assert result["transcript_source"] == "subtitle"
    assert result["transcript_segments"][0]["text"] == "直接使用分析阶段的字幕"
    assert markdown_path.exists()


def test_summary_service_skips_subtitle_extraction_when_analyzed_subtitles_are_not_direct(tmp_path: Path):
    ai = FakeAIProvider()
    audio = FakeAudioService(tmp_path / "audio.m4a")
    service = SummaryService(
        transcript_service=FailingTranscriptService(),
        audio_service=audio,
        ai_provider=ai,
    )
    events = []

    result, markdown_path = service.generate_summary(
        url="https://example.com/video",
        title="AI 课程",
        language="zh-CN",
        output_dir=tmp_path,
        seed_result={"subtitles": [{"lang": "zh-CN", "ext": "vtt", "automatic": False}]},
        progress_hook=lambda stage, progress, message, **changes: events.append((stage, progress, message, changes)),
    )

    assert audio.calls == [("https://example.com/video", tmp_path / "audio")]
    assert ai.transcribed == [(tmp_path / "audio.m4a", "zh-CN")]
    assert ai.summarized[0][1] == "[00:00] 语音转写内容"
    assert result["transcript_source"] == "speech_to_text"
    assert markdown_path.exists()
    assert any("Skipping slow subtitle extraction" in event[2] for event in events)
    assert not any("Extracting subtitles" in event[2] for event in events)


def test_summary_service_uses_subtitle_transcript_before_speech_to_text(tmp_path: Path):
    transcript = Transcript(
        source="subtitle",
        language="zh-CN",
        segments=[TranscriptSegment(start=1, end=4, text="字幕内容")],
    )
    ai = FakeAIProvider()
    audio = FakeAudioService(tmp_path / "audio.m4a")
    service = SummaryService(
        transcript_service=FakeTranscriptService(transcript),
        audio_service=audio,
        ai_provider=ai,
    )

    result, markdown_path = service.generate_summary(
        url="https://example.com/video",
        title="AI 课程",
        language="zh-CN",
        output_dir=tmp_path,
    )

    assert ai.transcribed == []
    assert audio.calls == []
    assert ai.summarized[0][1] == "[00:01] 字幕内容"
    assert result["transcript_source"] == "subtitle"
    assert result["transcript_segments"] == [
        {"start": 1, "end": 4, "time": "00:01", "text": "字幕内容"}
    ]
    assert result["mind_map"]["title"] == "AI 课程"
    assert result["qa_pairs"][0]["answer"] == "先复盘章节，再选择重点回看。"
    assert markdown_path.exists()


def test_summary_service_reuses_seed_transcript_before_fetching_media(tmp_path: Path):
    ai = FakeAIProvider()
    audio = FakeAudioService(tmp_path / "audio.m4a")
    transcript_service = FakeTranscriptService(None)
    service = SummaryService(
        transcript_service=transcript_service,
        audio_service=audio,
        ai_provider=ai,
    )

    result, markdown_path = service.generate_summary(
        url="https://www.youtube.com/watch?v=DXVHmGoCTco",
        title="AI 课程",
        language="zh-CN",
        output_dir=tmp_path,
        seed_result={
            "transcript_source": "subtitle",
            "transcript_language": "zh-Hans",
            "transcript_segments": [{"start": 3, "end": 6, "time": "00:03", "text": "已有字幕内容"}],
        },
    )

    assert transcript_service.calls == []
    assert audio.calls == []
    assert ai.transcribed == []
    assert ai.summarized[0][1] == "[00:03] 已有字幕内容"
    assert result["transcript_language"] == "zh-Hans"
    assert markdown_path.exists()


def test_summary_service_streams_only_ai_provider_final_preview(tmp_path: Path):
    class StreamingAIProvider(FakeAIProvider):
        def summarize_transcript(self, *, title: str, transcript: str, language: str, stream_hook=None) -> dict:
            if stream_hook:
                stream_hook("一句话概览：最终总结正在逐行输出\n核心知识点：真实模型流式要点")
            return super().summarize_transcript(
                title=title,
                transcript=transcript,
                language=language,
                stream_hook=stream_hook,
            )

    transcript = Transcript(
        source="subtitle",
        language="zh-CN",
        segments=[
            TranscriptSegment(start=0, end=20, text="主讲人说明 AI 总结需要边生成边展示。"),
            TranscriptSegment(start=40, end=70, text="系统先让用户看到概览，再逐步补充章节和要点。"),
        ],
    )
    service = SummaryService(
        transcript_service=FakeTranscriptService(transcript),
        ai_provider=StreamingAIProvider(),
    )
    events = []

    service.generate_summary(
        url="https://example.com/video",
        title="AI 课程",
        language="zh-CN",
        output_dir=tmp_path,
        progress_hook=lambda stage, progress, message, **changes: events.append((stage, progress, message, changes)),
    )

    streamed_updates = [event for event in events if event[3].get("streamed_text")]
    assert streamed_updates
    assert all(not event[3].get("draft_result") for event in events)
    assert any("Streaming readable summary" in event[2] for event in streamed_updates)
    assert any("真实模型流式要点" in event[3]["streamed_text"] for event in streamed_updates)
    assert not any("快速版" in event[2] for event in events)


def test_summary_service_falls_back_to_speech_to_text_without_subtitles(tmp_path: Path):
    ai = FakeAIProvider()
    audio = FakeAudioService(tmp_path / "audio.m4a")
    service = SummaryService(
        transcript_service=FakeTranscriptService(None),
        audio_service=audio,
        ai_provider=ai,
    )

    result, markdown_path = service.generate_summary(
        url="https://example.com/video",
        title="AI 课程",
        language="zh-CN",
        output_dir=tmp_path,
    )

    assert audio.calls == [("https://example.com/video", tmp_path / "audio")]
    assert ai.transcribed == [(tmp_path / "audio.m4a", "zh-CN")]
    assert ai.summarized[0][1] == "[00:00] 语音转写内容"
    assert result["transcript_source"] == "speech_to_text"
    assert result["transcript_segments"] == [
        {"start": 0.0, "end": 30.0, "time": "00:00", "text": "语音转写内容"}
    ]
    assert markdown_path.exists()
    assert "| 转写来源 | 语音转写 |" in markdown_path.read_text(encoding="utf-8")


def test_summary_service_transcribes_full_audio_without_preview_draft(tmp_path: Path, monkeypatch):
    class FullAudioProvider(FakeAIProvider):
        def transcribe_audio(self, audio_path: Path, language: str) -> str:
            self.transcribed.append((audio_path, language))
            assert audio_path.name != "preview.wav"
            return "[00:00] 完整转写包含开头\n[02:00] 完整转写覆盖中段\n[04:00] 完整转写覆盖结尾"

    ai = FullAudioProvider()
    audio = FakeAudioService(tmp_path / "audio.m4a")
    service = SummaryService(
        transcript_service=FakeTranscriptService(None),
        audio_service=audio,
        ai_provider=ai,
    )
    events = []

    def fail_if_preview_requested(*_args, **_kwargs):
        raise AssertionError("summary should not create preview draft before final AI summary")

    monkeypatch.setattr("app.services.summary_service.create_audio_preview_clip", fail_if_preview_requested)

    result, _ = service.generate_summary(
        url="https://example.com/video",
        title="AI 课程",
        language="zh-CN",
        output_dir=tmp_path,
        progress_hook=lambda stage, progress, message, **changes: events.append((stage, progress, message, changes)),
    )

    assert ai.transcribed == [(tmp_path / "audio.m4a", "zh-CN")]
    assert all(not event[3].get("draft_result") for event in events)
    assert result["transcript_text"].endswith("完整转写覆盖结尾")


def test_summary_service_falls_back_to_speech_to_text_when_bilibili_subtitles_need_login(tmp_path: Path, monkeypatch):
    ai = FakeAIProvider()
    audio = FakeAudioService(tmp_path / "audio.m4a")
    service = SummaryService(
        transcript_service=FakeTranscriptService(None),
        audio_service=audio,
        ai_provider=ai,
    )
    monkeypatch.setattr(
        "app.services.summary_service.describe_bilibili_transcript_unavailable",
        lambda url: "Bilibili 字幕需要登录态。",
    )
    events = []

    result, markdown_path = service.generate_summary(
        url="https://www.bilibili.com/video/BV1mAAmzqEfP/",
        title="AI 课程",
        language="zh-CN",
        output_dir=tmp_path,
        progress_hook=lambda stage, progress, message, **changes: events.append((stage, progress, message, changes)),
    )

    assert audio.calls == [("https://www.bilibili.com/video/BV1mAAmzqEfP/", tmp_path / "audio")]
    assert ai.transcribed == [(tmp_path / "audio.m4a", "zh-CN")]
    assert ai.summarized[0][1] == "[00:00] 语音转写内容"
    assert result["transcript_source"] == "speech_to_text"
    assert any("Bilibili 字幕需要登录态" in event[2] for event in events)
    assert markdown_path.exists()


def test_summary_service_answers_questions_from_existing_summary(tmp_path: Path):
    transcript = Transcript(
        source="subtitle",
        language="zh-CN",
        segments=[TranscriptSegment(start=1, end=4, text="字幕内容")],
    )
    ai = FakeAIProvider()
    service = SummaryService(
        transcript_service=FakeTranscriptService(transcript),
        ai_provider=ai,
    )
    result, _ = service.generate_summary(
        url="https://example.com/video",
        title="AI 课程",
        language="zh-CN",
        output_dir=tmp_path,
    )

    answer = service.answer_question(
        title="AI 课程",
        transcript=result["transcript_text"],
        summary=result,
        question="如何学习？",
        language="zh-CN",
    )

    assert answer == "基于《AI 课程》回答：如何学习？"


def test_summary_service_enriches_sparse_ai_summary_with_transcript(tmp_path: Path):
    class SparseAIProvider(FakeAIProvider):
        def summarize_transcript(self, *, title: str, transcript: str, language: str, stream_hook=None) -> dict:
            self.summarized.append((title, transcript, language))
            return {
                "overview": "本视频介绍核心内容。",
                "outline": [],
                "key_points": ["核心内容"],
                "highlights": [],
                "terms": [],
                "questions": [],
                "mind_map": {"title": "核心内容", "children": []},
                "qa_pairs": [],
            }

    transcript = Transcript(
        source="subtitle",
        language="zh-CN",
        segments=[
            TranscriptSegment(start=0, end=20, text="主讲人复盘 YouTube 频道增长，指出完播率连续两周下滑。"),
            TranscriptSegment(start=80, end=120, text="团队把选题从泛娱乐调整为 AI 工具教程，并记录标题点击率。"),
            TranscriptSegment(start=160, end=210, text="关键风险是样本量太小，不能只看单条视频的数据。"),
        ],
    )
    service = SummaryService(
        transcript_service=FakeTranscriptService(transcript),
        ai_provider=SparseAIProvider(),
    )

    result, _ = service.generate_summary(
        url="https://example.com/video",
        title="YouTube 增长复盘",
        language="zh-CN",
        output_dir=tmp_path,
    )

    assert "YouTube 增长复盘" in result["overview"]
    assert len(result["outline"]) >= 3
    assert all(point != "核心内容" for point in result["key_points"])
    assert any("点击率" in point or "完播率" in point for point in result["key_points"])
    assert len(result["mind_map"]["children"]) >= 4
