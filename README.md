# 万能视频下载总结器 SaveAny

万能视频下载总结器 SaveAny 是一个面向公开视频学习、复盘、下载、字幕整理和 AI 知识整理的本地或自托管 Web 应用。它把公开视频解析、格式选择、后台下载、实时进度、文件 token 交付、账号登录、个人额度、Stripe 订阅、AI 视频总结、字幕/语音转写、思维导图、AI 问答、Markdown 导出和 GEO/SEO 静态内容放在同一个项目里。

项目当前不是一个只保存视频文件的小工具，而是一个完整的公开视频学习控制台：用户粘贴公开视频链接后，系统会解析标题、封面、时长、格式、字幕和播放列表条目；用户可以选择稳定 MP4 或原始最高画质下载；登录用户还可以把视频自动转成摘要、章节大纲、核心知识点、时间轴要点、术语解释、字幕文本、思维导图、AI 问答和可导出的 Markdown 学习笔记。

> 中文内容中建议始终使用完整产品名：`万能视频下载总结器 SaveAny`。

## 目录

- [项目定位](#项目定位)
- [当前功能总览](#当前功能总览)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [核心工作流](#核心工作流)
- [后端架构](#后端架构)
- [前端架构](#前端架构)
- [API 接口](#api-接口)
- [账号、会员与额度](#账号会员与额度)
- [AI 总结与语音转写](#ai-总结与语音转写)
- [公开视频解析与下载](#公开视频解析与下载)
- [GEO 与 SEO](#geo-与-seo)
- [运行时数据](#运行时数据)
- [本地开发](#本地开发)
- [环境变量](#环境变量)
- [Stripe 联调](#stripe-联调)
- [测试与验证](#测试与验证)
- [部署说明](#部署说明)
- [安全与合规边界](#安全与合规边界)
- [已知限制](#已知限制)
- [文档索引](#文档索引)

## 项目定位

SaveAny 的产品定位是“公开视频下载总结器”，主要服务这些场景：

- 课程学习：保存公开课程、公开视频教程，并生成章节、知识点和复习问题。
- 会议复盘：处理公开录播、访谈、发布会等视频，提炼摘要和行动线索。
- 素材归档：把公开视频素材保存为本地文件，并保留可检索的文字记录。
- 字幕提取：优先读取公开视频字幕，没有字幕时按配置走语音转写。
- 知识整理：把长视频整理成 Markdown、思维导图和问答记录。
- 自托管使用：下载任务、账号、额度和缓存默认保存在自己的本地运行目录。

项目的边界也很明确：

- 只面向公开视频。
- 不绕过 DRM。
- 不绕过付费墙。
- 不绕过私密、登录限定、验证码、地区限制或平台风控。
- 不提供浏览器中的手动 Cookie 输入流程。
- 不托管共享登录态、二维码登录或平台账号池。
- 下载内容应只用于学习、研究、备份和个人资料整理，并遵守平台条款与版权要求。

## 当前功能总览

### 视频解析与下载

- 支持粘贴公开视频或播放列表 URL。
- 后端通过 `yt-dlp` 解析主流公开视频平台。
- 可返回视频标题、封面、时长、来源 extractor、格式列表、字幕轨道和播放列表条目。
- 支持 YouTube 相关机器人校验短暂失败的重试逻辑。
- 支持 Bilibili 公开视频元数据 fallback。
- 支持抖音公开视频专用解析链路，不要求用户提供 Cookie。
- 支持 TikTok、Bilibili、YouTube 等平台的格式策略差异化处理。
- 提供“稳定 MP4（推荐）”和“原始最高画质”两类默认选项。
- 可展示源格式中的分辨率、容器和文件大小。
- 下载任务在后端线程中执行，不阻塞 API 请求。
- 下载进度通过 Server-Sent Events 推送，前端同时有轮询兜底。
- 任务状态覆盖 `queued`、`downloading`、`processing`、`completed`、`failed`。
- 下载进度包含百分比、速度、ETA、状态消息、错误文案和下载入口。
- 完成文件通过 `/files/{token}` 临时 token 下载，不向浏览器暴露真实路径。
- 多个输出产物会被打包为 `download-artifacts.zip`。
- 下载完成后用 `ffprobe` 校验媒体流，避免把无视频、无音频或不兼容 MP4 误报为成功。
- 启动和任务完成后会清理临时下载碎片，只保留最近完成目录。

### 抖音公开视频解析

抖音不走普通 Cookie 登录路径，而是走公开视频 resolver chain：

- `f2` resolver：可用时优先，动态导入 `f2` 包。
- `douyinvd` resolver：兼容自托管 sidecar，也可以从公开页面提取播放地址。
- `browser` resolver：使用 Playwright 在公开页面捕获 `aweme/detail` 响应作为兜底。

默认链路由 `DOUYIN_RESOLVER_CHAIN=f2,douyinvd,browser` 控制。`DOUYIN_PUBLIC_ONLY=true` 默认开启，确保抖音请求保持在公开视频路径上。

### AI 视频总结

- 解析成功后，前端会尝试自动创建 AI 总结任务。
- AI 总结要求登录用户。
- 总结创建时必须有当前解析快照或可复用的分析结果。
- 总结流程优先使用人工字幕或自动字幕。
- 没有可用字幕时，后端提取公开视频音频并调用语音转写服务。
- 支持本地 `faster-whisper` 转写。
- 支持 OpenAI-compatible `/audio/transcriptions` 云端转写。
- 支持多个转写 provider 用逗号或 `>` 配置 fallback。
- 生成结构化 JSON 总结，字段覆盖 `overview`、`outline`、`key_points`、`highlights`、`terms`、`questions`、`mind_map`、`qa_pairs`。
- AI 输出会归一化，避免前端依赖不稳定字段。
- 支持快速版草稿：转写或总结尚未完成时先显示可读预览。
- 支持流式总结预览，前端逐行显示生成中的结构化内容。
- 支持总结缓存，相同视频、语言和 prompt 版本可以复用。
- 支持用户隔离：总结任务归属用户，其他用户不能读取；可在需要时为当前用户克隆完成缓存。
- 失败时会退还已预留的 AI 总结或转写额度。
- 服务重启后会退还中断任务的待退款额度。

### AI 学习工作区

前端 AI 工作区包含四个模块：

- 总结内容：概括、章节大纲、核心知识点、时间轴要点、术语解释、可继续追问的问题。
- 字幕文本：展示带时间戳的字幕或转写文本。
- 思维导图：把结构化 `mind_map` 渲染成可缩放 SVG。
- AI 问答：围绕当前总结和字幕继续提问。

导出能力：

- 下载总结 Markdown。
- 下载后端生成的完整 Markdown。
- 下载思维导图 SVG。
- 下载思维导图 PNG。
- 导出问答 Markdown 的前端工具函数已实现。

### 账号与安全登录

- 支持邮箱密码注册。
- 支持邮箱密码登录。
- 支持退出登录。
- 支持当前用户信息 `/api/me`。
- 支持密码重置请求和确认。
- 开发模式可直接返回重置 token，方便本地验证。
- 密码使用 Argon2 哈希。
- Session token 只保存哈希。
- Session 使用 HttpOnly cookie。
- Session 有空闲过期和绝对过期。
- 登录态写入 session 级 CSRF token。
- 注册、登录、退出、密码重置和账单写操作都有 CSRF 校验。
- 同源校验基于 `Origin` 或 `Referer`。
- 注册、登录失败和密码重置有 IP 与邮箱维度的短窗口限流。
- 密码重置成功后会撤销该用户现有 session。

### 会员、额度与 Stripe

- 未登录访客有每日解析和下载额度。
- 登录免费版有更高每日解析、下载、AI 总结额度，并有每月转写和问答额度。
- Pro 个人版有月度解析、下载、AI 总结、转写分钟和问答额度。
- 支持按量包：AI 总结次数包和语音转写分钟包。
- 额度扣减使用服务端 reservation 机制。
- 总结和问答失败时会退款。
- 按量包按过期时间优先消耗。
- Stripe 是唯一账单模式。
- 本地 mock billing 已移除，不允许绕过支付服务直接写入会员或额度。
- 支持 Stripe Checkout 订阅。
- 支持 Stripe Checkout 按量包购买。
- 支持 Stripe Customer Portal 管理订阅。
- 支持 Checkout 成功回跳后的服务端确认。
- 支持 Stripe webhook 签名校验。
- 支持 Stripe event id 幂等处理。
- 支持 webhook 处理 lease，避免同一事件并发处理。
- 支持 subscription、invoice、checkout session、payment failed 等事件更新会员状态。

### 前端体验

- Vue 3 单页应用。
- 工业媒体控制台风格，深色 graphite 背景和暖色主操作。
- 顶部导航包含下载、核心能力、常见问题、套餐方案。
- 首页首屏就是可用下载控制台，不是纯营销页。
- 输入 URL 后解析，解析成功后展示视频元数据、格式选择、下载按钮和 AI 工作区。
- 账号菜单显示邮箱、套餐、总结额度、转写额度和问答额度。
- 套餐页展示免费版、Pro 个人版和按量包。
- Stripe 支付成功回跳后自动确认状态。
- 支持本地工作区恢复：URL、解析结果、下载任务和总结任务会保存在浏览器存储里。
- SSE 中断时会自动尝试读取当前任务快照，轮询继续兜底。
- 中文状态文案覆盖下载、总结、转写、额度、支付和网络失败。

### GEO/SEO 与静态内容

- 前端构建前会生成 SEO 静态资产。
- 当前 `frontend/public` 下包含 47 个 `index.html` 页面和 47 个 Markdown mirror。
- 生成 `sitemap.xml`。
- 生成 `robots.txt`。
- 生成 `llms.txt` 和 `llms-full.txt`。
- 生成 `_headers`、`_redirects` 和 `404.html`。
- 支持站长平台 verification meta 或 verification file。
- 支持 IndexNow key 文件、dry run、增量提交和全量提交。
- FastAPI 可在生产自托管时直接服务构建后的前端静态文件。
- FastAPI 对前端静态资源设置不同缓存策略。
- 可启用 canonical redirect，把前端 GET/HEAD 请求跳转到配置的正式域名。
- 后端会记录隐私轻量的 GEO 访问日志，只包含方法、路径、状态、crawler family、时间和 surface type，不记录 IP 和 query string。

## 技术栈

### 后端

- Python
- FastAPI
- Pydantic
- Uvicorn
- yt-dlp
- httpx
- Playwright
- SQLite
- Argon2 (`argon2-cffi`)
- Stripe Python SDK
- pytest
- ffmpeg / ffprobe
- 可选：`f2` 抖音解析包
- 可选：`faster-whisper` 本地语音转写

### 前端

- Vue 3
- Vite 8
- Tailwind CSS 4
- `@tailwindcss/vite`
- `lucide-vue-next`
- 原生 `fetch`
- EventSource / Server-Sent Events
- Node.js `node:test`
- SEO 静态生成脚本

### 本地工具

- Node.js：当前 Vite 依赖要求 Node `^20.19.0` 或 `>=22.12.0`。
- npm
- Python 虚拟环境
- ffmpeg 和 ffprobe
- Stripe CLI，用于本地 webhook 转发
- Playwright Chromium 或本机 Chrome，用于抖音 browser resolver

## 项目结构

```text
.
├── README.md
├── backend
│   ├── .env.example
│   ├── app
│   │   ├── main.py
│   │   ├── auth_routes.py
│   │   ├── billing_routes.py
│   │   ├── entitlement_routes.py
│   │   ├── summary_routes.py
│   │   └── services
│   │       ├── ai_config.py
│   │       ├── ai_provider.py
│   │       ├── analysis_store.py
│   │       ├── app_config.py
│   │       ├── asset_store.py
│   │       ├── audio_service.py
│   │       ├── auth_service.py
│   │       ├── billing_service.py
│   │       ├── csrf.py
│   │       ├── database.py
│   │       ├── douyin_browser_service.py
│   │       ├── douyin_public_resolver.py
│   │       ├── entitlements.py
│   │       ├── geo_monitor.py
│   │       ├── plan_catalog.py
│   │       ├── rate_limit.py
│   │       ├── runtime_cleanup.py
│   │       ├── summary_service.py
│   │       ├── summary_store.py
│   │       ├── task_store.py
│   │       ├── transcript_service.py
│   │       ├── transcription_provider.py
│   │       ├── usage_meter.py
│   │       └── ytdlp_service.py
│   ├── scripts
│   │   └── geo_monitor_report.py
│   ├── tests
│   │   └── test_*.py
│   ├── pytest.ini
│   └── requirements.txt
├── frontend
│   ├── src
│   │   ├── App.vue
│   │   ├── main.js
│   │   ├── assets
│   │   ├── components
│   │   │   └── summary
│   │   ├── seo
│   │   │   └── pages.js
│   │   ├── services
│   │   └── utils
│   ├── public
│   │   ├── sitemap.xml
│   │   ├── robots.txt
│   │   ├── llms.txt
│   │   ├── llms-full.txt
│   │   ├── _headers
│   │   ├── _redirects
│   │   ├── 404.html
│   │   └── 多个 SEO 页面目录
│   ├── scripts
│   ├── tests
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   └── vite.config.js
├── docs
│   ├── 01-requirements.md
│   ├── 02-product-design.md
│   ├── 03-technical-architecture.md
│   ├── 04-api-design.md
│   ├── 05-ui-design-system.md
│   ├── 06-implementation-plan.md
│   ├── 07-extension-guide.md
│   ├── 08-feature-summary.md
│   ├── 09-ai-configuration.md
│   ├── 10-seo-deployment-checklist.md
│   ├── 11-membership-stripe-setup.md
│   └── diagrams
└── runtime
    ├── downloads
    ├── tmp
    ├── summaries
    └── saveany.db
```

`runtime` 是本地运行时目录，会保存下载结果、临时文件、总结缓存和 SQLite 数据库。它不应提交到 Git。

## 核心工作流

### 下载工作流

1. 用户在前端输入 YouTube、Bilibili、抖音、TikTok 等公开视频链接。
2. 前端调用 `POST /api/analyze`。
3. 后端检查访客或登录用户解析额度。
4. 后端使用 `yt-dlp` 或抖音公开视频 resolver chain 解析元数据。
5. 后端注册远程封面 asset token，并生成 `analysis_token`。
6. 前端展示标题、封面、时长、来源、格式选项和播放列表数量。
7. 用户选择格式并点击下载。
8. 前端调用 `POST /api/download`，携带 URL、格式和 `analysis_token`。
9. 后端复用解析快照进行时长校验和额度扣减。
10. 后端创建下载任务并启动线程。
11. 前端通过 `/api/tasks/{task_id}/events` 接收 SSE。
12. SSE 失败时，前端通过 `/api/tasks/{task_id}` 轮询兜底。
13. 下载完成后，后端注册文件 token。
14. 前端显示下载按钮，用户通过 `/files/{token}` 获取文件。

### AI 总结工作流

1. 用户解析公开视频。
2. 前端在解析成功后尝试自动创建总结任务。
3. 未登录用户会看到登录门禁。
4. 登录后，前端调用 `POST /api/summaries`，携带 URL、标题、语言和 `analysis_token`。
5. 后端检查解析快照、视频时长和 AI 总结额度。
6. 如果没有可用字幕，后端预留语音转写分钟。
7. 后端创建总结任务并启动线程。
8. `SummaryService` 优先提取字幕。
9. 没有字幕时，`AudioExtractionService` 提取音频。
10. `TranscriptionProvider` 使用本地 `faster-whisper` 或云端转写服务生成文本。
11. 后端先生成快速版草稿。
12. 后端调用文本模型生成结构化总结。
13. 前端通过 `/api/summaries/{summary_id}/events` 接收进度、草稿和流式预览。
14. 总结完成后，结果保存到 `runtime/summaries`。
15. 用户可以切换摘要、字幕、思维导图和问答视图。
16. 用户可以下载 Markdown、SVG 或 PNG。

### Stripe 订阅工作流

1. 用户登录。
2. 用户进入套餐页。
3. 点击开通 Pro 或购买按量包。
4. 前端调用 `POST /api/billing/checkout`。
5. 后端校验 session CSRF。
6. 后端创建或复用 Stripe Customer。
7. 后端创建 Checkout Session，并记录 `billing_attempts`。
8. 前端跳转到 Stripe Checkout。
9. 支付完成后回到 SaveAny。
10. 前端调用 `POST /api/billing/checkout/confirm` 做服务端确认。
11. Stripe webhook 同步 subscription、invoice 或 payment 状态。
12. 后端更新会员或授予按量包。
13. 前端刷新 `/api/me`、`/api/billing/status` 和 `/api/entitlements/status`。

## 后端架构

### `backend/app/main.py`

FastAPI 应用入口，负责：

- 初始化 SQLite 数据库。
- 退还中断的总结额度。
- 创建运行时下载目录。
- 清理旧下载目录和临时目录。
- 注册 CORS。
- 注册 auth、billing、entitlement、summary 路由。
- 提供 `/api/health`。
- 提供视频解析 `/api/analyze`。
- 提供下载任务 `/api/download`。
- 提供任务查询和 SSE。
- 提供封面代理 `/api/proxy/assets/{token}`。
- 提供文件下载 `/files/{token}`。
- 在存在 `frontend/dist` 时服务前端静态资源。
- 根据配置执行 canonical redirect。
- 记录 GEO crawler 访问。

### `YtDlpService`

路径：`backend/app/services/ytdlp_service.py`

职责：

- 清理 URL 中的追踪参数。
- 构造默认 HTTP headers。
- 为 YouTube 设置 extractor args。
- 为 Bilibili、TikTok 选择更稳妥的默认格式。
- 归一化 `yt-dlp` 的 formats、subtitles 和 playlist entries。
- 调用 `yt-dlp` 做 metadata extraction。
- 调用 `yt-dlp` 执行下载。
- 对 YouTube 下载错误做可恢复重试。
- 选择输出产物。
- 多产物时打包 zip。
- 用 `ffprobe` 校验媒体流。
- 把平台报错转换为用户可理解的中文边界提示。

### `DouyinPublicResolver`

路径：

- `backend/app/services/douyin_public_resolver.py`
- `backend/app/services/douyin_browser_service.py`

职责：

- 判断抖音 URL。
- 解析 `/video/{aweme_id}`。
- 使用 F2、douyinVd 和 Playwright browser resolver 依次尝试。
- 从公开页面或公开接口获得视频播放地址。
- 直接流式下载抖音公开视频。
- 失败时返回统一的公开视频边界提示。

### `TaskStore`

路径：`backend/app/services/task_store.py`

职责：

- 保存内存任务状态。
- 生成任务 ID。
- 更新任务进度。
- 注册完成文件 token。
- 解析文件 token 到本地路径。

任务状态是内存态。服务重启后，历史下载任务和文件 token 不可恢复。

### `SummaryService`

路径：`backend/app/services/summary_service.py`

职责：

- 管理字幕提取、音频提取、语音转写和文本总结流程。
- 支持从上次总结结果复用 transcript。
- 支持 demo mode。
- 生成快速草稿。
- 生成流式预览。
- 调用 AI provider 输出结构化 JSON。
- 归一化 AI 输出。
- 渲染 Markdown。
- 估算语音转写音频时长。

### `TranscriptService`

路径：`backend/app/services/transcript_service.py`

职责：

- 用 `yt-dlp` 下载字幕和自动字幕。
- 支持 SRT 和 VTT。
- 解析字幕时间戳。
- 清理字幕标签。
- 生成带时间戳 transcript text。
- 对 Bilibili 可选使用 `BILIBILI_COOKIE_FILE` 或 `BILIBILI_COOKIES_FROM_BROWSER`。

注意：这不是浏览器里给用户上传 Cookie 的入口，而是本地自用部署时的服务端显式配置。

### `AudioExtractionService`

路径：`backend/app/services/audio_service.py`

职责：

- 无字幕时提取音频。
- YouTube 使用更轻量的音频格式选择。
- 普通站点使用 `yt-dlp` 加 FFmpeg postprocessor。
- 抖音公开视频先通过 resolver 下载源媒体，再用 ffmpeg 抽音频。
- 失败时返回可理解的 ffmpeg 或音轨错误。

### AI Provider

路径：

- `backend/app/services/ai_config.py`
- `backend/app/services/ai_provider.py`
- `backend/app/services/transcription_provider.py`

职责：

- 从 `backend/.env`、shell 环境变量或旧 `AI_CONFIG_FILE` 读取 AI 配置。
- 支持 OpenAI-compatible chat completions。
- 支持 Anthropic-compatible messages 接口。
- 支持 mock provider。
- 支持 OpenAI-compatible speech-to-text。
- 支持本地 `faster-whisper`。
- 支持多个转写 provider fallback。
- 对 AI 输出做 JSON 解析、fallback 和归一化。
- 支持总结问答，并要求只基于字幕和总结回答。

### Auth、CSRF 与 Rate Limit

路径：

- `backend/app/auth_routes.py`
- `backend/app/services/auth_service.py`
- `backend/app/services/csrf.py`
- `backend/app/services/rate_limit.py`

职责：

- 注册、登录、退出、密码重置。
- Argon2 密码哈希。
- HttpOnly session cookie。
- session token 和 reset token 只保存哈希。
- session idle 和 absolute 过期。
- session CSRF token。
- prelogin CSRF token。
- 同源校验。
- IP/email 维度限流。

### Billing 与 Entitlements

路径：

- `backend/app/billing_routes.py`
- `backend/app/entitlement_routes.py`
- `backend/app/services/billing_service.py`
- `backend/app/services/entitlements.py`
- `backend/app/services/usage_meter.py`
- `backend/app/services/plan_catalog.py`

职责：

- 会员状态读取。
- 额度状态读取。
- Stripe Checkout。
- Stripe Portal。
- Stripe webhook。
- Stripe event id 幂等。
- Checkout attempt 复用和过期。
- Pro 订阅状态维护。
- AI 总结次数包和转写分钟包授予。
- plan quota 与 pack quota 混合扣减。
- 失败退款。

### Database

路径：`backend/app/services/database.py`

当前 SQLite schema 包含：

- `users`
- `sessions`
- `password_reset_tokens`
- `subscriptions`
- `stripe_customers`
- `stripe_events`
- `usage_daily`
- `summary_quota_reservations`
- `billing_attempts`
- `rate_limits`
- `usage_periods`
- `anonymous_usage`
- `meter_reservations`
- `credit_packs`
- `meter_reservation_pack_uses`
- `summary_questions`

数据库初始化时会执行兼容迁移，补齐旧库缺失字段。

### Runtime Cleanup

路径：`backend/app/services/runtime_cleanup.py`

职责：

- 删除 `.part` 和 `.ytdl` 临时文件。
- 失败任务无完成产物时删除任务目录。
- 保留最近完成下载目录。
- 启动和任务完成后清理下载目录。

## 前端架构

### `frontend/src/App.vue`

主应用组件，负责：

- 首页和套餐页导航。
- URL 输入和解析状态。
- 格式选择。
- 下载任务创建。
- 下载任务 SSE 和轮询。
- AI 总结自动创建。
- AI 总结 SSE 和轮询。
- 登录、注册、密码重置弹窗。
- 账号菜单。
- Stripe Checkout 和 Portal 操作。
- Checkout 回跳确认。
- 额度显示。
- 本地工作区保存和恢复。
- 中文状态文案本地化。

### API Client

路径：`frontend/src/services/api.js`

封装：

- `analyzeUrl`
- `createDownloadTask`
- `createSummaryTask`
- `getMe`
- `registerAccount`
- `loginAccount`
- `logoutAccount`
- `requestPasswordReset`
- `confirmPasswordReset`
- `getBillingStatus`
- `getEntitlementStatus`
- `createBillingCheckout`
- `confirmBillingCheckout`
- `createBillingPortal`
- `getTask`
- `getSummary`
- `askSummaryQuestion`
- `connectTaskEvents`
- `connectSummaryEvents`

写操作会自动带上 prelogin 或 session CSRF token。

### Summary Components

路径：`frontend/src/components/summary`

- `SummaryPanel.vue`：AI 总结工作区容器。
- `SummaryOverview.vue`：摘要、大纲、知识点、时间轴、术语和推荐问题。
- `SummaryTranscript.vue`：字幕或转写文本。
- `SummaryMindMap.vue`：思维导图渲染、缩放、全屏、SVG/PNG 下载。
- `SummaryQa.vue`：AI 问答输入、历史和额度提示。

### 前端工具模块

- `frontend/src/services/formats.js`：下载格式常量和格式选择。
- `frontend/src/services/authSession.js`：认证状态、会员标签和 quota meter 文案。
- `frontend/src/services/workspacePersistence.js`：浏览器本地工作区保存和恢复。
- `frontend/src/services/summaryExports.js`：Markdown、问答、字幕和文件下载工具。
- `frontend/src/utils/summaryStream.js`：流式总结预览行处理。
- `frontend/src/utils/mindMap.js`：思维导图数据归一化、布局、SVG 渲染和导出。
- `frontend/src/seo/pages.js`：SEO 页面、FAQ、平台页、功能页和 GEO 内容配置。

### Vite 配置

路径：`frontend/vite.config.js`

- 使用 Vue plugin。
- 使用 Tailwind CSS Vite plugin。
- 构建时替换 SEO site URL。
- 注入站长平台 verification meta。
- 开发服务器监听 `127.0.0.1:5173`。
- 将 `/api` 和 `/files` 代理到后端 `VITE_BACKEND_URL`，默认 `http://127.0.0.1:8000`。

## API 接口

### Health

```http
GET /api/health
```

返回：

```json
{
  "status": "ok",
  "service": "free-video-downloader"
}
```

### 视频解析

```http
POST /api/analyze
Content-Type: multipart/form-data
```

字段：

- `url`：必填，公开视频 URL。

返回示例：

```json
{
  "kind": "video",
  "id": "abc123",
  "title": "Example title",
  "webpage_url": "https://example.com/watch",
  "thumbnail": "/api/proxy/assets/asset-token",
  "duration": 120,
  "extractor": "youtube",
  "analysis_token": "analysis_123",
  "formats": [],
  "subtitles": [],
  "entries": []
}
```

说明：

- `kind` 为 `video` 或 `playlist`。
- playlist 会通过 `entries` 返回条目。
- thumbnail 会被重写为本地 asset proxy URL。
- `analysis_token` 有 30 分钟 TTL，用于后续下载和总结复用解析结果。

### 创建下载任务

```http
POST /api/download
Content-Type: application/json
```

请求示例：

```json
{
  "url": "https://example.com/watch",
  "analysis_token": "analysis_123",
  "entry_ids": ["abc123"],
  "format_id": "best",
  "subtitle_langs": ["en"],
  "write_auto_subs": false,
  "prefer_srt": true
}
```

返回：

```json
{
  "task_id": "task_123"
}
```

### 下载任务状态

```http
GET /api/tasks/{task_id}
```

返回示例：

```json
{
  "id": "task_123",
  "url": "https://example.com/watch",
  "status": "downloading",
  "progress": 42.5,
  "message": "Downloading",
  "speed": 2048000,
  "eta": 18,
  "download_url": null,
  "error": null
}
```

### 下载任务 SSE

```http
GET /api/tasks/{task_id}/events
```

事件类型：`task`

payload 与任务状态快照一致。

### 封面代理

```http
GET /api/proxy/assets/{token}
```

说明：

- token 只能由后端生成。
- 调用方不能传任意上游 URL。
- 后端请求上游封面时会带来源页 `Referer`。
- 未知 token 返回 404。
- 上游失败返回 502。
- 响应包含 `Cache-Control: private, max-age=3600`。

### 文件下载

```http
GET /files/{token}
```

说明：

- token 来自完成任务。
- 未知 token 返回 404。
- 不暴露服务器真实路径。

### CSRF

```http
GET /api/csrf
```

用于注册、登录和密码重置前获取 prelogin CSRF token。

### Auth

```http
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET  /api/me
POST /api/auth/password-reset/request
POST /api/auth/password-reset/confirm
```

说明：

- `register` 和 `login` 成功后返回用户、会员、用量和 session CSRF token。
- 前端必须使用 `credentials: "include"`。
- 前端不能直接读取 HttpOnly session cookie。
- `logout` 需要 session CSRF。
- `password-reset/request` 在开发模式下会返回 `reset_token`，生产环境不会。

### Entitlements

```http
GET /api/entitlements/status
```

需要登录。返回当前 plan、各 meter 用量和按量包余额。

核心 meter：

- `analyze`
- `download`
- `summary`
- `transcription_minutes`
- `question`

### Billing

```http
GET  /api/billing/status
POST /api/billing/checkout
POST /api/billing/checkout/confirm
POST /api/billing/portal
POST /api/billing/webhook
```

说明：

- `checkout` 支持 `purchase_type=subscription` 和 `purchase_type=credit_pack`。
- `checkout/confirm` 会查询 Stripe Checkout Session 并确认归属当前用户。
- `portal` 返回 Stripe Customer Portal URL。
- `webhook` 验证 Stripe 签名并幂等处理事件。
- `BILLING_MODE` 只支持 `stripe`。

### Summaries

```http
POST /api/summaries
GET  /api/summaries/{summary_id}
GET  /api/summaries/{summary_id}/events
GET  /api/summaries/{summary_id}/markdown
POST /api/summaries/{summary_id}/questions
```

`POST /api/summaries` 请求示例：

```json
{
  "url": "https://example.com/watch",
  "title": "Example title",
  "language": "zh-CN",
  "force": true,
  "duration": 120,
  "analysis_token": "analysis_123"
}
```

说明：

- 需要登录。
- 需要 session CSRF。
- 必须先解析视频。
- 免费版和 Pro 会执行不同的单视频时长限制。
- 没字幕且需要语音转写时，会预留转写分钟。
- 总结失败会退还额度。
- `events` 使用 SSE，事件类型为 `summary`。
- `questions` 会扣减本月 AI 问答额度，模型失败会退款。

## 账号、会员与额度

额度定义在 `backend/app/services/plan_catalog.py`。

### 未登录访客

- 每日解析：3 次。
- 每日下载：1 次。
- 单个下载视频最长：30 分钟。
- 不支持 AI 总结。
- 不支持语音转写。
- 不支持 AI 问答。

访客额度按 IP hash 记录，盐来自 `SAVEANY_IP_HASH_SALT`。生产环境必须替换为服务端随机值。

### 登录免费版

- 每日解析：30 次。
- 每日下载：10 次。
- 单个下载视频最长：60 分钟。
- 每日 AI 总结：默认 3 次，可由 `FREE_SUMMARY_DAILY_LIMIT` 覆盖。
- 单个 AI 总结视频最长：30 分钟。
- 每月语音转写：30 分钟。
- 每月 AI 问答：10 次。

### Pro 个人版

- 每月解析：300 次。
- 每月下载：100 次。
- 单个下载视频最长：180 分钟。
- 每月 AI 总结：120 次。
- 单个 AI 总结视频最长：120 分钟。
- 每月语音转写：600 分钟。
- 每月 AI 问答：200 次。
- 前端当前展示价格：`¥19/月`。

### 按量包

| 包 ID | 名称 | 类型 | 数量 | 有效期 | 前端价格标签 |
| --- | --- | --- | --- | --- | --- |
| `summary_small` | 总结小包 | AI 总结 | 20 次 | 90 天 | `¥6` |
| `summary_large` | 总结大包 | AI 总结 | 100 次 | 180 天 | `¥19` |
| `transcription_small` | 转写小包 | 语音转写 | 120 分钟 | 90 天 | `¥8` |
| `transcription_large` | 转写大包 | 语音转写 | 600 分钟 | 180 天 | `¥29` |

按量包只在套餐内额度不足时补充消耗。多个可用包会按过期时间和购买时间优先消耗。

## AI 总结与语音转写

### 文本总结模型

默认配置：

```dotenv
AI_PROVIDER=openai-compatible
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=
AI_TEXT_MODEL=gpt-4o-mini
AI_TIMEOUT_SECONDS=120
```

`AI_PROVIDER` 可选：

- `openai-compatible`
- `anthropic`
- `mock`

如果 `AI_PROVIDER=anthropic` 或 `AI_BASE_URL` 以 `/anthropic` 结尾，后端会使用 Anthropic-compatible Messages API。

### 语音转写模型

默认配置：

```dotenv
AI_TRANSCRIBE_PROVIDER=local-faster-whisper
AI_TRANSCRIBE_BASE_URL=
AI_TRANSCRIBE_API_KEY=
AI_TRANSCRIBE_MODEL=small
AI_TRANSCRIBE_DEVICE=cpu
AI_TRANSCRIBE_COMPUTE_TYPE=int8
AI_TRANSCRIBE_BEAM_SIZE=5
AI_TRANSCRIBE_VAD_FILTER=true
```

支持：

- `local-faster-whisper`
- `openai-compatible`
- `mock`
- 多 provider fallback，例如 `local-faster-whisper,openai-compatible`

本地 faster-whisper 需要额外安装：

```bash
cd backend
source .venv/bin/activate
pip install faster-whisper
```

### 总结输出内容

AI provider 被要求返回紧凑 JSON，至少包含：

- `overview`：一句话或一段概览。
- `outline`：章节大纲。
- `key_points`：核心知识点。
- `highlights`：带时间线的高光片段。
- `terms`：术语解释。
- `questions`：推荐继续追问的问题。
- `mind_map`：思维导图结构。
- `qa_pairs`：预置问答。

后端会把结果补充：

- `transcript_source`
- `language`
- `transcript_language`
- `transcript_text`
- `transcript_segments`

## 公开视频解析与下载

### 普通站点

普通站点由 `yt-dlp` 负责解析和下载。SaveAny 不重复实现平台协议，而是做这些封装：

- URL 清理。
- headers 构造。
- 格式选择策略。
- subtitle 归一化。
- playlist entries 归一化。
- 下载进度转成任务状态。
- 输出产物选择。
- 媒体校验。
- 用户友好的错误文案。

### YouTube

YouTube 相关处理：

- extractor args 使用 `android` 和 `web` player client。
- 分析时遇到短暂机器人校验会重试。
- 下载时对部分 403 或登录确认错误做 resumable retries。
- 默认格式优先稳定 MP4/H.264。

### Bilibili

Bilibili 相关处理：

- 默认格式最高优先到 720p MP4/H.264。
- 如果 `yt-dlp` metadata extraction 失败，会尝试 Bilibili public metadata fallback。
- 某些字幕 API 需要登录态。默认不读取 Cookie；本地自用可显式配置 `BILIBILI_COOKIE_FILE` 或 `BILIBILI_COOKIES_FROM_BROWSER` 供字幕提取使用。
- Bilibili 412 会转成公开视频边界提示。

### TikTok

TikTok 默认格式优先：

- MP4。
- H.264 / AVC。
- 带音频。
- 再退回到普通默认格式。

### 抖音

抖音默认只走公开视频解析：

```dotenv
DOUYIN_RESOLVER_CHAIN=f2,douyinvd,browser
DOUYIN_PUBLIC_ONLY=true
DOUYIN_F2_TIMEOUT_SECONDS=15
DOUYINVD_BASE_URL=
DOUYINVD_TIMEOUT_SECONDS=20
DOUYIN_BROWSER_TIMEOUT_MS=30000
DOUYIN_BROWSER_CHANNEL=chrome
```

可选依赖：

- 安装 `f2` 后启用主 resolver。
- 安装 Playwright 浏览器后启用 browser fallback：

```bash
cd backend
source .venv/bin/activate
python -m playwright install chromium
```

如果服务器上已有 Chrome，可以通过 `DOUYIN_BROWSER_CHANNEL=chrome` 使用本机 Chrome。

## GEO 与 SEO

SEO 内容来源主要在 `frontend/src/seo/pages.js`，生成脚本在 `frontend/scripts`。

当前静态内容包括：

- 平台页：YouTube、Bilibili、抖音、TikTok 等。
- 功能页：公开视频下载、AI 视频总结、字幕提取、思维导图。
- 用例页：课程学习、会议复盘、内容归档。
- 对比页和 FAQ。
- 文章页。
- pricing、privacy、terms、facts、sitemap 页面。
- 每个页面有 HTML 和 Markdown mirror。

常用命令：

```bash
cd frontend
npm run seo:generate
npm run seo:validate
npm run seo:validate:remote
npm run seo:indexnow:key
npm run seo:indexnow:dry-run
npm run seo:indexnow:submit
npm run seo:indexnow:submit:all
```

构建前需要设置正式域名：

```dotenv
PUBLIC_SITE_URL=https://your-domain.example
VITE_PUBLIC_SITE_URL=https://your-domain.example
```

FastAPI 自托管时可开启 canonical redirects：

```dotenv
SEO_CANONICAL_REDIRECTS=true
```

该跳转只影响前端 `GET` 和 `HEAD` 请求，不跳转 `/api` 和 `/files`。

GEO 访问日志：

```text
runtime/geo-access.jsonl
```

生成本地报告：

```bash
cd backend
./.venv/bin/python scripts/geo_monitor_report.py
```

## 运行时数据

默认运行时目录：

```text
runtime/
├── downloads
├── tmp
├── summaries
└── saveany.db
```

说明：

- `runtime/downloads`：下载任务输出目录。
- `runtime/tmp`：临时工作目录，后端退出时会清理。
- `runtime/summaries`：AI 总结任务、Markdown 和缓存索引。
- `runtime/saveany.db`：SQLite 数据库。
- `runtime/geo-access.jsonl`：GEO crawler 访问日志。

删除 `runtime` 会重置：

- 本地下载文件。
- 任务文件 token。
- 总结缓存。
- 用户账号。
- 登录 session。
- 会员状态。
- Stripe event 处理记录。
- 用量历史。
- 按量包余额。

## 本地开发

### 1. 准备系统依赖

需要安装：

- Python 3。
- Node.js `^20.19.0` 或 `>=22.12.0`。
- npm。
- ffmpeg 和 ffprobe。

macOS 可用 Homebrew：

```bash
brew install ffmpeg
```

### 2. 创建统一环境配置

在后端目录复制模板：

```bash
cp backend/.env.example backend/.env
```

本项目后端、AI、Stripe、SEO 和前端开发服务器配置都从 `backend/.env` 读取。部署平台注入的 shell 环境变量优先级高于 `backend/.env`。

### 3. 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

后端地址：

```text
http://127.0.0.1:8000
```

默认监听地址、端口和热重载可通过 `backend/.env` 中的 `SAVEANY_BACKEND_HOST`、`SAVEANY_BACKEND_PORT`、`SAVEANY_BACKEND_RELOAD` 调整。

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：

```text
http://127.0.0.1:5173
```

Vite 会把 `/api` 和 `/files` 代理到 `VITE_BACKEND_URL`，默认是 `http://127.0.0.1:8000`。

### 5. 本地 demo mode

可在 `backend/.env` 中开启：

```dotenv
SAVEANY_DEMO_MODE=true
AI_PROVIDER=mock
AI_TRANSCRIBE_PROVIDER=mock
```

然后使用 demo URL：

```text
https://demo.saveany.local/video
```

demo mode 会生成示例分析结果、示例下载占位文件和示例总结内容，适合本地 UI 验收。

## 环境变量

完整模板见 `backend/.env.example`。下面列出当前项目实际使用的主要配置。

### 运行时与安全

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SAVEANY_ENV` | `development` | 运行环境，只允许 `development` 或 `production`。 |
| `SAVEANY_DB_PATH` | `runtime/saveany.db` | SQLite 数据库路径。 |
| `SAVEANY_DEV_MODE` | `false` | 开发模式，开启后密码重置请求可返回 reset token。 |
| `SAVEANY_DEMO_MODE` | `false` | 本地演示模式。 |
| `SAVEANY_ALLOWED_ORIGINS` | 本地前端地址 | CSRF 同源校验允许来源。 |
| `SAVEANY_SECURE_COOKIES` | `false` | 生产环境必须为 `true`。 |
| `SAVEANY_SESSION_COOKIE` | `saveany_session` | session cookie 名。生产默认可用 `__Host-saveany_session`。 |
| `SAVEANY_SESSION_DAYS` | `30` | session 绝对有效天数。 |
| `SAVEANY_SESSION_IDLE_DAYS` | `7` | session 空闲有效天数。 |
| `SAVEANY_IP_HASH_SALT` | `saveany-local-ip-meter` | IP 和上下文哈希盐，生产必须替换。 |
| `PASSWORD_RESET_TOKEN_MINUTES` | `30` | 密码重置 token 有效分钟数。 |
| `AUTH_RATE_LIMIT_ATTEMPTS` | `5` | 认证相关限流次数。 |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | `300` | 认证相关限流窗口。 |
| `FREE_SUMMARY_DAILY_LIMIT` | `3` | 免费版每日 AI 总结额度。 |
| `SUMMARY_DRAFT_AUDIO_SECONDS` | `45` | 语音转写快速草稿截取秒数。 |

生产环境启动会强校验：

- `SAVEANY_SECURE_COOKIES=true`
- `SAVEANY_DEV_MODE=false`
- `PUBLIC_APP_URL` 必须是 HTTPS。
- `SAVEANY_ALLOWED_ORIGINS` 必须显式配置且不能为 `*`。
- 必须配置 Stripe secret key、webhook secret 和 Pro price id。

### 前端与公开 URL

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PUBLIC_APP_URL` | `http://localhost:5173` | 后端生成 Stripe 回跳和 portal 返回地址使用。 |
| `VITE_BACKEND_URL` | `http://127.0.0.1:8000` | Vite 开发代理后端地址。 |
| `PUBLIC_SITE_URL` | `https://your-domain.example` | SEO canonical 生产域名。 |
| `VITE_PUBLIC_SITE_URL` | `https://your-domain.example` | 前端构建时 SEO 域名。 |
| `SEO_CANONICAL_REDIRECTS` | `false` | FastAPI 自托管时是否启用 canonical redirect。 |

### AI 大模型

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AI_PROVIDER` | `openai-compatible` | 文本总结 provider。 |
| `AI_BASE_URL` | `https://api.openai.com/v1` | 文本模型 API 地址。 |
| `AI_API_KEY` | 空 | 服务端 AI key。 |
| `AI_TEXT_MODEL` | `gpt-4o-mini` | 文本总结模型名。 |
| `AI_TRANSCRIBE_PROVIDER` | `local-faster-whisper` | 语音转写 provider。 |
| `AI_TRANSCRIBE_BASE_URL` | 空 | 云端转写 API 地址，为空复用 `AI_BASE_URL`。 |
| `AI_TRANSCRIBE_API_KEY` | 空 | 云端转写 API key，为空复用 `AI_API_KEY`。 |
| `AI_TRANSCRIBE_MODEL` | `small` | 转写模型。 |
| `AI_TRANSCRIBE_DEVICE` | `cpu` | 本地转写设备。 |
| `AI_TRANSCRIBE_COMPUTE_TYPE` | `int8` | 本地转写计算类型。 |
| `AI_TRANSCRIBE_BEAM_SIZE` | `5` | faster-whisper beam size。 |
| `AI_TRANSCRIBE_VAD_FILTER` | `true` | 是否启用 VAD 静音过滤。 |
| `AI_TIMEOUT_SECONDS` | `120` | AI 请求超时时间。 |

### Stripe

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `BILLING_MODE` | `stripe` | 只支持 `stripe`。 |
| `STRIPE_SECRET_KEY` | 示例值 | Stripe secret key。 |
| `STRIPE_WEBHOOK_SECRET` | 示例值 | Stripe CLI 或 Dashboard webhook secret。 |
| `STRIPE_PRO_MONTHLY_PRICE_ID` | 示例值 | Pro 月付 recurring price id。 |
| `STRIPE_SUMMARY_SMALL_PACK_PRICE_ID` | 示例值 | 总结小包 one-time price id。 |
| `STRIPE_SUMMARY_LARGE_PACK_PRICE_ID` | 示例值 | 总结大包 one-time price id。 |
| `STRIPE_TRANSCRIPTION_SMALL_PACK_PRICE_ID` | 示例值 | 转写小包 one-time price id。 |
| `STRIPE_TRANSCRIPTION_LARGE_PACK_PRICE_ID` | 示例值 | 转写大包 one-time price id。 |

### 公共视频解析

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DOUYIN_RESOLVER_CHAIN` | `f2,douyinvd,browser` | 抖音 resolver 顺序。 |
| `DOUYIN_PUBLIC_ONLY` | `true` | 是否强制抖音走公开视频路径。 |
| `DOUYIN_F2_TIMEOUT_SECONDS` | `15` | F2 resolver 超时。 |
| `DOUYINVD_BASE_URL` | 空 | douyinVd sidecar 地址。 |
| `DOUYINVD_TIMEOUT_SECONDS` | `20` | douyinVd resolver 超时。 |
| `DOUYIN_BROWSER_TIMEOUT_MS` | `30000` | Playwright browser resolver 超时。 |
| `DOUYIN_BROWSER_CHANNEL` | `chrome` | Playwright browser channel。 |
| `BILIBILI_COOKIE_FILE` | 空 | 本地自用 Bilibili 字幕 Cookie 文件。 |
| `BILIBILI_COOKIES_FROM_BROWSER` | 空 | 让 yt-dlp 从浏览器读取 Bilibili Cookie。 |

### 站长平台与 IndexNow

支持的 verification 变量：

- `GOOGLE_SITE_VERIFICATION`
- `BING_SITE_VERIFICATION`
- `BAIDU_SITE_VERIFICATION`
- `SO_SITE_VERIFICATION`
- `QIHOO_SITE_VERIFICATION`
- `SOGOU_SITE_VERIFICATION`
- `YANDEX_SITE_VERIFICATION`

支持 verification file：

- `GOOGLE_SITE_VERIFICATION_FILE`
- `GOOGLE_SITE_VERIFICATION_FILE_CONTENT`
- `BING_SITE_VERIFICATION_FILE`
- `BING_SITE_VERIFICATION_FILE_CONTENT`
- `BAIDU_SITE_VERIFICATION_FILE`
- `BAIDU_SITE_VERIFICATION_FILE_CONTENT`
- `SO_SITE_VERIFICATION_FILE`
- `SO_SITE_VERIFICATION_FILE_CONTENT`
- `QIHOO_SITE_VERIFICATION_FILE`
- `QIHOO_SITE_VERIFICATION_FILE_CONTENT`
- `SOGOU_SITE_VERIFICATION_FILE`
- `SOGOU_SITE_VERIFICATION_FILE_CONTENT`
- `YANDEX_SITE_VERIFICATION_FILE`
- `YANDEX_SITE_VERIFICATION_FILE_CONTENT`

IndexNow：

- `INDEXNOW_KEY`
- `INDEXNOW_KEY_FILE`
- `INDEXNOW_KEY_LOCATION`
- `INDEXNOW_ENDPOINT`
- `INDEXNOW_STATE_FILE`
- `INDEXNOW_DRY_RUN`

## Stripe 联调

### 1. 创建 Stripe Price

在 Stripe test mode 中创建：

- `SaveAny Pro`：月度 recurring Price，`¥19`，currency `cny`。
- `总结小包`：one-time Price，`¥6`，currency `cny`。
- `总结大包`：one-time Price，`¥19`，currency `cny`。
- `转写小包`：one-time Price，`¥8`，currency `cny`。
- `转写大包`：one-time Price，`¥29`，currency `cny`。

### 2. 填写 `backend/.env`

```dotenv
BILLING_MODE=stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRO_MONTHLY_PRICE_ID=price_...
STRIPE_SUMMARY_SMALL_PACK_PRICE_ID=price_...
STRIPE_SUMMARY_LARGE_PACK_PRICE_ID=price_...
STRIPE_TRANSCRIPTION_SMALL_PACK_PRICE_ID=price_...
STRIPE_TRANSCRIPTION_LARGE_PACK_PRICE_ID=price_...
PUBLIC_APP_URL=http://127.0.0.1:5173
```

### 3. 启动 Stripe CLI

```bash
stripe listen --forward-to http://127.0.0.1:8000/api/billing/webhook
```

把输出的 `whsec_...` 写入 `STRIPE_WEBHOOK_SECRET`，然后重启后端。

### 4. 本地验收

1. 启动后端和前端。
2. 注册或登录账号。
3. 打开套餐页。
4. 点击 `开通 Pro ¥19/月`。
5. 使用 Stripe test card 完成支付。
6. 回到 SaveAny，等待前端确认和 webhook 同步。
7. 查看账号菜单和账单状态中的额度变化。
8. 购买按量包并确认余额同步。

## 测试与验证

当前测试覆盖：

- 后端 pytest 测试文件：25 个。
- 前端 node:test 测试文件：11 个。

### 后端测试

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

常见聚焦测试：

```bash
cd backend
python -m pytest tests/test_api.py -q
python -m pytest tests/test_summary_api.py -q
python -m pytest tests/test_usage_meter.py -q
python -m pytest tests/test_billing_stripe_webhook.py -q
python -m pytest tests/test_auth_api.py -q
python -m pytest tests/test_ytdlp_service.py -q
```

### 前端测试

```bash
cd frontend
npm test
```

当前前端测试覆盖：

- 认证 session。
- summary API client。
- SEO metadata。
- `backend/.env` 读取。
- mind map 工具。
- summary exports。
- formats。
- workspace persistence。
- 中文 UI 文案。
- summary auto layout。
- summary stream。

### 前端构建

```bash
cd frontend
npm run build
```

`prebuild` 会自动执行：

```bash
node scripts/generate-seo-assets.mjs
```

### SEO 验证

```bash
cd frontend
npm run seo:generate
npm run seo:validate
```

部署后：

```bash
cd frontend
npm run seo:validate:remote
```

### 手动浏览器验收建议

1. 启动后端。
2. 启动前端。
3. 打开 `http://127.0.0.1:5173`。
4. 使用 demo mode 或真实公开视频 URL 解析。
5. 检查封面、标题、格式、播放列表数量。
6. 创建下载任务，观察 SSE 进度和完成下载。
7. 注册账号，登录。
8. 创建 AI 总结，观察字幕、转写、快速版、流式预览和最终结果。
9. 切换总结、字幕、思维导图和 AI 问答。
10. 导出 Markdown、SVG、PNG。
11. 打开套餐页，检查免费版、Pro 和按量包显示。
12. 在 Stripe test mode 下走一次订阅和按量包支付。

## 部署说明

### 本地或单机自托管

推荐流程：

1. 在服务器创建 `backend/.env`，或通过部署平台注入同名环境变量。
2. 设置 `SAVEANY_ENV=production`。
3. 设置 `SAVEANY_SECURE_COOKIES=true`。
4. 设置 HTTPS `PUBLIC_APP_URL`。
5. 设置明确的 `SAVEANY_ALLOWED_ORIGINS`。
6. 设置真实 `SAVEANY_IP_HASH_SALT`。
7. 设置 AI 和 Stripe 密钥。
8. 构建前端：

```bash
cd frontend
npm install
npm run build
```

9. 启动 FastAPI：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

10. 通过 Nginx、Caddy、Traefik 或平台反向代理暴露 HTTPS。

FastAPI 会在 `frontend/dist` 存在时服务构建后的前端：

- `/assets/*` 使用长缓存。
- HTML 使用 no-cache。
- `.md`、`.txt`、`.xml` 使用短缓存。
- 目录页缺少尾斜杠时返回 308。
- 未知前端路径返回 `404.html`。

### 生产前必须关注

- HTTPS。
- Secure cookie。
- 强随机 `SAVEANY_IP_HASH_SALT`。
- 严格 allowed origins。
- Stripe webhook secret。
- AI key 不进入前端和日志。
- 下载文件生命周期。
- 公开部署限流和滥用防护。
- 任务并发和队列隔离。
- 平台条款和版权合规。
- SMTP 或邮件服务，当前密码重置只实现 token 生成和确认，生产发信需要接入。

## 安全与合规边界

### 已实现的安全措施

- 不向浏览器暴露真实文件路径。
- 文件下载通过后端 token。
- 远程封面通过后端生成的 asset token 代理，不开放任意 URL 代理。
- 账号密码使用 Argon2。
- session token、reset token 和 CSRF token 存储哈希。
- session cookie 为 HttpOnly。
- 生产环境要求 secure cookies。
- 写操作使用 CSRF token。
- 写操作做同源校验。
- 认证相关接口有限流。
- Stripe webhook 使用签名校验。
- Stripe event id 幂等。
- Stripe Checkout Session 确认会校验归属当前用户。
- Billing mock 接口已移除。
- AI 总结任务按用户隔离。
- 总结问答只能读取当前用户拥有的 summary。
- 失败任务清理临时文件。
- GEO 日志不记录 IP 和 query string。

### 明确不支持

- DRM 绕过。
- 付费内容绕过。
- 私密视频下载。
- 登录限定视频下载。
- 验证码绕过。
- 地区限制绕过。
- 平台风控绕过。
- 浏览器手动 Cookie 输入。
- 二维码登录。
- 共享账号池。
- 公开代理任意远程资源。

### Cookie 说明

项目默认不使用用户 Cookie。只有 Bilibili 字幕提取在本地自用部署时支持显式服务端配置：

- `BILIBILI_COOKIE_FILE`
- `BILIBILI_COOKIES_FROM_BROWSER`

这类配置属于敏感登录凭据。只建议在个人本地环境使用，不应提交到仓库，也不应在公共服务中要求用户提供。

## 已知限制

- 下载任务状态保存在内存中，服务重启后历史任务不可恢复。
- 文件 token 保存在内存中，服务重启后旧 token 不可用。
- 下载任务由本地线程处理，没有持久化队列。
- 当前没有全局下载并发控制。
- 当前没有任务取消接口。
- 当前没有下载失败重试按钮。
- 播放列表当前由前端把所有 entries 创建为任务，未提供精细条目选择 UI。
- 后端下载接口支持字幕参数，但当前前端下载面板没有开放字幕语言选择入口。
- 总结缓存保存在本地文件系统，多实例部署需要共享存储或数据库改造。
- SQLite 适合本地和单机自托管，多实例生产需要迁移到 Postgres 等数据库。
- 完成下载只保留最近少量目录，长期归档需要对象存储或明确的文件生命周期策略。
- AI 总结依赖外部模型或本地转写模型，未配置时会失败或只能使用 mock。
- 无字幕视频转写依赖 ffmpeg 和转写 provider。
- 抖音、YouTube、Bilibili 等平台可能因风控、地区、登录态和网络环境变化导致公开视频偶发失败。
- 生产密码重置发信尚需接入邮件服务。
- 公开部署仍需更强滥用防护、审计、告警、队列隔离和法律合规审查。

## 文档索引

建议阅读顺序：

1. `docs/01-requirements.md`：最初需求、MVP 范围和安全要求。
2. `docs/02-product-design.md`：产品定位和核心用户流程。
3. `docs/03-technical-architecture.md`：前后端、存储、安全和未来架构。
4. `docs/04-api-design.md`：API 设计和响应结构。
5. `docs/05-ui-design-system.md`：Industrial Media Console 视觉方向。
6. `docs/06-implementation-plan.md`：初始阶段计划。
7. `docs/07-extension-guide.md`：未来扩展建议。
8. `docs/08-feature-summary.md`：当前公开视频下载和 AI 总结功能总结。
9. `docs/09-ai-configuration.md`：AI 与语音转写配置。
10. `docs/10-seo-deployment-checklist.md`：SEO、站长验证和 IndexNow 部署。
11. `docs/11-membership-stripe-setup.md`：会员、Stripe 和按量包配置。

架构图：

- `docs/diagrams/system-architecture.md`
- `docs/diagrams/download-flow.md`
- `docs/diagrams/frontend-modules.md`

历史设计和执行计划：

- `docs/superpowers/specs/*`
- `docs/superpowers/plans/*`

这些文件记录了 AI 视频总结、思维导图导出、会员 Stripe、个人额度、登录安全、SEO、Checkout 回跳确认、AI 问答月度额度等功能的设计和实现过程。
