from pathlib import Path
import json

import httpx
import pytest

from app.services.ai_provider import (
    AIProviderConfig,
    AnthropicCompatibleProvider,
    MockAIProvider,
    OpenAICompatibleProvider,
    READABLE_SUMMARY_RESPONSE_MAX_TOKENS,
    SUMMARY_RESPONSE_MAX_TOKENS,
    SUMMARY_TRANSCRIPT_CHAR_BUDGET,
    build_stream_preview_from_summary_text,
    build_readable_summary_prompt,
    build_summary_prompt,
    build_ai_provider,
    compact_transcript_for_prompt,
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
    def __init__(self, *, summary_content=None):
        self.calls = []
        self.summary_content = summary_content or (
            '{"overview":"概览","outline":[],"key_points":["A"],"highlights":[],"terms":[],"questions":[],"mind_map":{"title":"概览","children":[]},"qa_pairs":[{"question":"Q","answer":"A"}]}'
        )

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/chat/completions"):
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": self.summary_content
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
                            "text": self.summary_content,
                        }
                    ]
                }
            )
        return FakeResponse({"text": "转写文本"})


class TimeoutClient:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        raise httpx.TimeoutException("too slow")


class FakeStreamResponse:
    def __init__(self, chunks):
        self.chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        for chunk in self.chunks:
            yield f'data: {{"choices":[{{"delta":{{"content":{json.dumps(chunk, ensure_ascii=False)}}}}}]}}'
        yield "data: [DONE]"


class FakeStreamingClient(FakeClient):
    def __init__(self, *, chunks, summary_content=None):
        super().__init__(summary_content=summary_content or "".join(chunks))
        self.stream_calls = []
        self.chunks = chunks

    def stream(self, method, url, **kwargs):
        self.stream_calls.append((method, url, kwargs))
        return FakeStreamResponse(self.chunks)


class FakeAnthropicStreamResponse(FakeStreamResponse):
    def iter_lines(self):
        yield 'event: message_start'
        for chunk in self.chunks:
            yield (
                'data: '
                + json.dumps(
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": chunk},
                    },
                    ensure_ascii=False,
                )
            )
        yield 'event: message_stop'


class FakeAnthropicStreamingClient(FakeClient):
    def __init__(self, *, chunks, summary_content=None):
        super().__init__(summary_content=summary_content or "".join(chunks))
        self.stream_calls = []
        self.chunks = chunks

    def stream(self, method, url, **kwargs):
        self.stream_calls.append((method, url, kwargs))
        return FakeAnthropicStreamResponse(self.chunks)


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
    assert kwargs["json"]["max_tokens"] >= 12_000
    assert result["overview"] == "概览"
    assert result["key_points"] == ["A"]
    assert result["mind_map"]["title"] == "Demo"
    assert result["qa_pairs"] == [{"question": "Q", "answer": "A"}]


def test_openai_provider_streams_readable_summary_then_builds_structured_json():
    structured_content = (
        '{"overview":"这是一段后台结构化增强后的概览，说明视频主题、关键步骤和最终结论。",'
        '"outline":[{"time":"00:00","title":"开场","summary":"介绍视频主题和学习目标。"}],'
        '"key_points":["第一条核心知识点","第二条核心知识点"],'
        '"highlights":[],"terms":[],"questions":[],"mind_map":{"title":"演示","children":[]},"qa_pairs":[]}'
    )
    readable_chunks = [
        "一句话结论：这是一段直接给用户看的最终总结。",
        "\n核心要点：\n- 用户会先看到可读总结，而不是 JSON 字段。\n- 后台继续补齐章节和问答。",
        "\n章节时间轴：\n- [00:00] 开场：介绍视频主题和学习目标。",
    ]
    client = FakeStreamingClient(chunks=readable_chunks, summary_content=structured_content)
    provider = OpenAICompatibleProvider(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            text_model="summary-model",
            transcribe_model="speech-model",
        ),
        client=client,
    )
    previews = []

    result = provider.summarize_transcript(
        title="Demo",
        transcript="[00:01] hello",
        language="zh-CN",
        stream_hook=previews.append,
    )

    method, url, kwargs = client.stream_calls[0]
    assert method == "POST"
    assert url == "https://api.example.com/v1/chat/completions"
    assert kwargs["json"]["stream"] is True
    assert "response_format" not in kwargs["json"]
    assert "禁止输出 JSON" in kwargs["json"]["messages"][0]["content"]
    structured_url, structured_kwargs = client.calls[0]
    assert structured_url == "https://api.example.com/v1/chat/completions"
    assert structured_kwargs["json"]["response_format"] == {"type": "json_object"}
    assert "已有可读总结" in structured_kwargs["json"]["messages"][1]["content"]
    assert result["overview"].startswith("这是一段后台结构化增强")
    assert result["readable_summary"].startswith("一句话结论")
    assert any("一句话结论" in preview and "最终总结" in preview for preview in previews)
    assert any("后台继续补齐章节和问答" in preview for preview in previews)
    assert not any("{" in preview or "overview" in preview for preview in previews)


def test_openai_provider_falls_back_when_streaming_summary_exceeds_total_timeout(monkeypatch):
    summary_content = (
        '{"overview":"这是一段很慢的流式总结，模型长时间没有完成 JSON。",'
        '"outline":[{"time":"00:00","title":"开场","summary":"介绍主题。"}],'
        '"key_points":["第一条"],"highlights":[],"terms":[],"questions":[],"mind_map":{"title":"演示","children":[]},"qa_pairs":[]}'
    )
    client = FakeStreamingClient(chunks=[summary_content[:40], summary_content[40:80], summary_content[80:120]])
    provider = OpenAICompatibleProvider(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            text_model="summary-model",
            transcribe_model="speech-model",
            timeout_seconds=120,
        ),
        client=client,
    )
    ticks = iter([0, 10, 125, 126])
    monkeypatch.setattr("app.services.ai_provider.monotonic", lambda: next(ticks, 52))

    result = provider.summarize_transcript(
        title="Demo",
        transcript="[00:00] 开场介绍主题\n[01:00] 解释关键步骤\n[02:00] 总结行动建议",
        language="zh-CN",
        stream_hook=lambda _preview: None,
    )

    assert "超过 120 秒" in result["overview"]
    assert result["outline"]


def test_build_stream_preview_from_summary_text_removes_json_scaffolding():
    preview = build_stream_preview_from_summary_text(
        '{"overview":"视频说明如何边生成边展示摘要。","key_points":["用户先看到概览","随后看到要点"]}',
        title="Demo",
        transcript="[00:00] 视频说明如何边生成边展示摘要。",
    )

    assert "overview" not in preview
    assert "{" not in preview
    assert "一句话概览：视频说明如何边生成边展示摘要。" in preview
    assert "- 用户先看到概览" in preview


def test_openai_provider_repairs_literal_newlines_inside_json_strings():
    client = FakeClient(
        summary_content='{"overview":"第一行\n第二行","outline":[],"key_points":["A"],"highlights":[],"terms":[],"questions":[],"mind_map":{"title":"概览","children":[]},"qa_pairs":[]}'
    )
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

    assert result["overview"] == "第一行\n第二行"
    assert result["key_points"] == ["A"]


def test_openai_provider_falls_back_when_summary_json_is_truncated():
    client = FakeClient(summary_content='{"overview":"还没写完')
    provider = OpenAICompatibleProvider(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            text_model="summary-model",
            transcribe_model="speech-model",
        ),
        client=client,
    )

    result = provider.summarize_transcript(
        title="Demo",
        transcript="[00:00] 开场介绍主题\n[01:00] 解释关键步骤\n[02:00] 总结行动建议",
        language="zh-CN",
    )

    assert "快速摘要" in result["overview"]
    assert result["outline"]
    assert result["key_points"]


def test_openai_provider_uses_configured_timeout_when_summary_request_times_out():
    client = TimeoutClient()
    provider = OpenAICompatibleProvider(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            text_model="summary-model",
            transcribe_model="speech-model",
            timeout_seconds=120,
        ),
        client=client,
    )

    result = provider.summarize_transcript(
        title="Demo",
        transcript="[00:00] 开场介绍主题\n[01:00] 解释关键步骤\n[02:00] 总结行动建议",
        language="zh-CN",
    )

    _, kwargs = client.calls[0]
    assert kwargs["timeout"] == 120
    assert "超过 120 秒" in result["overview"]
    assert result["outline"]


def test_provider_enriches_sparse_generic_summary_from_transcript():
    client = FakeClient(
        summary_content=(
            '{"overview":"这个视频讲了核心内容。",'
            '"outline":[],'
            '"key_points":["核心内容"],'
            '"highlights":[],'
            '"terms":[],'
            '"questions":["讲了什么？"],'
            '"mind_map":{"title":"核心内容","children":[]},'
            '"qa_pairs":[]}'
        )
    )
    provider = OpenAICompatibleProvider(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            text_model="summary-model",
            transcribe_model="speech-model",
        ),
        client=client,
    )

    result = provider.summarize_transcript(
        title="Notion AI 自动化复盘",
        transcript=(
            "[00:00] 主讲人说明这期视频复盘 Notion AI 数据库自动化流程。\n"
            "[01:10] 首先创建客户线索表，添加状态、来源、负责人三个字段。\n"
            "[03:20] 接着用 Zapier 监听表单提交，把邮箱和需求同步到 Notion。\n"
            "[05:40] 风险是重复线索会覆盖负责人，需要先用邮箱做去重校验。\n"
            "[07:00] 最后建议每周检查失败任务并记录修复动作。"
        ),
        language="zh-CN",
    )

    assert "Notion AI" in result["overview"]
    assert "核心内容" not in result["overview"]
    assert len(result["outline"]) >= 4
    assert result["outline"][0]["time"] == "00:00"
    assert any("Zapier" in point or "邮箱" in point for point in result["key_points"])
    assert len(result["key_points"]) >= 4
    assert len(result["highlights"]) >= 4
    assert any(item["time"] == "05:40" and "去重" in item["text"] for item in result["highlights"])
    assert len(result["terms"]) >= 2
    assert any(item["term"] == "Zapier" for item in result["terms"])
    assert len(result["questions"]) >= 3
    assert len(result["qa_pairs"]) >= 3
    assert all("继续追问" not in item["answer"] for item in result["qa_pairs"])
    assert len(result["mind_map"]["children"]) >= 4


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
    assert kwargs["json"]["max_tokens"] >= 12_000
    assert kwargs["json"]["messages"][0]["content"][0]["type"] == "text"
    assert result["overview"] == "概览"
    assert result["key_points"] == ["A"]
    assert result["mind_map"]["title"] == "Demo"
    assert result["qa_pairs"] == [{"question": "Q", "answer": "A"}]


def test_anthropic_provider_streams_readable_summary_then_builds_structured_json():
    structured_content = (
        '{"overview":"这是一段从 DeepSeek Anthropic 兼容接口完成后台结构化增强后的概览。",'
        '"outline":[{"time":"00:00","title":"开场","summary":"介绍视频主题和学习目标。"}],'
        '"key_points":["第一条核心知识点","第二条核心知识点"],'
        '"highlights":[],"terms":[],"questions":[],"mind_map":{"title":"演示","children":[]},"qa_pairs":[]}'
    )
    readable_chunks = [
        "一句话结论：DeepSeek Anthropic 兼容接口应该先流式输出可读总结。",
        "\n核心要点：\n- 用户立刻看到最终总结内容。\n- 结构化字段在后台补齐。",
    ]
    client = FakeAnthropicStreamingClient(
        chunks=readable_chunks,
        summary_content=structured_content,
    )
    previews = []
    provider = AnthropicCompatibleProvider(
        AIProviderConfig(
            base_url="https://api.deepseek.com/anthropic",
            api_key="secret",
            text_model="deepseek-v4-pro",
            transcribe_model="speech-model",
        ),
        client=client,
    )

    result = provider.summarize_transcript(
        title="Demo",
        transcript="[00:01] hello",
        language="zh-CN",
        stream_hook=previews.append,
    )

    method, url, kwargs = client.stream_calls[0]
    assert method == "POST"
    assert url == "https://api.deepseek.com/anthropic/v1/messages"
    assert kwargs["json"]["stream"] is True
    assert "禁止输出 JSON" in kwargs["json"]["system"]
    structured_url, structured_kwargs = client.calls[0]
    assert structured_url == "https://api.deepseek.com/anthropic/v1/messages"
    assert "已有可读总结" in structured_kwargs["json"]["messages"][0]["content"][0]["text"]
    assert result["overview"].startswith("这是一段从 DeepSeek")
    assert result["readable_summary"].startswith("一句话结论")
    assert any("一句话结论" in preview and "先流式输出可读总结" in preview for preview in previews)
    assert any("结构化字段在后台补齐" in preview for preview in previews)
    assert not any("{" in preview or "overview" in preview for preview in previews)


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


def test_summary_prompt_requests_compact_differentiated_mind_map():
    prompt = build_summary_prompt(title="学习视频", transcript="[00:00] 内容", language="zh-CN")

    assert "4-6 个一级分支" in prompt
    assert "每个一级分支至少 2 个子节点" in prompt
    assert "知识框架、内容脉络、方法步骤、案例证据、风险边界、行动建议" in prompt
    assert "避免使用“核心内容”“要点总结”这类泛化标题" in prompt


def test_summary_prompt_requires_grounded_complete_transcript_summary():
    prompt = build_summary_prompt(
        title="Notion AI 自动化复盘",
        transcript="[00:00] 先创建客户线索表\n[01:00] 再用 Zapier 同步表单",
        language="zh-CN",
    )

    assert "Notion AI 自动化复盘" in prompt
    assert "先创建客户线索表" in prompt
    assert "只能基于视频标题和转写稿" in prompt
    assert "不得编造" in prompt
    assert "字幕没有依据" in prompt
    assert "逐段提取字幕事实" in prompt
    assert "看完后应该能向没看过视频的人复述" in prompt
    assert '"topic"' in prompt
    assert '"audience"' in prompt
    assert '"main_thread"' in prompt
    assert '"examples"' in prompt
    assert '"action_items"' in prompt
    assert '"limitations"' in prompt
    assert "必须按字段顺序输出，overview 必须最先输出" in prompt
    assert "overview 320-520 字" in prompt
    assert "outline 8-14 项" in prompt
    assert "key_points 10-16 项" in prompt
    assert "highlights 6-10 项" in prompt
    assert "terms 0-8 项" in prompt
    assert "questions 5-8 项" in prompt
    assert "qa_pairs 5-8 项" in prompt


def test_summary_prompt_prioritizes_detailed_understanding_over_token_savings():
    transcript = "\n".join(
        f"[{index // 60:02d}:{index % 60:02d}] 第 {index} 段字幕详细说明产品定位、用户问题、操作步骤和验证结果。"
        for index in range(700)
    )

    structured_prompt = build_summary_prompt(
        title="AI 视频学习系统深度演示",
        transcript=transcript,
        language="zh-CN",
    )
    readable_prompt = build_readable_summary_prompt(
        title="AI 视频学习系统深度演示",
        transcript=transcript,
        language="zh-CN",
    )
    prepared_transcript = compact_transcript_for_prompt(transcript)

    assert SUMMARY_TRANSCRIPT_CHAR_BUDGET >= 50_000
    assert SUMMARY_RESPONSE_MAX_TOKENS >= 12_000
    assert READABLE_SUMMARY_RESPONSE_MAX_TOKENS >= 8_000
    assert "字幕已压缩" not in prepared_transcript
    assert "第 0 段字幕" in structured_prompt
    assert "第 699 段字幕" in structured_prompt
    assert "先不考虑返回 token 限制" in structured_prompt
    assert "像一篇可以独立阅读的深度学习笔记" in structured_prompt
    assert "禁止把字幕逐句改写或流水账搬运" in structured_prompt
    assert "关键内容详解" in readable_prompt
    assert "读完不需要看视频也能知道讲了什么" in readable_prompt


def test_summary_prompt_keeps_moderately_long_transcript_for_detailed_ai_calls():
    transcript = "\n".join(f"[{index:02d}:00] 这是第 {index} 段非常详细的视频字幕内容。" for index in range(500))

    prompt = build_summary_prompt(title="长视频", transcript=transcript, language="zh-CN")

    assert len(prompt) > 15000
    assert "字幕已压缩" not in prompt
    assert "这是第 0 段" in prompt
    assert "这是第 499 段" in prompt


def test_summary_prompt_compacts_extremely_long_transcript_after_large_budget():
    transcript = "\n".join(f"[{index:02d}:00] 这是第 {index} 段非常详细的视频字幕内容。" for index in range(2_500))

    prompt = build_summary_prompt(title="超长视频", transcript=transcript, language="zh-CN")

    assert "字幕已压缩" in prompt
    assert "这是第 0 段" in prompt
    assert "这是第 2499 段" in prompt


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


def test_normalize_summary_payload_preserves_complete_understanding_sections():
    payload = {
        "overview": "视频完整解释了从问题背景到执行路径的过程。",
        "topic": "AI 自动化复盘",
        "audience": "想理解自动化流程的运营人员",
        "main_thread": ["先说明线索表为什么重要", "再解释如何同步表单", "最后提醒验证指标"],
        "examples": [{"time": "01:00", "text": "用 Zapier 同步表单作为例子"}],
        "action_items": ["创建客户线索表", "同步表单数据", "检查转化指标"],
        "limitations": ["字幕没有说明具体价格"],
    }

    result = normalize_summary_payload(payload)

    assert result["topic"] == "AI 自动化复盘"
    assert result["audience"] == "想理解自动化流程的运营人员"
    assert result["main_thread"] == ["先说明线索表为什么重要", "再解释如何同步表单", "最后提醒验证指标"]
    assert result["examples"] == [{"time": "01:00", "text": "用 Zapier 同步表单作为例子"}]
    assert result["action_items"] == ["创建客户线索表", "同步表单数据", "检查转化指标"]
    assert result["limitations"] == ["字幕没有说明具体价格"]


def test_normalize_summary_payload_uses_transcript_to_replace_generic_sections():
    result = normalize_summary_payload(
        {
            "overview": "本视频介绍核心内容。",
            "outline": [],
            "key_points": ["核心内容", "要点总结"],
            "highlights": [],
            "terms": [],
            "questions": ["讲了什么？"],
            "mind_map": {"title": "核心内容", "children": []},
            "qa_pairs": [],
        },
        title="跨境独立站投放复盘",
        transcript=(
            "[00:00] 主讲人复盘跨境独立站广告投放结果，指出 ROAS 连续三天下滑。\n"
            "[02:15] 团队把预算从泛兴趣广告组转到复购人群，并暂停低转化素材。\n"
            "[04:30] 关键风险是样本量太小，不能只看单日点击成本做判断。\n"
            "[06:10] 后续动作是每周导出 Shopify 订单，和广告平台转化数据交叉核对。"
        ),
    )

    assert "跨境独立站" in result["overview"]
    assert len(result["outline"]) >= 4
    assert len(result["key_points"]) >= 4
    assert all(point not in {"核心内容", "要点总结"} for point in result["key_points"])
    assert any("ROAS" in item["text"] for item in result["highlights"])
    assert any(item["term"] in {"ROAS", "Shopify"} for item in result["terms"])
    assert len(result["qa_pairs"]) >= 3


def test_normalize_summary_payload_extracts_chinese_terms_from_transcript():
    result = normalize_summary_payload(
        {
            "overview": "本视频介绍核心内容。",
            "outline": [],
            "key_points": [],
            "highlights": [],
            "terms": [],
            "questions": [],
            "mind_map": {"title": "核心内容", "children": []},
            "qa_pairs": [],
        },
        title="私域运营自动化",
        transcript=(
            "[00:00] 主讲人介绍私域运营流程，先创建用户标签体系。\n"
            "[01:20] 接着使用自动化工具同步会员状态，避免人工漏记。\n"
            "[03:00] 关键风险是活动指标样本太少，不能只看单日转化率。"
        ),
    )

    terms = {item["term"] for item in result["terms"]}
    assert terms & {"私域运营流程", "自动化工具", "活动指标", "用户标签体系"}


class FakeRefusalStreamResponse(FakeStreamResponse):
    def iter_lines(self):
        yield 'data: {"choices":[{"delta":{"refusal":"I cannot generate this content.","content":""}}]}'
        yield "data: [DONE]"


class FakeRefusalStreamingClient(FakeClient):
    def __init__(self):
        super().__init__(summary_content="")
        self.stream_calls = []

    def stream(self, method, url, **kwargs):
        self.stream_calls.append((method, url, kwargs))
        return FakeRefusalStreamResponse([])


def test_openai_stream_delta_skips_refusal_and_returns_empty_string():
    client = FakeRefusalStreamingClient()
    provider = OpenAICompatibleProvider(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            text_model="summary-model",
            transcribe_model="speech-model",
        ),
        client=client,
    )

    with pytest.raises(RuntimeError, match="AI 总结服务未返回文本"):
        provider.summarize_transcript(
            title="Demo",
            transcript="[00:01] hello",
            language="zh-CN",
            stream_hook=lambda preview: None,
        )


def test_openai_stream_delta_does_not_leak_refusal_into_preview():
    readable_text = "一句话结论：本视频介绍核心内容。\n核心要点：\n- 要点一"
    valid_json = json.dumps(
        {
            "overview": "本视频介绍核心内容。",
            "outline": [],
            "key_points": ["要点一"],
            "highlights": [],
            "terms": [],
            "questions": [],
            "mind_map": {"title": "Demo", "children": []},
            "qa_pairs": [],
        },
        ensure_ascii=False,
    )

    class RefusalThenContentStreamResponse:
        def __init__(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"refusal":"I cannot generate","content":""}}]}'
            for i in range(0, len(readable_text), 30):
                yield f'data: {{"choices":[{{"delta":{{"content":{json.dumps(readable_text[i:i+30], ensure_ascii=False)}}}}}]}}'
            yield "data: [DONE]"

    client = FakeClient(summary_content=valid_json)
    client.stream = lambda method, url, **kwargs: RefusalThenContentStreamResponse()

    provider = OpenAICompatibleProvider(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            text_model="summary-model",
            transcribe_model="speech-model",
        ),
        client=client,
    )
    previews = []

    result = provider.summarize_transcript(
        title="Demo",
        transcript="[00:01] hello",
        language="zh-CN",
        stream_hook=previews.append,
    )

    assert result["overview"] == "本视频介绍核心内容。"
    assert not any("I cannot generate" in p for p in previews)
    assert any("一句话结论" in p for p in previews)


def test_mock_ai_provider_returns_deterministic_learning_summary(tmp_path: Path):
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")
    provider = MockAIProvider()

    assert "演示转写" in provider.transcribe_audio(audio, language="zh-CN")
    result = provider.summarize_transcript(title="AI 课程", transcript="第一章 模型", language="zh-CN")

    assert result["overview"].startswith("《AI 课程》")
    assert result["key_points"]
