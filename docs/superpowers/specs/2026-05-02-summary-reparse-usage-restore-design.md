# AI 总结恢复与主动重解析计数设计

## 背景

当前 AI 总结任务会按视频 URL、语言和 prompt 版本生成缓存 key。`POST /api/summaries` 在发现同 key 的任务时会直接返回已有任务，包括进行中的任务和已完成任务。这个行为导致两个问题：

1. 用户对同一个视频重复点击解析或重新总结时，可能复用已有任务，没有新增用户统计次数。
2. 用户刷新页面后需要恢复上次已完成的视频和总结，但恢复行为不应该被当成一次新的 AI 总结统计。

前端已经有本地工作区持久化和“发现上次解析结果 / 恢复工作区”提示。后端已有免费额度 reservation/refund 机制，当前统计发生在创建新 summary task 之前，任务创建或启动失败会退款。

## 目标

- 用户主动点击“解析视频”后，即使是同一个视频，也重新解析并重新创建 AI 总结任务。
- 用户主动点击“重新总结 / 重试总结”后，也重新创建 AI 总结任务。
- 只要新 AI 总结任务开始创建并进入总结流程，就立即统计用户 AI 总结次数，而不是等总结完成后再统计。
- 用户刷新页面后，如果选择“恢复工作区”，只读取已持久化的视频和总结结果，不统计 AI 总结次数。
- 已完成总结的恢复内容仍然可从服务端任务快照中拉取，AI 问答、导出入口和总结视图保持可用。
- 任务创建失败或 worker 启动失败继续退款；任务运行失败的退款行为保持当前实现，不在本次设计扩大范围。

## 非目标

- 不新增总结历史列表或多版本管理 UI。
- 不改变会员用户无限额度语义。
- 不调整下载任务缓存和恢复逻辑。
- 不把“恢复工作区”改成服务端搜索最近任务；本次仍使用浏览器本地持久化的 summary id。

## 推荐方案

主动请求永远新建总结任务，恢复请求只读已有任务。

前端把用户点击“解析视频”触发的自动总结视为主动请求，因此 `handleAnalyze -> startSummaryForResult(..., { mode: "auto" })` 也会使用强制新建语义。刷新后的恢复流程只执行 `applyWorkspaceSnapshot`、`resumeSummary`、`GET /api/summaries/{id}` 和 SSE/poll，不调用 `POST /api/summaries`。

后端保留 `force` 字段，但将主动请求的路径统一为 `force: true`。当 `force` 为 `true` 时，后端跳过同 URL 缓存命中，创建新的 summary id，预占用户免费额度，并启动总结线程。只有非强制请求才允许返回已完成缓存任务；进行中任务不再作为可复用缓存返回。

## 备选方案

### 方案 A：仅未完成任务新建，已完成任务复用

优点是节省 AI 成本。缺点是用户主动点击后有时扣次数、有时不扣次数，行为不直观，也不符合“主动点击一律重新解析并重新 AI 总结”的要求。

### 方案 B：新增专用恢复接口

优点是语义更显式。缺点是当前前端已经保存了 summary id，`GET /api/summaries/{id}` 已满足恢复需要，新增接口会扩大 API 面而收益有限。

### 方案 C：推荐方案

优点是产品语义最清楚：主动操作是新总结，恢复操作是只读。后端改动集中在缓存命中边界和测试；前端改动集中在 summary task 创建参数和恢复测试。缺点是同 URL 主动点击会增加 AI 成本，这是用户确认过的预期。

## 数据流

### 主动解析

1. 用户点击“解析视频”。
2. 前端清空当前视频和总结状态，调用 `POST /api/analyze` 重新解析视频。
3. 解析成功后，前端调用 `POST /api/summaries`，携带 `force: true`。
4. 后端跳过同 URL 缓存，生成新的 `summary_id`。
5. 后端调用 `reserve_summary_quota(user, summary_id)`，免费用户的 `usage_daily.summary_count` 立即加 1。
6. 后端创建 summary task 并启动 worker。
7. 前端收到新 `summary_id` 后更新账号 usage，并订阅该任务的 SSE/poll。

### 主动重新总结

1. 用户点击“重新总结 / 重试总结”。
2. 前端调用同一个 `startSummaryForResult`，携带非恢复语义。
3. 前端发送 `force: true`。
4. 后端创建新任务并立即统计。

### 刷新恢复

1. 页面加载时读取 `localStorage` 中的工作区快照。
2. 如果快照存在，前端展示“发现上次解析结果”提示。
3. 用户点击“恢复工作区”。
4. 前端应用本地快照并调用 `resumeSummary(summaryId)`。
5. `resumeSummary` 只调用 `GET /api/summaries/{id}` 和 `/events`，不调用 `POST /api/summaries`。
6. 因为没有创建新任务，后端不调用 `reserve_summary_quota`，用户次数不变。

## 后端调整

- `SummaryStore.get_cached_task` 只返回已完成任务。
- `POST /api/summaries` 在 `force: true` 时完全跳过缓存恢复分支。
- 非强制请求可以继续返回已完成缓存，便于未来只读恢复或 API 兼容，但前端主动请求不会使用这条路径。
- 同 URL 未完成任务不会被缓存复用，因此重复点击会新建任务并统计。
- 保持 `quota_user_id` 和 `summary_quota_reservations` 现有机制，避免泄露内部 quota 字段。

## 前端调整

- `startSummaryForResult` 对所有主动模式发送 `force: true`。
- 恢复工作区不调用 `startSummaryForResult`，只调用 `resumePersistedWorkspace`。
- 恢复提示文案保持“恢复工作区 / 保持清空”，但测试要覆盖恢复不创建新 summary task。
- 主动解析前继续调用 `clearCurrentSummary`，避免旧 SSE/poll 干扰新任务。

## 错误处理

- 用户未登录：仍进入 `summaryGate = "login"`，登录后继续主动创建新总结并统计。
- 免费额度不足：后端返回 402，前端显示额度升级提示。
- 任务创建失败或 worker 启动失败：后端退款 reservation，前端显示任务创建失败。
- 运行中失败：保持当前失败处理和退款策略。
- 恢复时 summary id 不存在：前端显示本地化错误，用户可重新解析。

## 测试计划

### 后端

- 同 URL 已完成任务后再次 `force: true` 创建新任务，`summary_id` 不同，`used_today` 增加。
- 同 URL 进行中任务后再次 `force: true` 创建新任务，`summary_id` 不同，`used_today` 增加。
- 非强制请求命中已完成缓存时不统计，用于兼容恢复或 API 只读场景。
- 进行中任务不再通过 `get_cached_task` 复用。

### 前端单元测试

- 主动创建 summary task 时 payload 包含 `force: true`。
- 恢复工作区流程包含 `resumeSummary`/`getSummary`，不调用 `createSummaryTask`。
- 工作区快照继续保存 `currentSummaryId`、`summaryTask` 和总结问答历史。

### 浏览器验证

- 登录免费用户，解析一个 demo 视频，确认 usage 立即从 0 变 1。
- 刷新页面，看到恢复提示；点击“恢复工作区”，确认总结内容恢复，usage 不增加。
- 对同一个视频再次点击“解析视频”，确认生成新的 summary task，usage 增加。
- 在总结未完成时再次触发同 URL 主动解析，确认新建任务且 usage 增加。
