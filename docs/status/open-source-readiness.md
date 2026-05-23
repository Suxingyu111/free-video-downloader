# 开源准备实施状态

## 当前状态

本批次按 `docs/architecture/open-source-security-readiness-design.md` 实施开源准备能力，重点覆盖敏感信息隔离、开源治理文件、GitHub 自动化、安全扫描、依赖治理和状态记录。

## 已完成范围

- 新增 `LICENSE`，当前采用 MIT License。
- 新增 `SECURITY.md`，说明支持范围、漏洞报告方式、安全边界和密钥处理要求。
- 新增 `CONTRIBUTING.md`，说明本地开发、测试验证、文档更新、密钥要求和 PR 要求。
- 新增 `CODE_OF_CONDUCT.md`，明确社区协作行为准则。
- 新增 `.pre-commit-config.yaml`，提供 Gitleaks pre-commit hook。
- 新增 `.gitleaks.toml`，启用默认规则并允许明确占位符与生成 lock hash。
- 新增 `.gitleaksignore`，记录已确认的历史 Gitleaks 误报 fingerprint。
- 新增 `.github/dependabot.yml`，覆盖 npm、pip 和 GitHub Actions。
- 新增 `.github/workflows/ci.yml`，覆盖前端测试/构建、后端测试和依赖审计。
- 新增 `.github/workflows/secret-scan.yml`，使用 Gitleaks 执行 secret scanning。
- 新增 `.github/workflows/codeql.yml`，覆盖 JavaScript/TypeScript 和 Python CodeQL 分析。
- 新增 `.github/workflows/scorecard.yml`，运行 OpenSSF Scorecard 并上传 SARIF。
- 新增 issue templates 和 PR template，提醒不要公开提交安全漏洞、密钥、Cookie 或私密链接。
- 修正 `.env.example`、README、Stripe 文档和测试中的 Stripe 示例值，避免使用看起来像真实供应商密钥的格式。
- 为 `frontend/package.json` 补充 license、repository、bugs 和 homepage 元数据。

## 重要约束

- `backend/.env`、`runtime/`、`output/`、`frontend/dist/`、`.tmp/`、`.npm-cache/`、数据库、日志、下载视频和音频缓存仍必须保持 ignored 状态，不得进入 git。
- SaveAny 仍只面向用户有权访问的公开视频，不提供 DRM 绕过、付费内容绕过、私密内容抓取、Cookie 托管、共享账号、二维码登录或验证码绕过能力。
- 生产部署仍需要部署者自行配置 HTTPS、强随机盐、生产 Cookie 安全属性、Stripe webhook secret、AI API key、运行时清理和滥用防护。

## 验证记录

本节记录本批次完成后的本地验证结果。若命令因网络或平台环境失败，应记录为未通过或未完成，不能视为已通过。

| 验证项 | 命令 | 当前结果 |
| --- | --- | --- |
| 前端依赖审计 | `cd frontend && npm audit --omit=dev --audit-level=moderate` | 通过，`found 0 vulnerabilities` |
| 前端测试 | `cd frontend && npm test` | 通过，116 个测试通过 |
| 前端构建 | `cd frontend && npm run build` | 通过，Vite 生产构建完成 |
| 后端定向测试 | `cd backend && ./.venv/bin/python -m pytest tests/test_app_config.py tests/test_billing_stripe_webhook.py` | 通过，52 个测试通过 |
| 后端全量测试 | `cd backend && ./.venv/bin/python -m pytest` | 通过，314 个测试通过 |
| Python 依赖审计 | `cd backend && ./.venv/bin/python -m pip_audit -r requirements.txt` | 通过，`No known vulnerabilities found` |
| 高置信密钥 grep | `git grep -n -I -E '(sk_(live\|test)_...|whsec_...|...)' -- .` | 通过，无输出 |
| detect-secrets | `detect-secrets scan --all-files $(git ls-files)` | 完成，无 verified secret；仍有变量名、测试假密码、lock hash 等未验证命中 |
| Gitleaks | `gitleaks detect --source . --redact --config .gitleaks.toml` | 通过，扫描 113 个提交，`no leaks found` |
| GitHub Actions YAML | `ruby -e 'require "yaml"; ...'` | 通过，所有新增 workflow、Dependabot 和 issue template 可解析 |
| Actionlint | `go run github.com/rhysd/actionlint/cmd/actionlint@latest` | 通过，无报错 |

## Gitleaks 历史误报处理

首次 Gitleaks 历史扫描发现 3 个 `generic-api-key` 命中，均为历史提交中的 SEO/IndexNow 测试或示例 key，不是当前仓库真实凭据。本批次已将对应 fingerprint 写入 `.gitleaksignore`，并重跑 Gitleaks 验证通过。

## 后续建议

- 在 GitHub 仓库设置中启用 Secret scanning、Push protection、Private Vulnerability Reporting 和 branch protection。
- 首次公开前运行一次完整历史提交 secret scanning。
- 根据 OpenSSF Scorecard 首次结果继续优化 pinned actions、branch protection、token permissions 和 release 流程。
