# AI 配置说明

AI 总结能力由后端统一配置，前端不会接收或保存 AI 服务密钥。

## 配置文件

本地配置文件路径：

```text
backend/config/ai.config.json
```

该文件已加入 `.gitignore`，可以填写真实密钥。仓库中保留了可提交的样例文件：

```text
backend/config/ai.config.example.json
```

字段说明：

```json
{
  "provider": "openai-compatible",
  "base_url": "https://api.openai.com/v1",
  "api_key": "",
  "text_model": "gpt-4o-mini",
  "transcribe_provider": "local-faster-whisper",
  "transcribe_model": "small",
  "transcribe_device": "cpu",
  "transcribe_compute_type": "int8",
  "transcribe_beam_size": 5,
  "transcribe_vad_filter": true,
  "timeout_seconds": 120
}
```

- `provider`: `openai-compatible` 使用真实 AI 服务，`mock` 用于本地演示。DeepSeek 官方 Chat Completions 接口属于 OpenAI 兼容协议，可填 `DeepSeek` 或 `openai-compatible`。
- `base_url`: OpenAI 兼容 API 地址。DeepSeek 官方地址可使用 `https://api.deepseek.com` 或兼容的 `/v1` 地址；如果使用 DeepSeek Anthropic 兼容接口，则使用以 `/anthropic` 结尾的地址。
- `api_key`: 服务端使用的 AI API Key。
- `text_model`: 结构化视频总结模型。
- `transcribe_provider`: 无字幕视频的语音转写服务。推荐 `local-faster-whisper`，也支持 `openai-compatible`。
- `transcribe_model`: 转写模型。`local-faster-whisper` 可填 `tiny`、`base`、`small`、`medium`、`large-v3` 等本地模型；`openai-compatible` 可填 `gpt-4o-mini-transcribe`、`whisper-1` 或第三方兼容模型。
- `transcribe_device`: 本地转写设备，CPU 环境用 `cpu`，NVIDIA GPU 可用 `cuda`。
- `transcribe_compute_type`: 本地转写计算类型。CPU 推荐 `int8`，CUDA 可用 `float16` 或 `int8_float16`。
- `transcribe_beam_size`: faster-whisper 解码 beam size，默认 `5`。
- `transcribe_vad_filter`: 是否启用 VAD 静音过滤，默认 `true`。
- `timeout_seconds`: AI 请求超时时间。

总结流程会优先使用人工字幕或自动字幕；如果没有可用字幕，会提取公开视频音频并调用语音转写模型生成转写稿，再继续复用同一套 AI 总结、思维导图、问答和 Markdown 导出流程。推荐把文本总结和语音转写分开配置：文本总结可以使用 OpenAI-compatible 或 DeepSeek 等文本模型，语音转写优先使用本地 `faster-whisper`，避免 OpenAI API quota 阻塞。

## 本地 faster-whisper 转写

首次使用本地语音转写前，需要在后端虚拟环境安装：

```bash
cd backend
source .venv/bin/activate
pip install faster-whisper
```

CPU 环境推荐从 `small` 起步：

```json
{
  "transcribe_provider": "local-faster-whisper",
  "transcribe_model": "small",
  "transcribe_device": "cpu",
  "transcribe_compute_type": "int8"
}
```

如果暂时不想安装本地模型，也可以把 `transcribe_provider` 改成 `openai-compatible`，并配置 `transcribe_base_url`、`transcribe_api_key`、`transcribe_model`，让转写走 OpenAI、Groq 或其他兼容 `/audio/transcriptions` 的服务。最稳妥的无额度依赖方案是只启用 `local-faster-whisper`。

## 环境变量覆盖

环境变量优先级高于配置文件，适合部署环境注入：

- `AI_CONFIG_FILE`
- `AI_PROVIDER`
- `AI_BASE_URL`
- `AI_API_KEY`
- `AI_TEXT_MODEL`
- `AI_TRANSCRIBE_PROVIDER`
- `AI_TRANSCRIBE_BASE_URL`
- `AI_TRANSCRIBE_API_KEY`
- `AI_TRANSCRIBE_MODEL`
- `AI_TRANSCRIBE_DEVICE`
- `AI_TRANSCRIBE_COMPUTE_TYPE`
- `AI_TRANSCRIBE_BEAM_SIZE`
- `AI_TRANSCRIBE_VAD_FILTER`
- `AI_TIMEOUT_SECONDS`

## Bilibili 登录字幕

Bilibili 某些视频会在公开页面显示字幕入口，但字幕 API 返回 `need_login_subtitle: true`。这类视频需要登录态才能下载字幕。

默认情况下，本项目不会读取浏览器 Cookie。只有你显式设置下面任一环境变量时，后端才会把授权信息交给 yt-dlp：

- `BILIBILI_COOKIE_FILE`: Netscape 格式的 Bilibili Cookie 文件路径。
- `BILIBILI_COOKIES_FROM_BROWSER`: 让 yt-dlp 从指定浏览器读取 Cookie，例如 `chrome`、`chrome:Default`、`safari`、`firefox:release`。

Cookie 属于敏感登录凭据。只建议在本地自用环境启用，并避免提交到仓库。

加载优先级：

```text
默认值 < backend/config/ai.config.json < 环境变量
```
