# 登录安全体系设计

## 背景

SaveAny 当前已经具备邮箱密码注册登录、HttpOnly Cookie 会话、AI 总结登录门禁、免费额度、Mock billing 和 Stripe 订阅支付。登录模块的核心代码集中在：

- `backend/app/auth_routes.py`
- `backend/app/services/auth_service.py`
- `backend/app/services/database.py`
- `backend/app/services/rate_limit.py`
- `frontend/src/App.vue`
- `frontend/src/services/api.js`
- `frontend/src/services/authSession.js`

当前实现方向正确：密码使用 Argon2 哈希；session token 和 password reset token 入库前只保存 SHA-256 摘要；`current_user()` 会校验 session 是否过期、是否撤销、用户是否 active；登录失败、注册和密码重置请求已有 IP + email 双维度限流；Cookie 已设置 `HttpOnly`、`SameSite=Lax` 和 `Path=/`。

但当前登录体系仍偏“本地可用”和“基础防护”，还不能满足公开部署下对安全性、可靠性、用户唯一性和横向访问隔离的要求。主要缺口是：AI 总结结果读取接口未绑定当前用户、密码重置后不撤销旧 session、生产 Cookie 安全依赖手动配置、缺少显式 CSRF 防护、直接信任 `X-Forwarded-For`、密码重置确认无限流、缺少认证审计日志，以及前端对会话过期和跨标签页状态同步处理不足。

本设计采用“完整 Cookie Session 安全体系”：保留当前 FastAPI + SQLite + Vue 架构，不引入第三方身份服务，补齐账号、会话、CSRF、资源归属、密码重置、审计、生产配置和测试验收闭环。

## 设计目标

- 登录、注册、退出、密码重置、会员支付、AI 总结等关键流程在正常网络下稳定可靠。
- 邮箱账号唯一，所有用户身份由服务端生成和判定，客户端不能伪造用户身份、会员状态或额度状态。
- 密码不明文存储，token 不明文入库，数据库泄露时不能直接拿到可用 session 或 reset token。
- Cookie session 在生产环境默认使用安全属性，避免因配置遗漏泄露 session。
- 所有 Cookie 认证的状态变更请求具备 CSRF 防护。
- AI 总结任务、转写、Markdown、问答、SSE 状态和用户私有工作区资源必须做用户归属校验。
- 密码重置后立即撤销旧 session，降低账号被盗后的持续风险。
- 限流、审计、配置校验和测试覆盖足够支撑公开部署。

## 非目标

- 不在第一阶段引入 OAuth、社交登录、Passkey 或强制 MFA。
- 不把 SaveAny 变成多租户团队账号系统。
- 不绕过视频平台登录、付费、DRM、验证码、地区限制或平台风控。
- 不让前端直接读取 HttpOnly session cookie。
- 不用 JWT 替代服务端 session。当前服务端 session 更适合撤销、审计、密码重置后全设备失效和本项目现有 SQLite 模型。

## 威胁模型

设计重点覆盖以下风险：

- 凭证填充、密码爆破、注册滥用、密码重置滥用。
- 邮箱枚举、错误信息差异导致的账号探测。
- Session 猜测、窃取、固定、过期未清理、密码重置后旧 session 继续有效。
- CSRF 导致用户在不知情时创建任务、退出登录、修改会员状态或确认支付。
- 横向越权：用户 A 通过猜测或泄露的 `summary_id` 读取用户 B 的总结、转写、问答和 Markdown。
- 生产配置遗漏：Cookie 未开启 Secure、Mock billing 上线、CORS 允许过宽、dev mode 在线上返回 reset token。
- 安全事件不可追踪：无法定位异常登录、爆破、重置密码、session 撤销、CSRF 失败和会员敏感操作。

## 方案选择

### 方案 A：最小加固

只补生产 Cookie、密码重置撤销 session、基础 CSRF 和少量测试。成本最低，但资源归属、审计、前端会话一致性和生产配置仍容易漏。

### 方案 B：完整 Cookie Session 安全体系

保留当前技术栈和用户模型，补齐资源归属、CSRF、session 生命周期、密码重置、限流、审计、生产配置校验、前端统一 API 请求和状态机。改动适中，能最大程度复用当前代码，同时显著降低公开部署风险。

### 方案 C：迁移外部身份服务或 Passkey 优先

长期安全潜力更高，但会引入外部供应商、迁移、支付归属绑定、产品复杂度和部署成本。当前项目尚未到必须迁移身份服务的阶段。

最终采用方案 B。

## 后端认证架构

### 输入模型

`AuthRequest` 和密码重置请求模型应从普通 `str` 升级为明确校验：

- 邮箱必须 trim 后 lower-case，格式合法，最大长度限制为 `254`。
- 密码最小长度提升到 `12`，最大长度设为 `256`，防止超长输入造成 Argon2 计算型 DoS。
- 密码允许 Unicode、空格和密码短语，不强制大小写、数字、特殊符号组合。
- 注册和重置密码时拒绝常见弱密码。第一阶段可内置小型弱密码表；公开部署可接入 Have I Been Pwned k-anonymity API 或本地泄露密码库。

登录失败文案保持统一：“邮箱或密码错误”。密码重置请求永远返回：“如果账号存在，重置链接会发送到邮箱。”账号禁用、邮箱不存在、密码错误等细节只进审计日志，不直接展示给前端。

### 密码存储

继续使用 Argon2，并明确为 Argon2id。参数目标参考 OWASP Password Storage Cheat Sheet：最低 `memory_cost=19456 KiB`、`time_cost=2`、`parallelism=1`。如果运行环境性能不足，可以在部署前压测后使用 OWASP 推荐的等价参数组合，但必须记录在配置文档中。

密码校验成功后，如果发现旧 hash 参数低于当前标准，应在本次登录事务中 rehash 并更新 `password_hash`。

### 用户唯一性

`users.email` 继续保持数据库唯一约束。服务端只存标准化邮箱，注册前后都不接受客户端传入用户 ID、会员状态、额度或角色。

新增或明确用户状态：

- `active`：可登录和使用。
- `disabled`：不可登录，已有 session 不再通过 `current_user()`。
- `deleted`：保留必要审计和支付数据，不允许登录。

## Session 设计

### Session 创建

登录和注册成功后创建全新 session：

- 明文 token 使用 `secrets.token_urlsafe(32)` 或更高熵随机值。
- 明文 token 只写入 Cookie，不写入日志、不返回 JSON、不入库。
- 数据库只保存 `sha256(token)`。
- 每次登录都生成新 session，不能复用旧 token。

### Session 表字段

保留当前 `sessions` 表，并通过迁移增加：

- `ip_hash text`
- `user_agent_hash text`
- `revoked_reason text`
- `rotated_from_session_id text`
- `csrf_token_hash text`
- `absolute_expires_at real`

`expires_at` 表示滑动过期时间；`absolute_expires_at` 表示最长有效期。默认策略：

- 最长有效期：30 天。
- 空闲有效期：7 天，访问 `/api/me` 或认证接口时刷新。
- 密码重置、账号禁用、全设备退出时立即撤销。

### Session 校验

`current_user()` 继续作为后端认证依赖入口。校验规则：

1. Cookie 中必须存在 session token。
2. token hash 能命中 `sessions`。
3. `revoked_at is null`。
4. `expires_at > now`。
5. `absolute_expires_at > now`。
6. 用户存在且 `users.status = 'active'`。

校验失败统一返回 `401` 和“请先登录”或“登录已过期，请重新登录”。具体原因写入审计日志。

### Session 撤销

需要支持：

- 当前设备退出：只撤销当前 session。
- 全部设备退出：撤销用户所有未撤销 session。
- 密码重置成功：撤销用户所有未撤销 session。
- 用户禁用：`current_user()` 自动拒绝，同时后台可批量撤销。

撤销时写入 `revoked_at` 和 `revoked_reason`，原因包括 `logout`、`password_reset`、`user_disabled`、`admin_revoke`、`expired_cleanup`。

## Cookie 设计

生产默认 Cookie：

```http
Set-Cookie: __Host-saveany_session=<token>; Max-Age=2592000; Path=/; Secure; HttpOnly; SameSite=Lax
```

要求：

- 生产环境必须启用 `Secure`。
- 不设置 `Domain`，限制为当前 host。
- `Path=/`。
- `HttpOnly`，前端不能读取 session。
- `SameSite=Lax` 作为默认平衡；如果未来跨站前后端部署必须使用 `SameSite=None`，则必须同时使用 `Secure` 并加强 CSRF。
- Cookie 名生产默认改为 `__Host-saveany_session`。本地开发可继续使用 `saveany_session`，但文档要明确差异。

启动配置增加 `SAVEANY_ENV`：

- `SAVEANY_ENV=development`：允许 `SAVEANY_SECURE_COOKIES=false`，允许 mock billing。
- `SAVEANY_ENV=production`：强制 `SAVEANY_SECURE_COOKIES=true`，禁止 `SAVEANY_DEV_MODE=true`，禁止 `BILLING_MODE=mock`，要求 CORS allowlist 非空且不含 `*`。

## CSRF 设计

FastAPI 本身不会自动为 Cookie session 提供 CSRF 防护，因此新增应用级 CSRF 机制。

### Token 策略

采用“预登录签名 token + 登录后 session 绑定 token”：

- `GET /api/csrf` 返回短期预登录 CSRF token，前端启动和打开登录弹窗时获取并保存在内存中。
- 预登录 token 使用服务端 HMAC 签名，包含随机值、签发时间和用途，不依赖用户 session，TTL 为 30 分钟。
- 登录、注册、密码重置请求和密码重置确认必须携带预登录 token，并同时通过 Origin 校验。
- 创建 session 时生成 session 绑定的 `csrf_token`。
- 数据库保存 session 绑定 `csrf_token_hash`。
- 登录、注册和 `/api/me` 响应返回 session 绑定 `csrf_token` 字段，前端替换内存中的预登录 token。
- 前端所有登录后的状态变更请求加 `X-CSRF-Token`。
- 后端对所有 Cookie 认证的 `POST`、`PUT`、`PATCH`、`DELETE` 校验 session 绑定 header token。
- token 比较使用常量时间比较。

这避免前端读取 session cookie，同时解决登录前认证表单的 CSRF 启动问题，并让服务端能在 session 维度撤销登录后的 CSRF token。

### Origin 校验

对所有状态变更请求同时校验：

- `Origin` 存在时必须匹配 `PUBLIC_APP_URL` 或 `SAVEANY_ALLOWED_ORIGINS`。
- `Origin` 缺失时检查 `Referer`。
- 本地开发允许 localhost 白名单。
- Stripe webhook 不走 Cookie session，不适用 CSRF，但必须保留 Stripe 签名验签。

### 前端配合

`frontend/src/services/api.js` 新增统一 `apiFetch`：

- 默认 `credentials: "include"`。
- 前端启动和打开登录弹窗时调用 `GET /api/csrf`，拿到预登录 token。
- 对状态变更请求自动附带 `Content-Type: application/json` 和 `X-CSRF-Token`。
- 登录、注册或 `/api/me` 成功返回新的 session 绑定 token 后，替换内存 token。
- 统一处理 `401`、`403`、`429`、`402`。
- 避免各函数手写 fetch 导致 credentials 或 CSRF 遗漏。

## 密码重置设计

### 请求重置

`POST /api/auth/password-reset/request`：

- 按可信 IP + 标准化 email 限流。
- 永远返回 `{"ok": true}`，不泄露账号是否存在。
- 如果用户存在，创建新 token 前撤销该用户所有未使用 reset token。
- reset token 明文只用于邮件链接，数据库只存 hash。
- token TTL 为 30 分钟。
- 生产环境必须通过 SMTP 或邮件服务发送链接。
- `SAVEANY_DEV_MODE=true` 时才允许在响应中返回 `reset_token`，生产环境启动时禁止 dev mode。

### 确认重置

`POST /api/auth/password-reset/confirm`：

- 按 IP + token hash 前缀限流。
- token 必须存在、未使用、未撤销、未过期。
- 新密码通过密码策略。
- 更新密码 hash。
- 标记 token used。
- 撤销该用户所有未撤销 session，原因 `password_reset`。
- 写审计事件。
- 发送密码变更通知邮件。

## 资源归属和授权

当前最关键的业务安全变更是给 AI 总结资源增加用户归属。

### Summary ownership

`summary_store` 的任务快照增加 `owner_user_id`。创建总结时写入当前用户 ID。所有后续访问必须校验：

- `GET /api/summaries/{summary_id}`
- `POST /api/summaries/{summary_id}/questions`
- `GET /api/summaries/{summary_id}/events`
- `GET /api/summaries/{summary_id}/markdown`

这些接口都使用 `Depends(current_user)`。如果任务不存在返回 `404`；如果任务存在但不属于当前用户，也返回 `404`，避免泄露资源存在性。

### 公共缓存模型

公开视频总结可以保留底层缓存以节省 AI 成本，但公共缓存不能等同于公开任务：

- 缓存键仍可按 URL + language。
- 用户命中缓存时，为当前用户创建或映射一个自己的 summary task。
- 用户只能读取自己的 task ID。
- 共享的是生成结果，不共享任务状态、草稿、内部 quota metadata、Markdown token 或用户行为数据。

## 会员和支付安全

Stripe 相关现有设计整体正确：Checkout session 使用 `client_reference_id` 和 metadata 绑定用户，webhook 使用 Stripe 签名和 event id 幂等。

需要补强：

- `BILLING_MODE=mock` 只能在 development 环境启用。
- mock activate/cancel/expire/payment-failed 写审计日志。
- Checkout、Portal、Checkout confirm 都校验 CSRF。
- Checkout confirm 继续校验 Stripe session 归属当前用户。
- 生产 webhook endpoint 必须 HTTPS。
- Stripe CLI 只用于本地测试。
- webhook secret 支持轮换流程。

## 限流设计

统一保留 SQLite `rate_limits` 表，第一阶段不引入 Redis。若未来多实例部署，必须迁移到 Redis 或数据库原子计数。

限流 key：

- 登录失败：`auth:login:email:{normalized_email}` + `auth:login:ip:{trusted_ip_hash}`。
- 注册：`auth:register:email:{normalized_email}` + `auth:register:ip:{trusted_ip_hash}`。
- 密码重置请求：`auth:reset-request:email:{normalized_email}` + `auth:reset-request:ip:{trusted_ip_hash}`。
- 密码重置确认：`auth:reset-confirm:token:{hash_prefix}` + `auth:reset-confirm:ip:{trusted_ip_hash}`。
- CSRF 失败：`auth:csrf:session:{session_hash_prefix}` + `auth:csrf:ip:{trusted_ip_hash}`。

默认策略：

- 登录失败：5 次 / 5 分钟，连续窗口内触发后返回 429。
- 注册：5 次 / 5 分钟。
- 重置请求：3 次 / 15 分钟。
- 重置确认：5 次 / 15 分钟。
- CSRF 失败：10 次 / 5 分钟。

`X-Forwarded-For` 只在请求来自可信代理时读取。新增 `SAVEANY_TRUSTED_PROXY_IPS` 或部署文档明确由平台清洗该 header。

## 审计日志

新增 `auth_audit_events` 表：

- `id text primary key`
- `event_type text not null`
- `user_id text`
- `email_hash text`
- `session_hash_prefix text`
- `ip_hash text`
- `user_agent_hash text`
- `success integer not null`
- `reason text`
- `metadata_json text`
- `created_at real not null`

事件类型：

- `register_success`
- `register_failed`
- `login_success`
- `login_failed`
- `logout`
- `logout_all`
- `session_expired`
- `session_revoked`
- `password_reset_requested`
- `password_reset_confirmed`
- `password_reset_failed`
- `csrf_failed`
- `billing_checkout_created`
- `billing_checkout_confirmed`
- `billing_mock_mutation`

禁止记录：

- 明文密码。
- 完整 session token。
- 完整 reset token。
- 完整 Cookie。
- Stripe secret 或 webhook secret。

## 前端设计

### API 请求层

`frontend/src/services/api.js` 统一入口：

- `apiFetch(path, { method, body, authRequired, csrf })`
- 默认 `credentials: "include"`。
- JSON 请求默认带 `Content-Type: application/json`。
- 状态变更默认带 `X-CSRF-Token`。
- 对 `401` / `403` 触发统一会话过期处理。
- 对 `429` 返回“请求太频繁，请稍后再试”。
- 对 `402` 保留额度/升级提示。

`getSummary()`、`askSummaryQuestion()`、`connectSummaryEvents()` 也要显式考虑认证。`EventSource` 在同源下可继续使用 Cookie；如果未来跨域，需要 `EventSource` 的 `withCredentials` 方案或改用 fetch stream。

### Auth 状态机

认证状态：

- `checking`：启动时确认登录状态。
- `anonymous`：未登录。
- `authenticating`：登录或注册提交中。
- `authenticated`：已登录。
- `refreshing`：已登录但正在同步会员和额度。
- `expired`：后端返回 401/403，会话失效。

用户可见文案：

- checking：“正在确认登录状态。”
- anonymous：“登录后每天可免费总结 3 次。”
- authenticating：“正在登录。”
- refreshing：“已登录，正在同步套餐。”
- expired：“登录已过期，请重新登录。”

### 表单状态

表单模式：

- `login`
- `register`
- `reset-request`
- `reset-confirm`

每个模式有 `idle`、`validating`、`submitting`、`success`、`error`。

表单字段：

- 登录：email + current password。
- 注册：email + new password + confirm password。
- 重置请求：email。
- 重置确认：reset token + new password + confirm password。

Autocomplete：

- 登录密码：`autocomplete="current-password"`。
- 注册密码：`autocomplete="new-password"`。
- 重置新密码：`autocomplete="new-password"`。
- reset token：`autocomplete="one-time-code"`。

切换表单模式时清理无关敏感字段，避免旧密码和 reset token 长时间停留在内存状态中。

### 跨标签页同步

使用 `BroadcastChannel("saveany-auth")`，不支持时 fallback 到 `localStorage` event。

事件：

- `login`
- `logout`
- `session-expired`
- `password-reset`

收到事件后：

- login：调用 `refreshMe()`。
- logout / session-expired / password-reset：清理 auth state，但保留用户输入 URL、解析结果和本地工作区。

### AI 总结门禁

状态：

- `idle`
- `analyzed`
- `gatedLogin`
- `creating`
- `running`
- `completed`
- `quotaBlocked`
- `sessionExpired`
- `failed`

未登录时保留解析结果，提示“解析结果已保留，登录后继续自动总结”。登录成功后自动继续创建 summary。会话过期时提示“登录状态已失效，重新登录后继续总结”。

### 支付回跳

状态：

- `idle`
- `returnedSuccess`
- `needsLogin`
- `confirming`
- `active`
- `pendingWebhook`
- `failed`

未登录时提示“登录后继续确认支付”。登录成功后继续使用 `session_id` 调用 Checkout confirm。409 可短暂重试，仍未确认时提示“支付已返回，仍在等待 Stripe 确认，可稍后刷新”。

## 生产配置

新增或明确配置：

- `SAVEANY_ENV=development|production`
- `SAVEANY_ALLOWED_ORIGINS`
- `SAVEANY_TRUSTED_PROXY_IPS`
- `SAVEANY_SESSION_COOKIE`
- `SAVEANY_SESSION_DAYS`
- `SAVEANY_SESSION_IDLE_DAYS`
- `SAVEANY_SECURE_COOKIES`
- `AUTH_RATE_LIMIT_ATTEMPTS`
- `AUTH_RATE_LIMIT_WINDOW_SECONDS`
- `PASSWORD_RESET_TOKEN_MINUTES`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `PUBLIC_APP_URL`
- `BILLING_MODE`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRO_MONTHLY_PRICE_ID`

生产启动校验：

- `SAVEANY_ENV=production` 时必须 `SAVEANY_SECURE_COOKIES=true`。
- `SAVEANY_ENV=production` 时禁止 `SAVEANY_DEV_MODE=true`。
- `SAVEANY_ENV=production` 时禁止 `BILLING_MODE=mock`。
- `SAVEANY_ENV=production` 时 `PUBLIC_APP_URL` 必须是 HTTPS。
- `SAVEANY_ENV=production` 时 `SAVEANY_ALLOWED_ORIGINS` 必须显式配置，不能为 `*`。
- Stripe 模式必须配置 Stripe secret、webhook secret 和 price id。
- 密码重置生产启用时必须配置 SMTP。

## 数据清理

启动或定时清理：

- 过期 session：保留 90 天审计窗口后删除，或先撤销再延迟删除。
- 已使用/过期 password reset token：保留 30 天后删除。
- 过期 rate limit 记录：重置窗口结束后 24 小时删除。
- auth audit events：默认保留 180 天。
- billing attempts：默认保留 180 天。
- stripe events：默认保留 1 年。

SQLite 单实例部署可在启动时清理。多实例部署需要迁移到专门 job 或外部队列。

## 测试验收

### 后端认证测试

- 注册成功设置安全 Cookie。
- 登录成功设置安全 Cookie。
- `SAVEANY_SECURE_COOKIES=true` 时 Cookie 包含 `Secure`。
- 生产 Cookie 名使用 `__Host-saveany_session`。
- 重复注册标准化邮箱被拒绝。
- 不存在邮箱和错误密码返回同样登录错误。
- 登录失败触发限流。
- 注册触发限流。
- 密码重置请求隐藏账号存在性。
- 密码重置请求触发限流。
- 密码重置确认 token 单次使用。
- 密码重置确认 token 过期失败。
- 密码重置确认触发限流。
- 密码重置成功后旧 session 全部失效。
- logout 撤销当前 session。
- logout all 撤销全部 session。
- 非 active 用户不能登录，已有 session 不能访问 `/api/me`。

### CSRF 测试

- 已登录 POST 缺少 `X-CSRF-Token` 返回 403。
- 已登录 POST 使用错误 token 返回 403。
- 已登录 POST 使用正确 token 成功。
- 跨 Origin 请求被拒绝。
- Stripe webhook 不要求 CSRF，但坏签名继续被拒绝。

### 资源归属测试

- 用户 A 创建 summary 后，用户 A 可读取状态、SSE、问答和 Markdown。
- 用户 B 访问用户 A 的 summary 状态返回 404。
- 用户 B 访问用户 A 的 Markdown 返回 404。
- 用户 B 对用户 A 的 summary 提问返回 404。
- 缓存命中时用户 B 获得自己的 task ID，不复用用户 A 的 task ID。

### 前端测试

- `apiFetch` 对状态变更请求带 credentials 和 CSRF header。
- 401/403 触发会话过期状态。
- 登录、注册、退出会广播跨标签页事件。
- 密码 autocomplete 按模式正确切换。
- 登录后继续 AI 总结门禁任务。
- 支付回跳未登录时登录后继续确认。
- 429 展示“请求太频繁，请稍后再试”。

### 配置测试

- `SAVEANY_ENV=production` 且 `SAVEANY_SECURE_COOKIES=false` 启动失败。
- `SAVEANY_ENV=production` 且 `SAVEANY_DEV_MODE=true` 启动失败。
- `SAVEANY_ENV=production` 且 `BILLING_MODE=mock` 启动失败。
- CORS allowlist 不允许 `*` 搭配 credentials。
- Stripe 模式缺少 secret 时启动或接口返回明确配置错误。

## 分阶段实施

### 第一阶段：阻断高风险

1. Summary ownership 与读取授权。
2. 密码重置成功撤销所有 session。
3. 生产 Cookie 和生产配置启动校验。
4. CSRF token 和 Origin 校验。
5. 后端核心测试。

### 第二阶段：完善可靠性

1. 前端统一 `apiFetch`。
2. 会话过期状态机。
3. 跨标签页同步。
4. 登录表单校验和 autocomplete。
5. 支付回跳和 AI 总结门禁状态整理。

### 第三阶段：运营安全

1. `auth_audit_events`。
2. SMTP 生产邮件。
3. 数据清理任务。
4. 监控告警。
5. 弱密码/泄露密码检查。

## 参考资料

- FastAPI Response Cookies: https://fastapi.tiangolo.com/advanced/response-cookies/
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- MDN Secure Cookie Configuration: https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies
