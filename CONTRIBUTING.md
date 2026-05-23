# 贡献指南

感谢你愿意参与 SaveAny。这个项目同时包含前端、后端、AI、Stripe、公开视频解析和 SEO/GEO 静态内容，提交前请尽量让变更小而清晰。

## 本地开发

后端：

```bash
cd backend
python -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
./.venv/bin/python main.py
```

前端：

```bash
cd frontend
npm ci
npm run dev
```

默认前端运行在 `http://127.0.0.1:5173`，后端运行在 `http://127.0.0.1:8000`。

## 测试与验证

提交前根据影响范围运行：

```bash
cd backend
./.venv/bin/python -m pytest
```

```bash
cd frontend
npm test
npm run build
```

涉及依赖、CI、安全配置或开源治理时，还应运行：

```bash
cd frontend
npm audit --omit=dev --audit-level=moderate
```

```bash
gitleaks detect --source . --redact
detect-secrets scan --all-files $(git ls-files)
```

## 文档要求

- 后端接口、字段、权限或错误响应变更后，同步更新接口文档。
- 每完成一个独立功能，同步更新状态文档。
- 新增配置项时，同步更新 `backend/.env.example`、README 和相关配置文档。
- 新增开源治理或安全流程时，同步更新 `docs/status/open-source-readiness.md`。

## 密钥与本地数据

不要提交真实 `.env`、API key、Stripe secret、webhook secret、站长平台 token、Cookie 文件、数据库、运行日志、下载视频、转写音频、缓存或构建产物。示例值必须使用明显的占位符，不应使用看起来像真实供应商密钥的格式。

## Pull Request 要求

PR 描述应包含：

- 变更目的。
- 主要改动点。
- 用户可见变化。
- 安全、隐私、兼容性或迁移影响。
- 已执行的验证命令和结果。

Commit title、commit message 和变更说明默认使用简体中文。代码标识符、命令、API 名称、日志原文和第三方报错保持原文。

## 安全问题

请不要通过普通 issue 报告未修复漏洞。请按照 `SECURITY.md` 使用私有安全报告渠道。
