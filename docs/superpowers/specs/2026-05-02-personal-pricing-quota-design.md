# 个人透明额度套餐设计

## 背景

SaveAny 当前已经从单纯的公开视频下载器演进为“公开视频下载 + AI 学习总结工作台”。用户可以粘贴公开视频链接，解析标题、封面、格式、字幕和播放列表，并在登录后生成 AI 总结、字幕文本、思维导图、问答和 Markdown 笔记。

现有商业化实现较轻：下载和解析完全免费且免登录；AI 总结需要登录；免费账号默认每天 3 次 AI 总结；有效 Pro 会员不消耗免费额度；Stripe 当前只配置一个 Pro 月订阅 Price。前端套餐页目前展示免费版、专业版和团队版，但后端真实可执行的套餐语义只有 `free` 和 `pro`，也没有团队、席位、共享空间或团队用量模型。

本设计将套餐调整为只面向个人用户的透明额度模型：保留免费入口，降低 Pro 月订阅价格到 `¥19/月`，并通过“AI 总结次数包”和“语音转写分钟包”承接重度使用。

## 竞品参考

调研到的公开定价模式说明，AI 总结和语音转写产品通常会把“转写分钟、单条时长、AI summary/AI credits”作为核心限制：

- Notta 免费版提供有限转写分钟和 AI Summary，Pro 提升到更高转写分钟、单条时长和 AI Summary 数量。参考：[Notta Pricing](https://www.notta.ai/en/pricing)。
- Tactiq 将 AI 功能抽象为 AI credits，免费和 Pro 有不同额度，并说明 AI credits 用于总结、行动项和基于转写的提问。参考：[Tactiq AI Credits](https://help.tactiq.io/en/articles/9514873-what-is-an-al-credit)。
- Fireflies 的套餐页同时展示转写、存储、AI 总结和单次录制时长等维度。参考：[Fireflies Pricing](https://fireflies.ai/fr/pricing)。
- Recall 对“Unlimited”使用公平使用边界，说明即便展示无限，也需要保留异常高用量处理能力。参考：[Recall Pricing](https://www.recall.it/pricing)。

SaveAny 不采用“无限”文案，而采用明确额度和按量包，减少用户误解，也便于控制 AI 和转写成本。

## 已确认决策

- 网站只服务个人用户。
- 完全删除团队套餐，不保留团队、自托管咨询或任何团队入口。
- 套餐采用“免费 + Pro + 按量包”。
- Pro 个人版价格为 `¥19/月`。
- 按量包分开售卖“AI 总结次数包”和“语音转写分钟包”，不采用统一点数。
- 未登录用户可以体验解析和下载，但按 IP 做轻量限制。
- 登录免费用户获得更多解析和下载额度，并保留 AI 总结试用。
- AI 总结和语音转写是主要商业化点。
- 所有额度文案使用明确数字，不使用“无限”。

## 目标

- 让个人用户一眼理解免费版、Pro 和按量包的差异。
- 保留公开视频解析和下载作为增长入口，但降低未登录滥用风险。
- 让注册账号有立即可感知的价值：更多解析、更多下载、AI 总结试用。
- 让 `¥19/月` Pro 成为大多数个人用户的主选择。
- 让重度用户通过按量包补充总结次数或转写分钟，而不是被迫多账号使用。
- 把当前没有限制的 AI 追问纳入登录和上限控制，避免隐藏成本洞。
- 保留现有 AI 总结 reservation/refund 体验，失败时不让用户白白损失额度。

## 非目标

- 不做团队版、团队协作、席位、共享空间、团队报表或团队账单。
- 不做企业销售、咨询入口或自托管商业入口。
- 不在第一阶段做年付折扣、优惠券、发票管理或完整用量明细页。
- 不承诺处理私密、登录限定、会员、付费、DRM、地区限制或平台风控内容。
- 不把下载变成核心付费点；下载仍是个人用户的基础工具能力，只做额度和风控。

## 套餐方案

### 免费与 Pro

| 能力 | 未登录访客 | 登录免费版 | Pro 个人版 |
| --- | ---: | ---: | ---: |
| 价格 | `¥0` | `¥0` | `¥19/月` |
| 视频解析 | `3 次/日/IP` | `30 次/日/账号` | `300 次/月/账号` |
| 视频下载 | `1 次/日/IP` | `10 次/日/账号` | `100 次/月/账号` |
| 单个下载视频时长 | `30 分钟` | `60 分钟` | `180 分钟` |
| AI 总结次数 | 不开放，需登录 | `3 次/日` | `120 次/月` |
| AI 总结单视频时长 | 不开放 | `30 分钟` | `120 分钟` |
| 语音转写分钟 | 不开放 | `30 分钟/月` | `600 分钟/月` |
| AI 追问 | 不开放 | 每个总结 `3 问` | 每个总结 `20 问` |
| 导出 | 不开放 | Markdown、TXT、思维导图基础导出 | Markdown、TXT、思维导图和批量导出准备 |

说明：

- 未登录访客的解析和下载额度按 `IP + 日期` 统计。
- 登录免费版的解析和下载额度按 `账号 + 日期` 统计。
- Pro 的解析、下载、AI 总结和语音转写额度按 `账号 + 自然月` 统计。
- 免费版 AI 总结次数继续保持当前每天 3 次的体验。
- Pro 不写“无限”，用 `120 次/月` 和 `600 分钟/月` 明确表达可用范围。
- 单视频时长限制用于控制超长公开视频带来的下载、转写和模型成本。

### 按量包

| 按量包 | 价格 | 内容 | 有效期 | 适用用户 |
| --- | ---: | ---: | --- | --- |
| 总结小包 | `¥6` | `20 次 AI 总结` | 90 天 | 免费版和 Pro |
| 总结大包 | `¥19` | `100 次 AI 总结` | 180 天 | 免费版和 Pro |
| 转写小包 | `¥8` | `120 分钟语音转写` | 90 天 | 免费版和 Pro |
| 转写大包 | `¥29` | `600 分钟语音转写` | 180 天 | 免费版和 Pro |

扣减顺序：

1. 先消耗当前套餐内置额度。
2. 内置额度不足时，自动消耗最早过期的同类型按量包。
3. 按量包不足时，拦截任务并提示购买对应包。
4. 月度套餐额度不结转。
5. 按量包在有效期内可跨月使用。
6. 读取缓存总结、恢复工作区、下载已生成导出文件不扣额度。

### AI 总结扣减口径

- 有可用字幕的视频：扣 `1 次 AI 总结`。
- 无可用字幕、需要语音转写的视频：扣 `1 次 AI 总结 + 实际语音转写分钟`。
- 语音转写分钟按向上取整扣费，最低扣 `1 分钟`。
- 主动解析和主动重新总结创建新任务时计数。
- 恢复工作区只读取已有 `summary_id`，不计数。
- AI 追问不消耗总结包或转写包，但受每个总结的追问次数上限控制。

## 后端设计

### 现有约束

当前后端的关键约束：

- `subscriptions.plan` 当前实际只有 `pro` 付费语义。
- `usage_daily.summary_count` 只记录每日 AI 总结次数。
- `summary_quota_reservations` 已承担 AI 总结失败退款。
- `/api/analyze` 和 `/api/download` 当前没有登录、用量、用户归属或持久化下载历史。
- `/api/summaries/{id}/questions` 当前没有登录和额度上限，是潜在 AI 成本风险。
- Stripe 目前只配置一个 `STRIPE_PRO_MONTHLY_PRICE_ID`，没有多 Price 到权益的映射。

### 权益目录

新增代码内权益目录 `PLAN_CATALOG`，第一阶段可以先放在后端服务模块中，不要求数据库化。

```python
PLAN_CATALOG = {
    "anonymous": {
        "analyze_daily_limit": 3,
        "download_daily_limit": 1,
        "download_max_duration_seconds": 30 * 60,
    },
    "free": {
        "analyze_daily_limit": 30,
        "download_daily_limit": 10,
        "download_max_duration_seconds": 60 * 60,
        "summary_daily_limit": 3,
        "summary_max_duration_seconds": 30 * 60,
        "transcription_monthly_minutes": 30,
        "questions_per_summary": 3,
    },
    "pro": {
        "analyze_monthly_limit": 300,
        "download_monthly_limit": 100,
        "download_max_duration_seconds": 180 * 60,
        "summary_monthly_limit": 120,
        "summary_max_duration_seconds": 120 * 60,
        "transcription_monthly_minutes": 600,
        "questions_per_summary": 20,
    },
}
```

`anonymous` 不是订阅 plan，只是未登录访问者的权益配置。

### 数据模型

保留现有 `subscriptions`、`stripe_events`、`billing_attempts`、`users` 和 `sessions`。

新增或迁移以下表：

#### `usage_periods`

用于记录登录用户在日或月维度的用量。第一阶段统一新增这张表，并把现有 `usage_daily.summary_count` 的语义迁入 `usage_periods`；迁移完成后，AI 总结额度读取以 `usage_periods` 为准。

- `user_id`
- `period_type`: `day` 或 `month`
- `period_key`: 例如 `2026-05-02` 或 `2026-05`
- `analyze_count`
- `download_count`
- `summary_count`
- `transcription_minutes`
- `question_count`
- `created_at`
- `updated_at`

约束：

- `(user_id, period_type, period_key)` 唯一。
- 免费版 AI 总结沿用日维度；Pro 月度额度使用月维度。
- `usage_daily` 可以作为兼容迁移来源保留，但新扣减、新退款和新状态 API 都不再依赖它。

#### `anonymous_usage`

用于记录未登录访客解析和下载。

- `ip_hash`
- `usage_date`
- `analyze_count`
- `download_count`
- `created_at`
- `updated_at`

约束：

- `(ip_hash, usage_date)` 唯一。
- 只保存 IP 哈希，不保存原始 IP。
- 哈希应加入服务端固定 salt，避免日志泄露后反推常见 IP。

#### `meter_reservations`

用于统一记录额度预占和退款，替代或扩展 `summary_quota_reservations`。

- `reservation_id`
- `user_id`
- `meter_type`: `summary`、`transcription_minutes`、`analyze`、`download`、`question`
- `amount`
- `period_type`
- `period_key`
- `credit_pack_id`
- `status`: `reserved`、`committed`、`refunded`
- `created_at`
- `committed_at`
- `refunded_at`

说明：

- AI 总结任务创建时预占 `summary=1`。
- 如果后续需要语音转写，再预占 `transcription_minutes=N`。
- 任务失败或启动失败时按 reservation 退款。
- `credit_pack_id` 为空表示消耗套餐内置额度；不为空表示消耗按量包。

#### `credit_packs`

用于存储用户购买的按量包余额。

- `id`
- `user_id`
- `pack_type`: `summary` 或 `transcription_minutes`
- `source`: `stripe` 或 `mock`
- `stripe_price_id`
- `stripe_payment_intent_id`
- `purchased_amount`
- `remaining_amount`
- `expires_at`
- `status`: `active`、`depleted`、`expired`、`refunded`
- `created_at`
- `updated_at`

规则：

- 总结包以“次”为单位。
- 转写包以“分钟”为单位。
- 扣减时优先使用最早过期的 active pack。
- 购买成功以后即写入余额；退款或争议时可标记 `refunded` 并冻结余额。

### API 调整

#### `/api/analyze`

行为：

- 未登录：按 `anonymous_usage` 检查 `3 次/日/IP`。
- 登录免费：按 `usage_periods` 检查 `30 次/日/账号`。
- Pro：按 `usage_periods` 检查 `300 次/月/账号`。
- 超额时返回 `429` 或 `402`，前端根据是否登录展示注册或升级引导。

说明：

- 解析失败是否计数采用“开始解析即计数”的口径，避免平台风控被反复请求。
- 如果后端在参数校验前失败，例如 URL 为空，不计数。

#### `/api/download`

行为：

- 未登录：按 `anonymous_usage` 检查 `1 次/日/IP`，并检查单视频时长 `30 分钟`。
- 登录免费：检查 `10 次/日/账号` 和 `60 分钟` 单视频时长。
- Pro：检查 `100 次/月/账号` 和 `180 分钟` 单视频时长。

说明：

- 下载接口不能只信任前端传入的视频时长。第一阶段由 `/api/analyze` 在服务端生成短期 `analysis_token` 并保存解析快照，`/api/download` 必须携带该 token；后端用解析快照里的视频时长和播放列表条目数做限制校验。没有有效 token 时，后端重新解析一次再决定是否创建下载任务。
- 播放列表下载按条目数量计下载次数；如果当前仍是全选下载，应在创建任务前显示将消耗的下载次数。

#### `/api/summaries`

行为：

- 继续要求登录。
- 检查 AI 总结次数和单视频总结时长。
- 创建 summary task 前预占 `summary=1`。
- 如果已有可用字幕，只消耗总结次数。
- 如果无字幕，需要语音转写，在 summary worker 中根据音频或视频时长预占转写分钟。
- 任务失败、创建失败、worker 启动失败或启动后中断，按 reservation 退款。

错误提示：

- 总结次数不足：提示开通 Pro 或购买总结次数包。
- 视频超过当前套餐总结时长：提示升级 Pro；如果已经是 Pro，则提示当前仅支持单视频 120 分钟以内的 AI 总结。
- 转写分钟不足：提示当前任务需要约 `X` 分钟转写，当前还差 `Y` 分钟，并引导购买转写分钟包。

#### `/api/summaries/{id}/questions`

行为：

- 改为必须登录。
- 校验当前用户有权访问该 summary。
- 按每个 summary 统计追问次数。
- 免费版每个总结最多 `3 问`。
- Pro 每个总结最多 `20 问`。
- 超额时返回 `402`，提示升级 Pro。

说明：

- 第一阶段不售卖追问包，避免套餐复杂化。
- 如果 summary 本身来自恢复工作区，也必须校验当前用户访问权。

#### 账单 API

保留：

- `GET /api/billing/status`
- `POST /api/billing/checkout`
- `POST /api/billing/checkout/confirm`
- `POST /api/billing/portal`
- `POST /api/billing/webhook`
- mock billing 入口

新增：

- `GET /api/entitlements/status`：返回当前用户套餐、周期额度、按量包余额、即将过期余额。
- `POST /api/billing/checkout` 支持 `{ "purchase_type": "subscription" | "credit_pack", "pack_id": "summary_small" }`。
- mock billing 支持购买总结包和转写包，方便本地验收。

Stripe 配置建议：

- `STRIPE_PRO_MONTHLY_PRICE_ID`
- `STRIPE_SUMMARY_SMALL_PACK_PRICE_ID`
- `STRIPE_SUMMARY_LARGE_PACK_PRICE_ID`
- `STRIPE_TRANSCRIPTION_SMALL_PACK_PRICE_ID`
- `STRIPE_TRANSCRIPTION_LARGE_PACK_PRICE_ID`

后端必须维护 Price ID 到 pack 的映射，不能相信前端传入的价格或数量。

## 前端体验

### 套餐页结构

套餐页只保留两张主卡：

- 免费版
- Pro 个人版

团队版卡片、团队协作文案、团队咨询 CTA、`¥99/月起` 全部删除。

套餐页顶部建议文案：

> 下载和解析轻量免费，AI 总结按额度透明使用。先免费整理几个视频，需要高频总结或长视频转写时再升级。

免费版卡片重点：

- 登录后每天解析 `30` 次。
- 登录后每天下载 `10` 次。
- 每天 `3` 次 AI 总结。
- 每月 `30` 分钟语音转写试用。
- 单视频总结 `30` 分钟以内。

Pro 卡片重点：

- `¥19/月`。
- 每月 `120` 次 AI 总结。
- 每月 `600` 分钟语音转写。
- 单视频总结 `120` 分钟以内。
- 单视频下载 `180` 分钟以内。
- 每个总结 `20` 次 AI 追问。
- 支持更稳定的高频个人学习和内容整理工作流。

按量包区域放在主套餐卡片下方，分为两组：

- AI 总结次数包：`¥6 / 20 次`、`¥19 / 100 次`。
- 语音转写分钟包：`¥8 / 120 分钟`、`¥29 / 600 分钟`。

### 转化提示

- 未登录解析超额：提示“今天的访客解析次数已用完，登录后每天可解析 30 次。”
- 未登录下载超额：提示“今天的访客下载次数已用完，登录后每天可下载 10 次。”
- 免费总结超额：提示“今天免费总结已用完，开通 Pro 每月 120 次，或购买总结次数包。”
- 转写分钟不足：提示“这个视频需要约 X 分钟转写，当前还差 Y 分钟。”
- Pro 额度快用完：提示“本月还剩 X 次总结 / Y 分钟转写，可购买按量包继续使用。”

### 账号菜单

账号菜单应展示：

- 当前套餐。
- 解析/下载剩余额度。
- AI 总结剩余额度。
- 转写分钟剩余额度。
- 即将过期的按量包余额。

现有固定宽度额度条需要改成真实进度，不再使用固定 `62%`。

## 错误处理与退款

- URL 参数校验失败不扣额度。
- 解析任务开始后失败，解析次数不退款。
- 下载任务创建失败退款下载次数；平台下载失败是否退款按失败类型决定，第一阶段建议退款，减少用户负面感受。
- AI 总结任务创建失败、worker 启动失败、运行失败或服务重启后中断，退款总结 reservation。
- 如果语音转写已预占但未成功产生转写文本，退款转写分钟。
- 如果 AI 总结成功但用户不满意，不自动退款。
- 读取缓存总结、恢复工作区、下载已有 Markdown、TXT、思维导图不扣额度。

## 安全与风控

- 未登录用量按 IP 哈希统计，避免保存原始 IP。
- 登录账号按账号统计用量。
- 同 IP 多账号异常只记录，不在第一阶段做复杂封禁。
- 继续保留公开视频边界文案，不提供 Cookie 上传、二维码登录、付费内容绕过或 DRM 绕过。
- 所有 Stripe 支付结果以后端 webhook 或 checkout confirm 为准，前端不能自行开通套餐或发放按量包。
- Price ID 到套餐/按量包的映射必须在后端维护，前端只传 `pack_id`。

## 上线顺序

### 第一阶段：真实个人套餐

1. 删除团队套餐和所有团队入口。
2. 套餐页改成免费版 + Pro 个人版 + 按量包区域。
3. 新增权益目录和用量状态 API。
4. 增加未登录解析/下载限制。
5. 增加登录用户解析/下载限制。
6. 增加 AI 总结月度额度、转写分钟、单视频时长限制。
7. 给 AI 追问增加登录和每 summary 上限。
8. Stripe 支持 Pro 月订阅、总结次数包、转写分钟包。
9. Mock billing 支持购买和消耗按量包。
10. 账号菜单和总结工作区展示剩余额度。

### 第二阶段：增强能力

1. 年付折扣。
2. 用量明细页。
3. 购买记录和发票入口。
4. 更细的失败原因退款策略。
5. 历史总结列表。
6. 批量导出。

## 测试计划

### 后端

- 未登录 IP 每天可解析 3 次，第 4 次被拦截。
- 未登录 IP 每天可下载 1 次，第 2 次被拦截。
- 登录免费用户每天可解析 30 次、下载 10 次。
- 免费用户每天可创建 3 次 AI 总结，第 4 次被引导升级或购买总结包。
- 免费用户单视频总结超过 30 分钟被拦截。
- Pro 用户每月可创建 120 次 AI 总结，超过后消耗总结包。
- Pro 用户每月可消耗 600 分钟转写，超过后消耗转写包。
- 按量包按最早过期顺序扣减。
- 按量包过期后不再可用。
- AI 总结任务失败退款总结次数。
- 语音转写失败退款转写分钟。
- `/api/summaries/{id}/questions` 未登录返回 401。
- 免费用户每个 summary 第 4 次追问被拦截。
- Pro 用户每个 summary 第 21 次追问被拦截。
- Stripe webhook 根据 Price ID 发放正确订阅或按量包。
- 重复 Stripe event 不重复发放按量包。

### 前端

- 套餐页只展示免费版和 Pro 个人版两张主卡。
- 页面中不再出现团队版、团队协作、团队咨询或 `¥99/月起`。
- Pro 价格展示为 `¥19/月`。
- 免费版展示解析、下载、AI 总结、转写分钟和时长限制。
- Pro 展示月度总结次数、转写分钟、追问上限和时长限制。
- 按量包区域展示四个包。
- 未登录解析/下载超额时引导登录。
- 免费总结超额时引导 Pro 或总结包。
- 转写分钟不足时引导转写包。
- 账号菜单显示真实剩余额度和真实进度条。
- Checkout 成功回跳后刷新会员和按量包余额。

### 手动验收

- 未登录用户连续解析 4 个公开视频，确认第 4 次被引导登录。
- 未登录用户下载 2 次，确认第 2 次被引导登录。
- 注册登录后确认解析和下载额度变多。
- 免费用户创建 3 个短视频总结后，第 4 次被引导升级或买包。
- 购买总结小包后，第 4 次总结可以继续创建。
- 对无字幕视频触发语音转写，确认转写分钟减少。
- 转写分钟不足时购买转写小包，确认任务可以继续。
- Pro 开通后确认月度额度显示为 `120 次总结 / 600 分钟转写`。
- 取消 Pro 后本周期内仍显示有效，到期后恢复免费额度。

## 文案原则

- 用户可见套餐文案面向个人用户，不出现团队、企业、席位、协作、销售咨询等词。
- 不使用“无限”。
- 用“本月剩余”“今天剩余”“按月重置”“有效期至”解释额度。
- 明确说明只处理用户有权访问的公开视频。
- 把 Pro 价值讲成“高频学习、课程整理、播客复习、创作者素材笔记”，而不是抽象的“更强 AI”。

## 成功标准

- 用户能在套餐页 10 秒内理解免费版、Pro 和按量包差异。
- 未登录滥用解析和下载的成本下降。
- 登录转化提升，因为注册后立即获得更高解析和下载额度。
- Pro 转化围绕 `¥19/月` 形成低门槛心智。
- 重度用户可以自然购买总结包或转写包，而不是创建多个免费账号。
- 后端能够清楚解释每次扣费来自套餐额度还是按量包余额。
