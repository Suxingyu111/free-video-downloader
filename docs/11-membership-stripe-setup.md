# 会员与 Stripe 配置

SaveAny 的下载功能继续免费。AI 总结需要登录账号，免费账号每天默认 3 次额度，专业版会员解锁高频使用。

## 本地无外网测试

使用 mock billing：

```bash
BILLING_MODE=mock
```

启动后端和前端，注册账号，打开套餐页，使用“模拟开通”“模拟取消”“模拟过期”“模拟付款失败”按钮验收会员状态。Mock billing 写入真实的本地 SQLite 会员表，因此可以覆盖登录、额度、购买、取消、过期和付款失败状态。

## Stripe Test Mode

1. 在 Stripe Dashboard 创建 Product：`SaveAny Pro`。
2. 在 Stripe Dashboard 创建以下 Prices：
   - `SaveAny Pro`：月度 recurring Price，`¥19`，currency 为 `cny`。
   - `总结小包`：one-time Price，`¥6`，currency 为 `cny`。
   - `总结大包`：one-time Price，`¥19`，currency 为 `cny`。
   - `转写小包`：one-time Price，`¥8`，currency 为 `cny`。
   - `转写大包`：one-time Price，`¥29`，currency 为 `cny`。
3. 复制本地 Stripe 配置模板：

```bash
cp backend/config/stripe.env.example backend/config/stripe.env
```

4. 编辑 `backend/config/stripe.env`：

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

`backend/config/stripe.env` 已被 git 忽略，不要提交真实密钥。Shell 环境变量仍然会覆盖该文件，方便生产部署平台使用 Environment Variables。

5. 启动 Stripe CLI：

```bash
stripe listen --forward-to http://127.0.0.1:8000/api/billing/webhook
```

把 Stripe CLI 输出的 `whsec_...` 填入 `STRIPE_WEBHOOK_SECRET`，然后重启后端。

6. 打开套餐页，点击“开通专业版 ¥19/月”或购买按量包，用 Stripe test card 完成 Checkout。
7. 回到 SaveAny 后等待 webhook 确认会员状态。

前端成功回跳不会自行开通会员。会员状态只由后端在 Stripe webhook 验签通过后更新。

## 开发提示

- 默认数据库路径是 `runtime/saveany.db`，可用 `SAVEANY_DB_PATH` 覆盖。
- 默认 session cookie 名是 `saveany_session`，可用 `SAVEANY_SESSION_COOKIE` 覆盖。
- 账号接口默认按 IP 和邮箱做 5 次 / 5 分钟基础限流，可用 `AUTH_RATE_LIMIT_ATTEMPTS` 和 `AUTH_RATE_LIMIT_WINDOW_SECONDS` 调整。
- 生产 HTTPS 环境应设置 `SAVEANY_SECURE_COOKIES=true`。
- `checkout.session.completed`、subscription 和 invoice webhook 可能乱序到达；后端只以服务端存储的订阅状态为准，不依赖成功页或单个事件顺序。
