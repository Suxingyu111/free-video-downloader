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

    def summarize_transcript(self, *, title: str, transcript: str, language: str) -> dict:
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
    assert result["mind_map"]["title"] == "课程概览"
    assert result["qa_pairs"][0]["answer"] == "先复盘章节，再选择重点回看。"
    assert markdown_path.exists()


def test_summary_service_fails_without_subtitles_and_never_transcribes_audio(tmp_path: Path):
    ai = FakeAIProvider()
    audio = FakeAudioService(tmp_path / "audio.m4a")
    service = SummaryService(
        transcript_service=FakeTranscriptService(None),
        audio_service=audio,
        ai_provider=ai,
    )

    try:
        service.generate_summary(
            url="https://example.com/video",
            title="AI 课程",
            language="zh-CN",
            output_dir=tmp_path,
        )
    except RuntimeError as exc:
        assert "没有可用字幕" in str(exc)
    else:
        raise AssertionError("无字幕视频不应进入 AI 总结流程")

    assert audio.calls == []
    assert ai.transcribed == []
    assert ai.summarized == []


def test_summary_service_surfaces_bilibili_login_required_subtitle_reason(tmp_path: Path, monkeypatch):
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

    try:
        service.generate_summary(
            url="https://www.bilibili.com/video/BV1mAAmzqEfP/",
            title="AI 课程",
            language="zh-CN",
            output_dir=tmp_path,
        )
    except RuntimeError as exc:
        assert "Bilibili 字幕需要登录态" in str(exc)
    else:
        raise AssertionError("Bilibili 登录态受限字幕应返回明确原因")

    assert audio.calls == []
    assert ai.transcribed == []
    assert ai.summarized == []


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
