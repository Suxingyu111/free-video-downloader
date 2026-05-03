# 万能视频下载功能总结

## 当前状态

万能视频下载功能已经完成 MVP 闭环：用户粘贴公开视频链接后，可以解析视频信息、选择下载格式、创建后台下载任务、实时查看进度，并通过临时文件令牌保存下载结果。系统定位为本地或自托管工具，优先服务学习、归档、字幕提取和个人资料整理场景。

本功能不提供登录态托管、手动 Cookie 上传、二维码登录、DRM 绕过、付费内容绕过或平台安全策略绕过能力。遇到私密、登录限定、地区限制、验证码、短链失效或平台风控场景时，系统会以公开视频边界提示失败。

## 已完成能力

- 视频链接解析：通过 `POST /api/analyze` 获取标题、封面、时长、来源站点、可选格式、字幕轨道、播放列表条目和后续下载使用的 `analysis_token`。
- 主流站点下载：普通站点统一由 `yt-dlp` 承担解析和下载，避免重复实现各平台协议细节。
- 抖音公开视频下载：通过 F2、douyinVd 兼容解析、浏览器抓取三段式 resolver chain 提高公开视频解析成功率。
- 下载任务管理：后端创建内存任务，前端通过 SSE 和轮询兜底同步任务状态。
- 下载进度展示：任务状态覆盖 `queued`、`downloading`、`processing`、`completed`、`failed`，并返回进度、速度、ETA、错误信息和下载入口。
- 文件安全交付：完成文件只通过后端生成的临时 token 暴露，不向浏览器泄露服务器真实路径。
- 缩略图代理：远程封面被转换为 `/api/proxy/assets/{token}`，后端带来源 `Referer` 代理请求，减少前端热链失败。
- 格式选择：前端提供“稳定 MP4（推荐）”和“原始最高画质”，后端针对 Bilibili、TikTok、YouTube 等场景调整默认格式策略。
- 输出校验：下载完成后使用 `ffprobe` 检查媒体流，避免把缺失音频、缺失视频或不兼容的 MP4 误报为成功。
- 运行时清理：启动时和任务完成后清理临时下载碎片，只保留最近的完成目录，失败任务会清理临时文件。
- 个人透明额度：未登录访客、登录免费版和 Pro 个人版分别执行解析、下载、AI 总结、语音转写和 AI 追问额度；额度不够时可购买 AI 总结次数包或语音转写分钟包。

## 用户流程

1. 用户在前端输入 YouTube、Bilibili、抖音、TikTok 等公开视频链接。
2. 前端调用 `/api/analyze`，展示封面、标题、时长、格式选项和播放列表数量，并保存 `analysis_token`。
3. 用户选择格式并点击下载。
4. 前端调用 `/api/download`，携带 `analysis_token` 创建后台任务。
5. 后端在线程中执行下载，持续写入任务进度。
6. 前端通过 `/api/tasks/{task_id}/events` 接收 SSE 事件，同时每秒轮询 `/api/tasks/{task_id}` 作为兜底。
7. 任务完成后，前端展示保存按钮，用户通过 `/files/{token}` 下载文件。

## 技术闭环

### 前端

- 技术栈：Vue 3、Vite、Tailwind CSS、lucide-vue-next。
- 入口：`frontend/src/App.vue`。
- API 客户端：`frontend/src/services/api.js`。
- 格式常量：`frontend/src/services/formats.js`。
- 体验重点：单页下载控制台、中文状态提示、解析和下载状态联动、SSE 断开时轮询兜底。

### 后端

- 技术栈：FastAPI、yt-dlp、httpx、Playwright、pytest。
- API 入口：`backend/app/main.py`。
- 下载服务：`backend/app/services/ytdlp_service.py`。
- 抖音公开视频 resolver：`backend/app/services/douyin_public_resolver.py` 和 `backend/app/services/douyin_browser_service.py`。
- 任务状态：`backend/app/services/task_store.py`。
- 运行时清理：`backend/app/services/runtime_cleanup.py`。
- 资源代理：`backend/app/services/asset_store.py`。

## API 面

- `GET /api/health`：服务健康检查。
- `POST /api/analyze`：解析公开视频 URL，返回标准化视频或播放列表信息和 `analysis_token`。
- `POST /api/download`：携带 URL、格式、播放列表条目和可选 `analysis_token` 创建下载任务，返回 `task_id`。
- `GET /api/tasks/{task_id}`：读取任务快照。
- `GET /api/tasks/{task_id}/events`：以 Server-Sent Events 推送任务状态变化。
- `GET /api/proxy/assets/{token}`：代理封面等远程媒体资源。
- `GET /files/{token}`：下载已完成文件。
- `GET /api/entitlements/status`：读取当前登录用户的个人套餐、解析/下载/总结/转写用量和按量包余量。

## 抖音解析策略

抖音走公开视频专用链路，默认顺序由 `DOUYIN_RESOLVER_CHAIN=f2,douyinvd,browser` 控制。

- F2 resolver：可用时优先，动态导入 `f2` 包，不强制作为项目依赖。
- douyinVd resolver：支持自托管 sidecar，也支持从公开页面提取播放地址。
- Browser resolver：使用 Playwright 在公开页面捕获 `aweme/detail` 响应，作为最后兜底。

`DOUYIN_PUBLIC_ONLY` 默认开启，确保抖音不会进入需要 Cookie 的路径。所有 resolver 都失败时，统一返回公开视频边界提示。

## 安全与边界

- 不接受手动 Cookie 字段，API contract 已通过测试约束。
- 不向前端返回真实文件路径，只返回文件 token。
- 不开放任意 URL 代理，封面代理 token 只能由后端注册生成。
- 默认只保留少量完成下载目录，降低本地磁盘膨胀风险。
- 仅面向本地或自托管环境；若公开部署，需要补齐认证、限流、任务隔离、文件生命周期策略和合规审查。

## 配置项

- `DOUYIN_RESOLVER_CHAIN`：抖音 resolver 顺序，默认 `f2,douyinvd,browser`。
- `DOUYINVD_BASE_URL`：可选的 douyinVd sidecar 地址。
- `DOUYIN_PUBLIC_ONLY`：是否强制抖音走公开视频路径，默认 `true`。
- `DOUYIN_F2_TIMEOUT_SECONDS`：F2 resolver 超时时间。
- `DOUYINVD_TIMEOUT_SECONDS`：douyinVd resolver 超时时间。
- `DOUYIN_BROWSER_TIMEOUT_MS`：Playwright 浏览器解析超时时间。
- `DOUYIN_BROWSER_CHANNEL`：浏览器 channel，默认 `chrome`。
- `SAVEANY_IP_HASH_SALT`：匿名访客解析/下载额度的 IP 哈希盐，生产环境必须替换为服务端随机值。
- `STRIPE_PRO_MONTHLY_PRICE_ID`：Pro 个人版月付订阅 Price ID。
- `STRIPE_SUMMARY_SMALL_PACK_PRICE_ID`、`STRIPE_SUMMARY_LARGE_PACK_PRICE_ID`：AI 总结次数包 Price ID。
- `STRIPE_TRANSCRIPTION_SMALL_PACK_PRICE_ID`、`STRIPE_TRANSCRIPTION_LARGE_PACK_PRICE_ID`：语音转写分钟包 Price ID。
- 个人额度目录：`backend/app/services/plan_catalog.py` 定义匿名访客、免费版、Pro 个人版和按量包的额度、有效期和价格标签。

## 已覆盖验证

- 后端 API 健康检查、封面 token 重写、无 Cookie API contract、YouTube 临时机器人校验重试。
- yt-dlp 服务的格式选择、URL 清洗、输出文件选择、媒体流校验和错误文案。
- 抖音 resolver 的 F2 标准化、无 Cookie 调用、resolver chain fallback、失败边界文案。
- 任务存储、文件 token、运行时清理策略。
- 账号注册/登录/退出、`/api/me` 会员摘要、`/api/entitlements/status` 个人额度和按量包余量。
- 匿名访客解析/下载限额、登录免费额度、Pro 月度 AI 总结与语音转写额度、单视频时长限制。
- Stripe Checkout、Customer Portal、webhook 验签、事件幂等和乱序处理，包括 Pro 订阅和按量包购买；本地 mock billing 状态修改接口已移除。
- AI 总结登录校验、个人额度扣减、按量包消耗、失败退款和重启后中断任务退款。
- 前端格式常量、中文 UI 文案、个人套餐页、按量包卡片、账号菜单和账单区 quota meter。

建议交付前执行：

```bash
cd backend
./.venv/bin/python -m pytest

cd ../frontend
npm test
npm run build
```

## 已知限制

- 任务和文件 token 当前保存在内存中，服务重启后历史任务不可恢复。
- 下载任务由本地线程处理，没有队列、并发限额或持久化重试。
- 播放列表当前以前端全选条目创建任务，尚未提供细粒度条目选择界面。
- 字幕能力后端已保留参数，但当前前端没有开放字幕语言选择入口。
- 抖音、YouTube、Bilibili 等平台可能因风控、地区、登录态和网络环境变化导致公开视频偶发失败。
- 生产公开部署仍需要更强限流、隔离队列、日志脱敏、文件保留策略、SMTP 发信和法律合规审查。

## 后续演进方向

- 如需多实例部署，引入 Postgres 保存账号、会员、任务历史、文件元数据和用户配置。
- 使用 Redis/RQ/Celery 等队列系统承载可恢复的后台任务。
- 增加播放列表条目选择、字幕语言选择、自动字幕下载和字幕格式转换 UI。
- 增加下载并发控制、任务取消、失败重试和更细的错误分类。
- 抽象本地存储与对象存储，支持更清晰的文件生命周期。
- 在公开部署前补齐生产级审计、告警、发信、风控和平台合规策略。
