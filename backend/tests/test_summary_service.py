from pathlib import Path

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
            "overview": "课程概览",
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
    assert "## 一句话概览" in markdown
    assert "- [00:00] **开场**：介绍主题" in markdown
    assert "- 核心观点" in markdown
    assert "- **模型**：从数据中学习规律" in markdown
    assert "## 思维导图" in markdown
    assert "## AI 问答" in markdown


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


def test_summary_service_emits_grounded_draft_and_stream_preview(tmp_path: Path):
    class StreamingAIProvider(FakeAIProvider):
        def summarize_transcript(self, *, title: str, transcript: str, language: str, stream_hook=None) -> dict:
            if stream_hook:
                stream_hook("一句话概览：AI 正在逐行输出总结\n核心知识点：实时生成的要点")
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
    assert any("基于字幕" in event[2] for event in streamed_updates)
    assert any("实时生成的要点" in event[3]["streamed_text"] for event in streamed_updates)


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
