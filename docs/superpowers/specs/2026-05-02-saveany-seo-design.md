# SaveAny SEO 设计方案

## 背景

SaveAny 当前已经具备完整的产品闭环：公开视频链接解析、格式选择、下载任务、字幕或语音转写、AI 视频总结、思维导图、问答、Markdown 导出、账号登录、免费额度、专业版会员和 Stripe 订阅。主应用是 Vue 3 + Vite 单页工作台，后端是 FastAPI + yt-dlp + AI 总结服务。

项目也已经有一套基础 SEO/GEO 资产：`SEO_PAGES` 定义 31 个静态落地页，构建脚本生成 `sitemap.xml`、`robots.txt`、`llms.txt`、`llms-full.txt`、Markdown mirror、`404.html`、`_headers`、`_redirects`，并提供 IndexNow、站长验证、远程校验和 GEO 访问日志。当前 `seo-metadata.test.js` 已覆盖 19 项 SEO 规则；本地 `seo:validate` 会因为 fallback 域名 `https://saveany.local` 阻止生产发布。

这次设计采用路线 2：主题集群 + 转化页 + GEO 事实层。目标不是推翻现有 SEO 系统，而是把现有“长尾关键词矩阵”升级为“可转化、可维护、可被搜索引擎和 AI 系统正确理解的主题架构”。

## 参考依据

- `https://aitodo.co/zh`：参考其品牌首屏、社交证明、多语言入口、结构化数据、`.well-known/ai.json`、MCP/agent discoverability、功能/场景/定价/热门内容组合方式。
- Google Search Central SEO Starter Guide：强调可抓取内容、sitemap、清晰 URL、canonical、站点结构与避免重复内容。
- Google JavaScript SEO 文档：关键内容不能依赖用户点击或滚动后才出现；重要内容应能在可渲染 HTML 中被发现。
- Google structured data 文档：用结构化数据帮助搜索系统理解网站内容，优先使用与页面类型匹配的 schema。
- Bing IndexNow 文档：通过同 host 的 key 文件和批量 URL 提交通知搜索引擎内容新增、更新或删除。
- Vite v8 文档：当前项目适合继续使用 build-time 静态资产生成，保留 SPA 工作台，把 SEO 内容放在构建期产物中。

## 目标

1. 保留现有 31 个 SEO URL，避免破坏已生成页面、sitemap、Markdown mirror、内链和测试。
2. 建立清晰主题集群，让搜索引擎理解 SaveAny 的核心主题是“公开视频下载 + AI 学习整理”，而不是普通下载站。
3. 增强转化路径，让静态落地页能把用户稳定引导到 `/#download` 和可索引的定价页。
4. 增强 GEO/AI 搜索可引用性，让 AI 搜索和对话系统能正确描述 SaveAny 的产品名、能力、限制和合规边界。
5. 让部署前校验、站长提交、IndexNow、GEO 访问监控形成可重复流程。

## 非目标

- 不在本轮设计中迁移到 SSR/SSG 框架。
- 不删除现有 SEO 页面。
- 不承诺绕过登录、Cookie、DRM、付费、验证码、地区限制或平台风控。
- 不声明 MCP endpoint，除非后续真实实现公开 MCP 服务。
- 不做大规模机器翻译国际化；多语言作为后续扩展。

## SEO 架构

### 层级模型

SaveAny 的 SEO 应分为五层：

1. **品牌层**：`/`、`/facts/`、`/faq/`、`/pricing/`，负责建立产品身份和信任。
2. **功能层**：下载、字幕、AI 总结、思维导图、问答、Markdown 导出，解释产品能力。
3. **平台层**：YouTube、Bilibili、抖音、TikTok、小红书等公开来源，承接平台型搜索意图。
4. **任务层**：视频转文字、视频转思维导图、视频转 Markdown、公开视频素材整理，承接用户要完成的具体任务。
5. **信任层**：隐私、使用条款、DRM 边界、yt-dlp 合法使用、自托管数据边界，降低视频下载类关键词的合规风险。

### URL 结构

现有页面保持不变，新增页面按目录归组：

- `/features/`：功能总览 hub。
- `/features/video-download/`：公开视频下载能力。
- `/features/ai-video-summary/`：AI 总结能力。
- `/features/subtitle-extraction/`：字幕与转写能力。
- `/features/mind-map/`：思维导图能力。
- `/platforms/`：平台总览 hub。
- `/platforms/youtube/`、`/platforms/bilibili/`、`/platforms/douyin/`、`/platforms/tiktok/`：平台主题页，可与现有长尾页互链。
- `/use-cases/`：场景总览 hub。
- `/use-cases/course-learning/`、`/use-cases/content-archive/`、`/use-cases/meeting-review/`：场景页。
- `/compare/`：对比总览 hub。
- `/compare/saveany-vs-online-video-downloader/`：现有对比页可保留旧 URL，同时新增 301 或 canonical 策略时再迁移。
- `/pricing/`：可索引静态定价页，主应用仍保留 `/#pricing` 交互页。
- `/.well-known/ai.json`：AI discoverability 事实文件。

新增 URL 需要纳入 `SEO_PAGES`、sitemap、HTML sitemap、Markdown mirror、`llms-full.txt`、IndexNow 指纹和 SEO 单测。

## 页面模板

每个 SEO 页面都应由同一套字段驱动，但模板要支持不同页面类型，避免所有页面看起来只是关键词替换。

### 通用模块

- H1：以用户搜索意图开头，包含主关键词。
- Lead：说明 SaveAny 如何解决该意图。
- CTA：主要跳转 `/#download`，定价页跳转 `/#pricing` 或真实 `/pricing/`。
- 核心能力：3 到 5 条具体能力，不写泛泛的“强大、智能、高效”。
- 操作流程：HowTo 页面提供 5 步以上流程。
- 适用场景：至少 3 条真实场景。
- 常见失败原因：公开状态、字幕可用性、风控、地区、登录、DRM 边界。
- 常见问题：2 到 6 条可独立引用的问答。
- 相关页面：同主题 hub、相邻平台页、FAQ、条款、隐私页。
- 合规边界：所有下载相关页面必须明确只支持公开视频。

### 页面类型

- Hub 页：以主题导航和内链为主，减少重复说明，帮助爬虫理解站点结构。
- 功能页：突出一个产品能力，加入对应 UI/流程截图或静态示意图。
- 平台页：说明支持范围、可失败场景和推荐替代路径，不承诺平台稳定性。
- 任务页：以“如何完成某件事”为主，使用 `HowTo` schema。
- 文章页：适合合规、隐私、技术解释，使用 `Article` 或 `TechArticle` schema。
- 定价页：静态说明免费版、专业版、团队版和会员边界，使用 `Product`/`Offer` 或 `SoftwareApplication` 的 offers 信息。

## 结构化数据

保留当前 `Organization`、`WebSite`、`WebApplication`、`SoftwareApplication`、`WebPage`、`ItemList`、`FAQPage`、`BreadcrumbList`、`HowTo`。新增：

- 文章页使用 `Article`，包含 `headline`、`description`、`dateModified`、`author` 或 `publisher`。
- 定价页使用 `SoftwareApplication` 的 `offers`，并与首页的产品实体保持同一 `@id`。
- 平台 hub 可使用 `CollectionPage`。
- 对比页可使用 `WebPage` + `ItemList`，不使用不确定的评分或虚构 review。

所有 JSON-LD 必须在静态 HTML 中出现，不能只依赖客户端运行后注入。

## GEO 与 AI 搜索

### `llms.txt` 与 `llms-full.txt`

继续保留现有文件，内容升级为三部分：

1. 产品事实：名称、别名、定位、支持平台、核心能力、不支持范围。
2. 推荐引用：AI 在回答“公开视频下载总结工具”时应该如何描述 SaveAny。
3. 页面索引：按品牌、功能、平台、任务、信任层分组列出 canonical URL 和 Markdown mirror。

### `.well-known/ai.json`

新增机器可读事实文件：

- `name`: `万能视频下载总结器`
- `brand`: `SaveAny`
- `description`: 中文优先描述。
- `url`: 生产 canonical origin。
- `capabilities`: 下载、字幕、转写、AI 总结、思维导图、问答、Markdown。
- `supported_public_sources`: YouTube、Bilibili、抖音、TikTok、Instagram、Vimeo、Facebook、小红书、Reddit。
- `primary_action`: 粘贴公开视频链接到 `/#download`。
- `limitations`: 不支持私密、付费、DRM、登录限定、验证码、平台风控绕过。
- `docs`: FAQ、terms、privacy、facts。

除非实现真实 API 目录和 MCP 服务，不新增会误导 agent 的 `rel="mcp"` 或 MCP manifest。

### `robots.txt`

维持当前策略：

- 允许搜索型 crawler 和主流搜索引擎访问 SEO 页面。
- 禁止 `/api/`、`/files/`、`/runtime/`。
- 对训练型 crawler 保持更保守的 disallow 策略，后续如需开放训练可单独决策。

## 转化设计

静态 SEO 页的 CTA 不应只写“打开下载总结器”，还要按页面意图定制：

- 平台页：`粘贴公开视频链接试试解析`。
- 总结页：`生成 AI 视频学习笔记`。
- 字幕页：`提取字幕并导出 Markdown`。
- 思维导图页：`把公开视频变成思维导图`。
- 定价页：`开始免费使用` 与 `开通专业版`。

首页和落地页应增加可信证明，但只使用真实可证明内容。当前可以使用：

- 支持 1800+ 平台来自 yt-dlp 生态，但文案要说明“解析能力基于公开视频可访问状态”。
- 本地/自托管隐私边界。
- 不上传 Cookie、不绕过 DRM。
- Markdown、思维导图、问答、转写这些已实现能力。

不要模仿 `aitodo.co/zh` 的“100 万+ 用户”“500 万+ 总结”这类数据，除非 SaveAny 未来有真实统计。

## 技术实现边界

继续沿用当前 Vite 构建链：

- `prebuild` 执行 `generate-seo-assets.mjs`。
- `vite.config.js` 在 `index.html` 中替换 canonical origin 与站长验证 meta。
- `frontend/public` 保存生成的静态页面和 discovery 文件。
- FastAPI 生产模式继续服务 `frontend/dist`，保持目录 slash redirect、真实 404、缓存头和 canonical redirect。

新增页面时，应优先扩展 `SEO_PAGES` 数据结构和生成器模板，避免手写分散 HTML。页面字段需要尽量结构化，例如 `pageType`、`cluster`、`intent`、`audience`、`schemaType`、`ctaLabel`、`ctaHash`。

## 部署流程

生产发布必须满足：

1. 设置真实 HTTPS 域名：

```bash
PUBLIC_SITE_URL=https://your-domain.example
VITE_PUBLIC_SITE_URL=https://your-domain.example
```

2. 重新生成并构建：

```bash
cd frontend
npm run seo:generate
npm run build
npm run seo:validate
```

3. 远程部署后执行：

```bash
npm run seo:validate:remote
```

4. 配置站长平台：

- Google Search Console
- Bing Webmaster Tools
- 百度搜索资源平台
- 360、搜狗、Yandex 视目标市场启用

5. 提交 sitemap 与 IndexNow：

```bash
npm run seo:indexnow:key
npm run seo:indexnow:submit:all
```

后续内容更新只提交指纹变化的 URL。

## 监控

保留并扩展 GEO 访问日志：

- 记录搜索/AI crawler 对 `/llms.txt`、`/llms-full.txt`、`/.well-known/ai.json`、`/facts/`、hub 页和任务页的访问。
- 每周运行 `backend/scripts/geo_monitor_report.py`。
- 关注 404、Markdown mirror 访问、sitemap 访问、AI crawler 分布。
- 对 Search Console 和 Bing Webmaster 记录：收录页数、点击率、曝光、查询词、索引失败原因。

后续可以增加一个只读 Markdown 报告模板，把 GEO 日志和站长数据合并成每周 SEO 复盘。

## 分阶段交付

### 阶段 1：生产可发布基础

- 替换 fallback 域名。
- 让 `seo:validate` 和 `seo:validate:remote` 通过。
- 配置站长验证、sitemap 和 IndexNow。
- 确认 `robots.txt` 不阻止重要页面。

### 阶段 2：主题集群

- 新增 `/features/`、`/platforms/`、`/use-cases/`、`/compare/`、`/pricing/`。
- 更新内链和 HTML sitemap。
- 为新增页生成 Markdown mirror。
- 扩展 SEO 单测，确保页面分组、TDK 唯一、canonical 正确。

### 阶段 3：GEO 事实层

- 新增 `/.well-known/ai.json`。
- 强化 `/facts/` 和 `llms-full.txt` 的分组事实。
- 更新 GEO monitor，将 `.well-known` 加入 surface path。

### 阶段 4：内容质量升级

- 把最高价值页升级为非模板化内容：`/video-summary/`、`/online-video-downloader/`、`/youtube-to-mp4/`、`/bilibili-course-downloader/`、`/douyin-public-video-download/`。
- 增加真实演示、截图或示意图。
- 增加更具体的 FAQ、失败恢复和合规说明。

### 阶段 5：持续运营

- 根据 Search Console 查询词补充页面。
- 根据 404 和 GEO 日志补齐缺失路径。
- 每次新增或大改 SEO 内容后运行 IndexNow 指纹提交。
- 每月审查标题、描述、内链和低价值页面。

## 验收标准

- `npm test -- tests/seo-metadata.test.js` 通过。
- `npm run seo:validate` 在真实 HTTPS 域名下通过。
- 远程部署后 `npm run seo:validate:remote` 返回所有必需 URL 为 200。
- `sitemap.xml` 只包含 canonical、可索引、返回 200 的 URL。
- 每个新增页面有唯一 title、description、primary keyword、canonical、Markdown mirror、相关内链和结构化数据。
- `/.well-known/ai.json` 返回 200，内容不包含虚假的 MCP 或未实现能力。
- 下载相关页面都包含公开视频和合规边界。
- 首页、hub 页、定价页和高价值任务页都有明确 CTA。

## 风险与应对

- **模板化内容风险**：新增页面必须有独立搜索意图、场景、失败原因和内链，不为了凑关键词创建薄页。
- **视频下载合规风险**：所有下载页都保持公开视频边界，重点强调学习、研究、个人备份和资料整理。
- **SPA 可抓取风险**：关键 SEO 内容放在静态 HTML，不依赖 Vue mount 后生成。
- **域名混乱风险**：生产只使用一个 canonical host，canonical、sitemap、OG、IndexNow、站长平台保持一致。
- **AI 搜索误描述风险**：`facts`、`llms`、`.well-known/ai.json` 三处事实源保持一致，明确不支持绕过限制。

## 设计结论

SaveAny 当前最适合在既有静态 SEO 生成器上继续演进。路线 2 可以复用现有测试和部署脚本，同时补上主题架构、转化页面和 AI discoverability。短期先解决真实域名与核心 hub，随后把高价值页面从“关键词覆盖”升级成“能说服用户、能被 AI 正确引用、能稳定转化”的内容资产。
