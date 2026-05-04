# AI 配置说明

AI 总结能力由后端统一配置，前端不会接收或保存 AI 服务密钥。项目现在只把本地配置集中到 `backend/.env`，不再默认读取 `backend/config/ai.config.json`。

## 配置入口

首次本地运行时复制统一模板：

```bash
cp backend/.env.example backend/.env
```

然后在 `backend/.env` 中填写 AI 配置：

```dotenv
AI_PROVIDER=openai-compatible
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=
AI_TEXT_MODEL=gpt-4o-mini
AI_TRANSCRIBE_PROVIDER=local-faster-whisper
AI_TRANSCRIBE_BASE_URL=
AI_TRANSCRIBE_API_KEY=
AI_TRANSCRIBE_MODEL=small
AI_TRANSCRIBE_DEVICE=cpu
AI_TRANSCRIBE_COMPUTE_TYPE=int8
AI_TRANSCRIBE_BEAM_SIZE=5
AI_TRANSCRIBE_VAD_FILTER=true
AI_TIMEOUT_SECONDS=120
```

部署环境可以直接注入同名环境变量，环境变量优先级高于 `backend/.env`。

## 字段说明

- `AI_PROVIDER`: `openai-compatible` 使用真实 AI 服务，`mock` 用于本地演示。DeepSeek 官方 Chat Completions 接口属于 OpenAI 兼容协议，可填 `DeepSeek` 或 `openai-compatible`。
- `AI_BASE_URL`: OpenAI 兼容 API 地址。DeepSeek 官方地址可使用 `https://api.deepseek.com` 或兼容的 `/v1` 地址；如果使用 DeepSeek Anthropic 兼容接口，则使用以 `/anthropic` 结尾的地址。
- `AI_API_KEY`: 服务端使用的 AI API Key。
- `AI_TEXT_MODEL`: 结构化视频总结模型。
- `AI_TRANSCRIBE_PROVIDER`: 无字幕视频的语音转写服务。推荐 `local-faster-whisper`，也支持 `openai-compatible`。
- `AI_TRANSCRIBE_BASE_URL`: 云端语音转写服务地址；为空时复用 `AI_BASE_URL`。
- `AI_TRANSCRIBE_API_KEY`: 云端语音转写服务密钥；为空时复用 `AI_API_KEY`。
- `AI_TRANSCRIBE_MODEL`: 转写模型。`local-faster-whisper` 可填 `tiny`、`base`、`small`、`medium`、`large-v3` 等本地模型；`openai-compatible` 可填 `gpt-4o-mini-transcribe`、`whisper-1` 或第三方兼容模型。
- `AI_TRANSCRIBE_DEVICE`: 本地转写设备，CPU 环境用 `cpu`，NVIDIA GPU 可用 `cuda`。
- `AI_TRANSCRIBE_COMPUTE_TYPE`: 本地转写计算类型。CPU 推荐 `int8`，CUDA 可用 `float16` 或 `int8_float16`。
- `AI_TRANSCRIBE_BEAM_SIZE`: faster-whisper 解码 beam size，默认 `5`。
- `AI_TRANSCRIBE_VAD_FILTER`: 是否启用 VAD 静音过滤，默认 `true`。
- `AI_TIMEOUT_SECONDS`: AI 请求超时时间。

总结流程会优先使用人工字幕或自动字幕；如果没有可用字幕，会提取公开视频音频并调用语音转写模型生成转写稿，再继续复用同一套 AI 总结、思维导图、问答和 Markdown 导出流程。推荐把文本总结和语音转写分开配置：文本总结可以使用 OpenAI-compatible 或 DeepSeek 等文本模型，语音转写优先使用本地 `faster-whisper`，避免 OpenAI API quota 阻塞。

## 本地 faster-whisper 转写

首次使用本地语音转写前，需要在后端虚拟环境安装：

```bash
cd backend
source .venv/bin/activate
pip install faster-whisper
```

CPU 环境推荐从 `small` 起步：

```dotenv
AI_TRANSCRIBE_PROVIDER=local-faster-whisper
AI_TRANSCRIBE_MODEL=small
AI_TRANSCRIBE_DEVICE=cpu
AI_TRANSCRIBE_COMPUTE_TYPE=int8
```

如果暂时不想安装本地模型，也可以把 `AI_TRANSCRIBE_PROVIDER` 改成 `openai-compatible`，并配置 `AI_TRANSCRIBE_BASE_URL`、`AI_TRANSCRIBE_API_KEY`、`AI_TRANSCRIBE_MODEL`，让转写走 OpenAI、Groq 或其他兼容 `/audio/transcriptions` 的服务。最稳妥的无额度依赖方案是只启用 `local-faster-whisper`。

## Bilibili 登录字幕

Bilibili 某些视频会在公开页面显示字幕入口，但字幕 API 返回 `need_login_subtitle: true`。这类视频需要登录态才能下载字幕。

默认情况下，本项目不会读取浏览器 Cookie。只有你显式设置下面任一 `backend/.env` 配置时，后端才会把授权信息交给 yt-dlp：

- `BILIBILI_COOKIE_FILE`: Netscape 格式的 Bilibili Cookie 文件路径。
- `BILIBILI_COOKIES_FROM_BROWSER`: 让 yt-dlp 从指定浏览器读取 Cookie，例如 `chrome`、`chrome:Default`、`safari`、`firefox:release`。

Cookie 属于敏感登录凭据。只建议在本地自用环境启用，并避免提交到仓库。

加载优先级：

```text
默认值 < 显式 AI_CONFIG_FILE 旧 JSON 配置 < backend/.env < shell 环境变量
```

`AI_CONFIG_FILE` 仅作为旧配置迁移兼容入口保留；新配置请写入 `backend/.env`。
