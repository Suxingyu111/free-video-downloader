# AI 问答月度额度设计

## 背景

当前 AI 问答会调用大模型回答用户对视频总结的追问，因此需要明确的成本边界。现有实现按“每个总结、每个用户”的追问次数限制：免费版每个总结 3 次，Pro 每个总结 20 次。这个模型对用户不够直观，也会让 Pro 重度用户在生成大量总结后产生较高的大模型成本。

本设计把 AI 问答改成账号级月度额度，只在免费版和 Pro 套餐内限制每月 AI 问答次数。

## 目标

- 免费版每月 10 次 AI 问答。
- Pro 个人版每月 200 次 AI 问答。
- 额度不足时在调用大模型之前拦截，避免产生成本。
- 大模型回答失败时退回本次 AI 问答额度。
- 前端展示 AI 问答剩余额度，并在成功问答后实时更新。
- 不再限制“每个总结最多追问几次”，只按账号月度总次数限制。

## 非目标

- 第一版不设计 AI 问答按量包。
- 第一版不按 token、输入长度或输出长度计费。
- 第一版不迁移历史 `summary_questions` 数据到月度额度。
- 第一版不删除 `summary_questions` 表，避免破坏历史数据和潜在统计用途。

## 套餐规则

AI 问答采用统一月度额度：

- 未登录用户：不能使用 AI 问答。
- 免费版：每月 10 次 AI 问答。
- Pro 个人版：每月 200 次 AI 问答。
- 额度周期：使用现有月度周期 `PeriodType.MONTH` 和 `current_period_key(PeriodType.MONTH)`。
- 扣费单位：每次成功获得 AI 回答扣 1 次。
- 失败处理：大模型调用失败时退回本次预扣额度。

套餐页文案：

- 免费版：`每月 10 次 AI 问答`
- Pro 个人版：`每月 200 次 AI 问答`

账户菜单和个人中心文案：

- `AI 问答还剩 X 次`

## 后端设计

### 计划配置

`PlanLimits` 将当前的 `questions_per_summary` 替换为账号级月度字段：

```python
question_monthly_limit: int | None = None
```

`PLAN_CATALOG` 配置：

```python
"free": PlanLimits(
    ...
    question_monthly_limit=10,
)

"pro": PlanLimits(
    ...
    question_monthly_limit=200,
)
```

### 额度计算

`MeterType.QUESTION` 继续复用现有枚举值 `question`。

`allowance_for_user(user, MeterType.QUESTION)` 返回：

- `period_type = PeriodType.MONTH`
- `period_key = current_period_key(PeriodType.MONTH)`
- `limit = limits.question_monthly_limit or 0`
- `column = "question_count"`

AI 问答使用现有 `usage_periods.question_count` 字段记录月度用量：

```text
usage_periods
period_type = "month"
period_key = "YYYY-MM"
question_count = 本月已用 AI 问答次数
```

### 问答接口流程

接口保持不变：

```text
POST /api/summaries/{summary_id}/questions
```

处理流程：

1. 校验用户已登录。
2. 校验 session CSRF。
3. 校验用户拥有该总结。
4. 校验总结状态为 `completed`。
5. 校验问题文本非空。
6. 在调用大模型前预扣 1 次 AI 问答额度：
   ```python
   reserve_user_meter(user, MeterType.QUESTION, 1, reservation_id=reservation_id)
   ```
7. 如果额度不足，返回 `402`，不调用大模型。
8. 如果额度充足，调用大模型生成回答。
9. 大模型调用成功：保留扣减，并返回回答和最新 usage。
10. 大模型调用失败：调用 `refund_reservation(reservation_id)`，退回本次问答额度，再返回友好错误。

推荐 `reservation_id` 格式：

```text
question_{summary_id}_{random_token}
```

同一个总结可以连续追问多次，所以 reservation id 必须每次唯一，不能只使用 `summary_id`。

### 错误提示

第一版统一使用：

```text
本月 AI 问答次数已用完，请下月继续使用或升级套餐。
```

这样免费版和 Pro 都可以复用同一套处理逻辑。后续如果需要更精细的文案，可以根据套餐状态区分：

- 免费用户：`本月 AI 问答次数已用完，请升级 Pro 或下月继续使用。`
- Pro 用户：`本月 AI 问答次数已用完，请下月继续使用。`

### 兼容策略

旧表 `summary_questions` 保留，但不再作为额度判断来源。

原因：

- 保留历史数据。
- 避免破坏现有数据库结构。
- 未来如果需要做“某个总结下问答统计”，仍可复用。

上线后不迁移历史问答次数到月度额度。新逻辑从用户下一次 AI 问答开始写入 `usage_periods.question_count`。

## 前端设计

### 额度展示

`entitlement_status` 需要新增 `meters.question`，前端使用 `usage.meters.question.remaining` 展示剩余次数。

账号菜单新增：

```text
AI 问答还剩 X 次
```

AI 问答区域在输入框附近展示：

```text
本月 AI 问答还剩 X 次
```

套餐页新增：

- 免费版：`每月 10 次 AI 问答`
- Pro 个人版：`每月 200 次 AI 问答`

### 提问交互

- 前端可以根据 `usage.meters.question.remaining === 0` 禁用提交按钮。
- 即使前端禁用，后端仍是最终权限来源。
- 问答成功后，后端响应带最新 usage，前端调用 `applyUsageState` 实时刷新剩余额度。
- 问答失败时展示后端友好错误；如果失败响应包含最新 usage，前端同步恢复显示。

## 数据流

```text
用户提交问题
  -> 前端 POST /api/summaries/{summary_id}/questions
  -> 后端校验 summary ownership/status
  -> 后端 reserve_user_meter(question, 1)
  -> 额度不足：返回 402，不调用大模型
  -> 额度充足：调用大模型
  -> 成功：返回 answer + usage
  -> 失败：refund_reservation + 返回错误
  -> 前端更新问答历史和 usage
```

## 测试计划

后端测试：

1. 免费版月度额度：
   - 免费用户连续问 10 次成功。
   - 第 11 次返回 `402`。
   - 第 11 次不调用大模型。

2. Pro 月度额度：
   - Pro 用户可问 200 次。
   - 第 201 次返回 `402`。

3. 失败退款：
   - 预扣 1 次问答额度。
   - 模拟大模型失败。
   - 确认 `usage_periods.question_count` 回滚。
   - 确认下一次仍可继续问。

4. 取消每总结限制：
   - 免费用户可以在同一个总结中问超过旧的 3 次。
   - 只要本月 10 次未用完，就不触发旧限制。

5. usage 返回：
   - 问答成功后响应包含 `usage.meters.question.remaining`。
   - 前端可实时刷新。

前端测试：

1. 套餐页显示 `每月 10 次 AI 问答` 和 `每月 200 次 AI 问答`。
2. 账号菜单显示 `AI 问答还剩 X 次`。
3. 问答区域显示本月剩余 AI 问答次数。
4. 问答成功后调用 `applyUsageState` 更新额度。
5. AI 问答额度为 0 时提交按钮不可用或展示友好提示。

浏览器验证：

1. 注册免费测试用户。
2. 生成或复用一个已完成 AI 总结。
3. 连续提问，观察 AI 问答剩余次数实时减少。
4. 第 10 次后额度变成 0。
5. 第 11 次提示额度不足。
6. 数据库确认 `usage_periods.question_count = 10`。

## 验收标准

- AI 问答不会绕过月度额度。
- 额度不足时不会调用大模型。
- 大模型失败时会退回本次问答额度。
- 前端显示和后端账本一致。
- 免费版和 Pro 都只按账号月度总次数限制，不再按单个总结限制。
- 现有 AI 总结、语音转写、解析、下载额度逻辑不受影响。
