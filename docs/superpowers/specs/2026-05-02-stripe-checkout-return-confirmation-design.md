# Stripe Checkout 回跳确认与套餐状态设计

## 背景

SaveAny 已有账号、会员、mock billing、Stripe Checkout、Customer Portal、webhook 幂等处理和套餐页入口。当前主流程仍依赖 Stripe webhook 更新本地会员状态；用户从 Stripe Checkout 成功回到套餐页后，如果本地没有同时运行 Stripe CLI 或 webhook 投递较慢，页面只能显示“正在确认会员状态”，无法在浏览器端到端测试中稳定看到套餐已开通。

本设计补齐支付成功回跳后的服务端兜底确认。Stripe webhook 仍是权威链路；成功回跳携带 `session_id` 时，前端请求后端查询 Stripe Checkout Session 和 Subscription，后端确认当前登录用户确实完成支付后，同步本地会员表。

## Stripe 文档依据

已通过 Context7 查询当前 Stripe 文档，相关依据如下：

- Checkout 可以把用户重定向到 Stripe 托管支付页，支付后再带 `session_id` 回到应用的成功 URL。
- 测试成功银行卡可用 `4242 4242 4242 4242`，任意未来有效期、任意三位 CVC 和任意其它字段。
- 订阅支付仍应通过服务端、Stripe API 和 webhook 确认，不能让前端仅凭回跳 URL 自行开通会员。

## 目标

- 用户点击“开通专业版 ¥29/月”后进入 Stripe Checkout。
- 用户使用 Stripe 测试卡支付成功后回到 `#pricing?checkout=success&session_id=...`。
- 套餐页自动调用后端确认接口，确认成功后刷新 `/api/me` 和 `/api/billing/status`。
- 套餐页清楚展示当前已开通套餐，例如专业版卡片显示“当前已开通”，按钮变为“管理订阅”。
- 支付取消、确认中、确认失败、付款失败、已取消但周期内仍有效、已过期、免费版、未登录等状态都有明确文案。
- webhook 和回跳确认可以重复到达，不会创建重复订阅或把订阅错误绑定到其他用户。

## 非目标

- 不新增多套餐、升级降级、团队席位或优惠券。
- 不在前端收集卡号，也不引入 Stripe Elements；继续使用 Stripe 托管 Checkout。
- 不移除 webhook，也不把前端回跳作为会员开通依据。
- 不实现发票、税务、账单地址或完整后台审计。

## 后端设计

新增 `POST /api/billing/checkout/confirm`。接口只允许已登录用户调用，请求体包含 `session_id`。处理步骤：

1. 校验 `BILLING_MODE=stripe`，并确认 `STRIPE_SECRET_KEY` 已配置。
2. 使用 Stripe Python SDK 查询 Checkout Session，展开或随后查询 `subscription`。
3. 校验 session 归属当前用户：`client_reference_id` 或 `metadata.saveany_user_id` 必须等于当前登录用户 ID。
4. 校验 session 状态：`payment_status` 为 `paid`，或关联的 subscription 状态为 `active` / `trialing`。
5. 将 session 写入现有 checkout attempt 状态，并调用现有订阅 upsert 逻辑同步 `subscriptions`。
6. 返回最新 `membership` 和 `mode`。

如果 session 不属于当前用户，返回 403。Stripe 配置缺失返回 503。支付尚未完成或 Stripe subscription 还不可读时返回 409，并带用户可理解的“支付确认中，请稍后刷新”文案。

## 前端设计

前端新增 `confirmBillingCheckout(sessionId)` API。`syncCurrentPageFromHash` 发现 `checkout=success` 且有 `session_id` 时，触发一次确认流程：

1. 设置账单状态为 `confirming`，套餐页展示“正在确认支付”。
2. 调用 `/api/billing/checkout/confirm`。
3. 成功后更新 `auth.membership`，再刷新 `/api/me` 和 `/api/billing/status`。
4. 如果返回 409，继续短轮询数次；轮询结束仍未确认时展示“支付已返回，仍在等待 Stripe 确认，可稍后刷新或进入管理订阅”。
5. 如果用户取消支付，展示“已取消支付，可以稍后继续开通专业版”。

套餐页专业版卡片根据 `auth.membership` 渲染状态：

- `active` / `trialing` 且未取消：显示“当前已开通”，按钮为“管理订阅”。
- `active` / `trialing` 且 `cancel_at_period_end=true`：显示“已取消续费，本周期内仍可使用”，按钮为“管理订阅”。
- `past_due`：显示“付款失败，请更新支付方式”，按钮为“管理订阅”。
- `canceled` 或周期过期：显示“专业版已过期”，按钮为“重新开通专业版 ¥29/月”。
- 未登录：点击开通时打开登录弹窗。
- 免费登录用户：显示免费额度和“开通专业版 ¥29/月”。

## 数据和幂等

继续复用 `subscriptions`、`billing_attempts` 和 `stripe_events`。回跳确认不新增表。确认接口按 Stripe `session_id` 更新对应 `billing_attempts`，并依赖 `stripe_subscription_id` 唯一约束和现有 upsert 逻辑保证幂等。若 webhook 先到，confirm 只刷新同一条订阅。若 confirm 先到，webhook 后到也只更新同一条订阅。

## 错误处理

- Stripe 查询失败：返回 502，并在前端显示“Stripe 确认失败，请稍后重试”。
- session 缺失：返回 400。
- session 不属于当前用户：返回 403，不更新任何会员状态。
- 支付未完成：返回 409，不更新会员状态，前端继续轮询或提示等待。
- 用户未登录：返回 401，前端打开登录弹窗并保留套餐页。

## 测试计划

后端测试：

- confirm 接口能用已支付 Checkout Session 同步 active 订阅。
- confirm 接口拒绝其它用户的 `session_id`。
- confirm 接口在支付未完成时返回 409 且不激活会员。
- webhook 先到和 confirm 后到不会产生重复订阅。

前端测试：

- `#pricing?checkout=success&session_id=...` 会调用确认接口并显示专业版已开通。
- 专业版卡片在 active、cancel_at_period_end、past_due、canceled、未登录和免费状态下显示正确文案。
- 支付取消回跳显示取消提示，不调用确认接口。

浏览器验证：

- 启动后端和前端，注册或登录测试账号。
- 打开套餐页，点击“开通专业版 ¥29/月”。
- 在 Stripe Checkout 使用卡号 `4242 4242 4242 4242`、未来有效期、任意三位 CVC 和任意姓名完成支付。
- 回到套餐页后确认专业版卡片显示“当前已开通”，账号菜单显示“专业版会员”，按钮变为“管理订阅”。
