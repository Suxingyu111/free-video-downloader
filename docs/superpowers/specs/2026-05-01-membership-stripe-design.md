# 用户会员与 Stripe 月订阅设计

## 背景

当前 SaveAny 已完成公开视频下载、AI 总结、思维导图、问答和 Markdown 导出。项目仍以本地或自托管为主要部署形态，后端是 FastAPI，前端是 Vue 3，现有运行时数据主要保存在 `runtime/`。历史文档明确写过 v1 不包含账号和真实支付，但前端已经有静态“套餐方案”页面。

本设计把“专业版会员”作为 AI 总结能力的商业化入口：下载继续免费，AI 总结对免费账号每天提供 3 次额度，会员获得高额度或近似不限量使用。

## 已确认决策

- 会员绑定到用户账号，不绑定浏览器、本机实例或部署许可证。
- 登录方式使用邮箱 + 密码，不做邮箱验证。
- 付费方式使用 Stripe 月度订阅，第一版专业版展示为 `¥29/月`，Stripe 货币使用人民币 `cny`。
- Stripe 账号主体使用 Stripe 支持的国家或地区，不按中国大陆主体设计。
- 数据库存储使用 SQLite，默认放在 `runtime/saveany.db`。
- 密码重置第一版支持本地开发模式返回或打印重置链接，生产预留 SMTP 发信配置。
- 无外网测试需要本地 `mock billing` 模式，用同一套会员数据库状态模拟购买成功、续费失败、取消和过期。
- 方案采用平衡实现：账号、会话、密码重置、订阅状态、Webhook 幂等、Customer Portal 和离线 mock billing 一次成型。

## Stripe 文档依据

已通过 Context7 拉取当前 Stripe 文档，设计遵循以下要点：

- 使用 Checkout Sessions API 创建订阅收银台，`mode` 设置为 `subscription`，`line_items` 使用 Stripe Dashboard 或 API 中创建的 recurring Price ID。
- Checkout 成功页只用于用户回跳；真正的会员开通、续费、取消和过期以 Stripe webhook 为准。
- Webhook 必须使用 Stripe 官方库基于原始请求体、`Stripe-Signature` header 和 endpoint secret 验签。
- 本地 Stripe 联调使用 Stripe CLI：`stripe listen --forward-to localhost:8000/api/billing/webhook`。
- Webhook 事件可能重试或重复投递，需要按 Stripe event ID 做幂等处理。

## 目标

- 用户可以注册、登录、退出和重置密码。
- 用户登录后能看到当前会员状态和免费 AI 总结剩余额度。
- 未登录用户点击 AI 总结时被引导登录。
- 免费用户每天最多创建 3 次 AI 总结任务。
- 免费额度用完后，前端引导开通专业版。
- 用户可以通过 Stripe Checkout 购买专业版月订阅。
- Stripe webhook 更新本地订阅状态，前端不能自行决定会员状态。
- 已订阅用户可以进入 Stripe Customer Portal 管理订阅。
- 无外网时可以用 mock billing 完整验收账号、额度、购买、取消、过期和付款失败状态。

## 非目标

- 不实现邮箱验证。
- 不实现多套餐、升级降级和团队席位。
- 不限制视频下载功能。
- 不实现完整 SaaS 级审计、后台管理、发票管理或税务配置。
- 不做登录态托管、平台 Cookie 上传、DRM 绕过、付费内容绕过或账号共享能力。
- 不在前端保存 Stripe secret key、webhook secret 或真实支付配置。

## 推荐架构

后端新增三个边界清晰的模块：

- `auth`：注册、登录、退出、当前用户、密码重置、会话管理。
- `billing`：Stripe Checkout、Stripe Customer、Stripe webhook、Customer Portal、mock billing。
- `entitlements`：会员权益判断和 AI 总结用量扣减。

现有 `summary_routes` 在创建总结任务前调用 `entitlements`：

1. 读取当前登录用户。
2. 判断订阅是否有效。
3. 非会员按日期检查并原子扣减免费额度。
4. 额度通过后再创建总结任务。

下载相关接口保持现状，第一版不要求登录。

## 数据模型

SQLite 第一版建议使用以下表。

### `users`

- `id`
- `email`
- `password_hash`
- `status`
- `created_at`
- `updated_at`

约束：

- `email` 唯一。
- 邮箱统一规范化为小写和去除首尾空格。
- 密码只保存专用哈希，不保存明文。

### `sessions`

- `id`
- `user_id`
- `session_token_hash`
- `expires_at`
- `created_at`
- `last_seen_at`
- `revoked_at`

说明：

- 浏览器只持有随机 session token。
- 数据库只保存 token 哈希。
- Cookie 设置 `HttpOnly`、`SameSite=Lax`，生产 HTTPS 下设置 `Secure`。

### `password_reset_tokens`

- `id`
- `user_id`
- `token_hash`
- `expires_at`
- `used_at`
- `created_at`

说明：

- 重置 token 只保存哈希。
- 开发模式可返回或打印重置链接。
- 生产模式预留 SMTP 发信。

### `subscriptions`

- `id`
- `user_id`
- `plan`
- `status`
- `stripe_customer_id`
- `stripe_subscription_id`
- `stripe_price_id`
- `current_period_start`
- `current_period_end`
- `cancel_at_period_end`
- `created_at`
- `updated_at`

有效会员状态第一版包括 `active` 和 `trialing`。`past_due` 是否临时保留权益可配置，默认不视为有效会员，避免付款失败后继续无限使用。

### `stripe_events`

- `event_id`
- `event_type`
- `processed_at`
- `payload_hash`

约束：

- `event_id` 唯一。
- 重复事件返回 200，但不再次修改业务状态。

### `usage_daily`

- `user_id`
- `usage_date`
- `summary_count`
- `created_at`
- `updated_at`

约束：

- `(user_id, usage_date)` 唯一。
- 创建总结任务时在同一事务中检查和递增，避免并发请求绕过每天 3 次限制。

### `billing_attempts`

- `id`
- `user_id`
- `mode`
- `status`
- `stripe_checkout_session_id`
- `created_at`
- `updated_at`

用途：

- 记录 Checkout 创建和回跳状态。
- 避免同一用户已有有效订阅时重复创建订阅 Checkout。
- 帮助支付成功页展示“正在确认会员状态”。

## API 设计

### 账号

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/me`
- `POST /api/auth/password-reset/request`
- `POST /api/auth/password-reset/confirm`

`GET /api/me` 返回当前用户、会员状态和今日免费额度摘要。

### 会员和支付

- `GET /api/billing/status`
- `POST /api/billing/checkout`
- `POST /api/billing/portal`
- `POST /api/billing/webhook`

Stripe 模式下：

- `checkout` 创建 Stripe Checkout Session，返回 `url`。
- `portal` 创建 Stripe Customer Portal Session，返回 `url`。
- `webhook` 使用 Stripe 官方库验签并处理事件。

Mock 模式下：

- `checkout` 返回本地 mock checkout URL 或 mock action。
- `portal` 返回本地会员管理 URL 或 mock action。
- mock 管理页面可以触发开通、取消、过期、付款失败等状态。

### AI 总结

现有 `POST /api/summaries` 增加认证和权益检查：

- 未登录返回 401。
- 免费额度用完返回 402 或 403，并附带升级提示。
- 已登录且有额度或有效会员时继续创建总结任务。

## Stripe 订阅流程

1. 用户登录后点击“开通专业版 ¥29/月”。
2. 后端读取 `STRIPE_PRO_MONTHLY_PRICE_ID`，创建或复用 Stripe Customer。
3. 后端创建 Checkout Session：
   - `mode=subscription`
   - `line_items[0].price=STRIPE_PRO_MONTHLY_PRICE_ID`
   - `line_items[0].quantity=1`
   - `success_url` 带 `session_id={CHECKOUT_SESSION_ID}`
   - `cancel_url` 回到套餐页
   - `client_reference_id` 或 metadata 写入本地 user ID
4. 前端跳转 Stripe Checkout。
5. 用户付款后回到成功页。
6. 成功页轮询 `/api/me` 或 `/api/billing/status`。
7. Stripe webhook 到达后更新 `subscriptions`。
8. 前端看到会员状态变为有效，解锁 AI 总结额度。

## Webhook 处理

第一版处理以下事件：

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.paid`
- `invoice.payment_failed`

处理规则：

- 所有事件先验签。
- 先写入或检查 `stripe_events.event_id`。
- 重复事件直接返回 200。
- 订阅事件以 `stripe_subscription_id` 和 `stripe_customer_id` 关联本地用户。
- `invoice.paid` 可用于确认续费成功和更新周期。
- `invoice.payment_failed` 标记付款失败，会员状态按当前订阅状态计算。

## 安全和风控

- 密码哈希使用 `argon2` 或 `bcrypt`。若依赖安装困难，优先选择项目环境可稳定安装的官方成熟库。
- 注册、登录和密码重置做基础限流，按 IP 和邮箱维度记录短窗口失败次数。
- 登录失败返回统一错误，不暴露邮箱是否存在。
- Cookie 不对 JavaScript 可读。
- 生产环境要求配置 HTTPS 和安全 cookie。
- Stripe secret key、webhook secret 和 Price ID 只在后端环境变量中配置。
- Webhook 使用原始请求体来验签，不能先 JSON 解析再验签。
- Checkout 成功回跳不直接开通会员。
- AI 总结额度扣减必须在后端事务中完成。

## 前端体验

顶部导航新增账号入口：

- 未登录：显示“登录 / 注册”。
- 已登录：显示邮箱、会员状态、退出、管理订阅。

套餐页调整：

- 免费版说明每天 3 次 AI 总结。
- 专业版按钮改为“开通专业版 ¥29/月”。
- 已订阅时按钮改为“管理订阅”。

AI 总结工作区调整：

- 未登录时展示登录引导。
- 免费用户展示今日剩余额度。
- 额度用完后展示升级引导。
- 会员展示专业版状态。

支付回跳页：

- 成功回跳显示“正在确认会员状态”。
- 如果 webhook 尚未到达，继续轮询状态。
- 取消回跳回到套餐页，并说明未产生扣款。

## 本地无外网测试

配置：

```bash
BILLING_MODE=mock
```

能力：

- 注册和登录账号。
- 非会员每天创建 3 次 AI 总结，第 4 次被拦截。
- 点击开通专业版进入 mock billing。
- 模拟购买成功后，本地订阅状态变为有效。
- 模拟取消后，`cancel_at_period_end` 生效。
- 模拟过期后，会员权益失效。
- 模拟付款失败后，前端展示付款异常状态。

Mock 模式必须使用同一套 `subscriptions` 和 `usage_daily` 表，确保业务逻辑和 Stripe 模式一致。

## Stripe 有外网联调

准备工作：

1. 在 Stripe Dashboard 创建 Product：`SaveAny Pro`。
2. 创建 recurring Price：`¥29/month`，currency 使用 `cny`。
3. 配置后端环境变量：

```bash
BILLING_MODE=stripe
STRIPE_SECRET_KEY=stripe_secret_placeholder
STRIPE_WEBHOOK_SECRET=stripe_webhook_placeholder
STRIPE_PRO_MONTHLY_PRICE_ID=price_...
PUBLIC_APP_URL=http://localhost:5173
```

4. 启动后端和前端。
5. 启动 Stripe CLI：

```bash
stripe listen --forward-to localhost:8000/api/billing/webhook
```

6. 使用 Stripe 测试卡完成订阅。
7. 回到页面确认会员状态由 webhook 驱动变为有效。

## 验收标准

- 新用户能注册、登录、退出。
- 密码错误不会登录成功。
- 密码重置 token 过期或复用会失败。
- 免费用户每天前三次 AI 总结成功，第四次被引导升级。
- 会员用户可继续创建 AI 总结。
- Stripe webhook 签名错误返回 400。
- 重放同一个 Stripe event 不会重复处理。
- Checkout 成功回跳但 webhook 未到达时，不会提前开通会员。
- Mock billing 无外网可模拟购买成功、取消、过期和付款失败。
- 前端不会暴露 Stripe secret key 或 webhook secret。

## 后续扩展

- 邮箱验证。
- SMTP 正式发信。
- 多套餐和年度订阅。
- 团队空间和席位。
- PostgreSQL 迁移。
- 更完整的后台审计和支付报表。
- 全站公开部署的认证、限流、任务隔离和合规策略。
