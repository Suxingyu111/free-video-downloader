from pathlib import Path

import pytest

from app.services.ai_provider import (
    AIProviderConfig,
    AnthropicCompatibleProvider,
    MockAIProvider,
    OpenAICompatibleProvider,
    build_summary_prompt,
    build_ai_provider,
    normalize_summary_payload,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/chat/completions"):
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"overview":"概览","outline":[],"key_points":["A"],"highlights":[],"terms":[],"questions":[],"mind_map":{"title":"概览","children":[]},"qa_pairs":[{"question":"Q","answer":"A"}]}'
                            }
                        }
                    ]
                }
            )
        if url.endswith("/v1/messages"):
            return FakeResponse(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": '{"overview":"概览","outline":[],"key_points":["A"],"highlights":[],"terms":[],"questions":[],"mind_map":{"title":"概览","children":[]},"qa_pairs":[{"question":"Q","answer":"A"}]}',
                        }
                    ]
                }
            )
        return FakeResponse({"text": "转写文本"})


def test_openai_provider_requires_api_key_for_real_provider():
    config = AIProviderConfig(base_url="https://api.example.com/v1", api_key="", text_model="gpt", transcribe_model="whisper")

    with pytest.raises(RuntimeError, match="AI_API_KEY"):
        OpenAICompatibleProvider(config)


def test_openai_provider_shapes_chat_completion_request():
    client = FakeClient()
    provider = OpenAICompatibleProvider(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            text_model="summary-model",
            transcribe_model="speech-model",
        ),
        client=client,
    )

    result = provider.summarize_transcript(title="Demo", transcript="[00:01] hello", language="zh-CN")

    url, kwargs = client.calls[0]
    assert url == "https://api.example.com/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert kwargs["json"]["model"] == "summary-model"
    assert kwargs["json"]["response_format"] == {"type": "json_object"}
    assert result["overview"] == "概览"
    assert result["key_points"] == ["A"]
    assert result["mind_map"]["title"] == "概览"
    assert result["qa_pairs"] == [{"question": "Q", "answer": "A"}]


def test_openai_provider_shapes_audio_transcription_request(tmp_path: Path):
    client = FakeClient()
    provider = OpenAICompatibleProvider(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            text_model="summary-model",
            transcribe_model="speech-model",
        ),
        client=client,
    )
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")

    text = provider.transcribe_audio(audio, language="zh-CN")

    url, kwargs = client.calls[0]
    assert url == "https://api.example.com/v1/audio/transcriptions"
    assert kwargs["data"]["model"] == "speech-model"
    assert kwargs["data"]["language"] == "zh-CN"
    assert text == "转写文本"


def test_anthropic_provider_shapes_messages_request():
    client = FakeClient()
    provider = AnthropicCompatibleProvider(
        AIProviderConfig(
            base_url="https://api.deepseek.com/anthropic",
            api_key="secret",
            text_model="deepseek-v4-pro",
            transcribe_model="speech-model",
        ),
        client=client,
    )

    result = provider.summarize_transcript(title="Demo", transcript="[00:01] hello", language="zh-CN")

    url, kwargs = client.calls[0]
    assert url == "https://api.deepseek.com/anthropic/v1/messages"
    assert kwargs["headers"]["x-api-key"] == "secret"
    assert kwargs["headers"]["anthropic-version"]
    assert kwargs["json"]["model"] == "deepseek-v4-pro"
    assert kwargs["json"]["max_tokens"] == 4096
    assert kwargs["json"]["messages"][0]["content"][0]["type"] == "text"
    assert result["overview"] == "概览"
    assert result["key_points"] == ["A"]
    assert result["mind_map"]["title"] == "概览"
    assert result["qa_pairs"] == [{"question": "Q", "answer": "A"}]


def test_openai_provider_answers_question_with_transcript_context():
    client = FakeClient()
    provider = OpenAICompatibleProvider(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            text_model="summary-model",
            transcribe_model="speech-model",
        ),
        client=client,
    )

    answer = provider.answer_question(
        title="Demo",
        transcript="[00:01] hello",
        summary={"overview": "概览"},
        question="讲了什么？",
        language="zh-CN",
    )

    url, kwargs = client.calls[0]
    assert url == "https://api.example.com/v1/chat/completions"
    assert kwargs["json"]["model"] == "summary-model"
    assert "讲了什么？" in kwargs["json"]["messages"][1]["content"]
    assert answer


def test_anthropic_provider_answers_question_with_transcript_context():
    client = FakeClient()
    provider = AnthropicCompatibleProvider(
        AIProviderConfig(
            base_url="https://api.deepseek.com/anthropic",
            api_key="secret",
            text_model="deepseek-v4-pro",
            transcribe_model="speech-model",
        ),
        client=client,
    )

    answer = provider.answer_question(
        title="Demo",
        transcript="[00:01] hello",
        summary={"overview": "概览"},
        question="讲了什么？",
        language="zh-CN",
    )

    url, kwargs = client.calls[0]
    assert url == "https://api.deepseek.com/anthropic/v1/messages"
    assert kwargs["json"]["model"] == "deepseek-v4-pro"
    assert "讲了什么？" in kwargs["json"]["messages"][0]["content"][0]["text"]
    assert answer


def test_build_ai_provider_selects_openai_for_official_deepseek_config():
    provider = build_ai_provider(
        AIProviderConfig(
            provider="DeepSeek",
            base_url="https://api.deepseek.com",
            api_key="secret",
            text_model="deepseek-v4-pro",
            transcribe_model="speech-model",
        )
    )

    assert isinstance(provider, OpenAICompatibleProvider)


def test_build_ai_provider_selects_anthropic_for_anthropic_base_url():
    provider = build_ai_provider(
        AIProviderConfig(
            provider="DeepSeek",
            base_url="https://api.deepseek.com/anthropic",
            api_key="secret",
            text_model="deepseek-v4-pro",
            transcribe_model="speech-model",
        )
    )

    assert isinstance(provider, AnthropicCompatibleProvider)


def test_summary_prompt_requests_detailed_differentiated_mind_map():
    prompt = build_summary_prompt(title="学习视频", transcript="[00:00] 内容", language="zh-CN")

    assert "4-6 个一级分支" in prompt
    assert "每个一级分支至少 2 个子节点" in prompt
    assert "知识框架、内容脉络、方法步骤、案例证据、风险边界、行动建议" in prompt
    assert "避免使用“核心内容”“要点总结”这类泛化标题" in prompt


def test_normalize_summary_payload_enriches_sparse_mind_map():
    payload = {
        "overview": "视频讲解如何规划出海项目。",
        "outline": [
            {"time": "00:00", "title": "项目背景", "summary": "解释为什么选择出海方向。"},
            {"time": "01:20", "title": "执行路径", "summary": "拆解产品、获客和验证步骤。"},
        ],
        "key_points": ["先验证市场需求", "用小范围实验降低风险", "关注渠道和转化数据"],
        "highlights": [{"time": "02:10", "text": "用真实用户反馈决定下一步。"}],
        "terms": [{"term": "PMF", "explanation": "产品与目标市场匹配。"}],
        "questions": ["如何判断项目值得继续？"],
        "mind_map": {"title": "出海项目", "children": []},
    }

    result = normalize_summary_payload(payload)
    branches = result["mind_map"]["children"]

    assert result["mind_map"]["title"] == "出海项目"
    assert len(branches) >= 4
    assert {branch["title"] for branch in branches} >= {"内容脉络", "核心知识点", "关键证据", "术语概念"}
    assert all(branch["children"] for branch in branches[:4])


def test_mock_ai_provider_returns_deterministic_learning_summary(tmp_path: Path):
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")
    provider = MockAIProvider()

    assert "演示转写" in provider.transcribe_audio(audio, language="zh-CN")
    result = provider.summarize_transcript(title="AI 课程", transcript="第一章 模型", language="zh-CN")

    assert result["overview"].startswith("《AI 课程》")
    assert result["key_points"]
