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
  "timeout_seconds": 120
}
```

- `provider`: `openai-compatible` 使用真实 AI 服务，`mock` 用于本地演示。DeepSeek 官方 Chat Completions 接口属于 OpenAI 兼容协议，可填 `DeepSeek` 或 `openai-compatible`。
- `base_url`: OpenAI 兼容 API 地址。DeepSeek 官方地址可使用 `https://api.deepseek.com` 或兼容的 `/v1` 地址；如果使用 DeepSeek Anthropic 兼容接口，则使用以 `/anthropic` 结尾的地址。
- `api_key`: 服务端使用的 AI API Key。
- `text_model`: 结构化视频总结模型。
- `timeout_seconds`: AI 请求超时时间。

当前版本只支持已有字幕的视频总结。历史配置里的 `transcribe_model` 字段会被兼容读取，但总结流程不会调用语音转写。

## 环境变量覆盖

环境变量优先级高于配置文件，适合部署环境注入：

- `AI_CONFIG_FILE`
- `AI_PROVIDER`
- `AI_BASE_URL`
- `AI_API_KEY`
- `AI_TEXT_MODEL`
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
