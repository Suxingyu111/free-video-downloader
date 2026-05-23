# 开源安全与项目完善设计方案

## 背景

SaveAny 准备以开源仓库形式对外发布。项目包含前端 Vue SPA、后端 FastAPI、公开视频解析、AI 总结、字幕/转写、Stripe 会员、SEO/GEO 静态内容和本地运行数据等能力。开源前需要确认当前提交内容不包含个人配置、密钥、运行数据或其他不适合公开的信息，并补齐开源项目应具备的安全治理、供应链治理和贡献协作机制。

本方案基于 2026-05-24 对当前工作区的审查结果、联网查询的 GitHub/OpenSSF/Choose a License 公开资料，以及 Context7 查询的 Gitleaks 和 GitHub Actions 文档整理。

## 目标

- 确认已跟踪文件和准备提交文件不包含真实密钥、私钥、个人路径、个人邮箱、运行数据库、下载视频、日志或站长平台验证 token。
- 建立开源前的安全门禁，避免后续提交引入敏感信息。
- 补齐开源仓库基础治理文件，让外部用户理解许可证、漏洞报告方式、贡献流程和行为准则。
- 补齐依赖、CI、Secret scanning、Scorecard 等自动化能力，降低供应链风险。
- 形成可执行的开源前验收清单。

## 非目标

- 不在本方案中修改业务功能、下载能力、AI 总结能力或会员计费逻辑。
- 不在本方案中选择最终商业化策略。
- 不承诺开源后完全不存在安全风险；本方案建立的是可审计、可持续运行的风险降低机制。
- 不处理已经发布到远程公开仓库后的密钥泄露应急流程；如历史提交发现真实密钥，需要单独执行密钥吊销和历史清理。

## 当前审查结论

当前代码具备开源基础，但尚未达到建议的开源发布完成状态。

已确认事项：

- `.gitignore` 已忽略 `backend/.env`、`runtime/`、`output/`、`frontend/node_modules/`、`.tmp/`、`.npm-cache/`、构建产物和常见本地缓存。
- `backend/.env` 存在于本地工作区，但未被 git 跟踪。
- 已跟踪文件中未发现真实 API Key、私钥、个人路径、个人邮箱、真实站长验证 token 或生产 `.env` 泄露。
- `detect-secrets` 扫描命中均为未验证项，主要来自测试假密码、变量名、示例 Stripe key 形态、lock 文件哈希和长测试字符串。
- `npm audit --omit=dev --audit-level=moderate` 返回 `found 0 vulnerabilities`。

待处理事项：

- 仓库缺少 `LICENSE`、`SECURITY.md`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`。
- 仓库缺少 `.github/` 下的 CI、Dependabot、CodeQL、Gitleaks 和 OpenSSF Scorecard 配置。
- `pip-audit` 因网络代理重试未完成，后端依赖漏洞审计不能视为已通过。
- `backend/.env.example` 和部分测试中存在 `stripe_secret_placeholder`、`stripe_secret_placeholder`、`stripe_webhook_placeholder` 这类示例值，虽然不是泄露，但容易触发扫描误报。
- 工作区当前仍有 `findings.md`、`progress.md`、`task_plan.md` 未跟踪文件，需要决定是否正式纳入文档或移除。
- `frontend/package.json` 仍是 `"private": true`。这不影响以 GitHub 仓库形式开源，但需要明确项目不作为 npm 包发布，或补充 `license`、`repository`、`bugs`、`homepage` 等元数据。

## 风险分级

### P0：发布前必须完成

1. 敏感文件隔离

   保持 `.gitignore` 对 `.env`、运行数据库、日志、下载视频、音频、缓存和构建产物的忽略。开源前执行 `git status --ignored`，确认 ignored 文件未被强制加入。

2. Secret scanning

   增加 Gitleaks 扫描，覆盖本地 pre-commit、CI 和历史提交扫描。Context7 查询的 Gitleaks 文档确认其支持 pre-commit hook 和 GitHub Action，可用于阻止包含敏感信息的提交。

3. 开源许可证

   增加 `LICENSE`。如果没有许可证，代码仍受版权保护，外部用户无法明确复制、修改和分发权限。许可证建议由项目所有者确认；常见选择是 MIT、Apache-2.0 或 AGPL-3.0。

4. 安全策略

   增加 `SECURITY.md`，说明支持版本、漏洞报告渠道、响应预期、不要公开提交漏洞利用细节等规则。GitHub 文档建议通过安全策略文件说明如何报告漏洞。

5. 最小权限 CI

   增加 GitHub Actions 工作流，并将默认 `permissions` 设置为 `contents: read`。Context7 查询的 GitHub Actions 文档建议工作流凭据遵循最小权限原则，仅在特定 job 需要时提升权限。

6. 依赖治理

   增加 Dependabot 配置，覆盖 `npm`、`pip` 和 GitHub Actions。前端继续使用 `package-lock.json` 进行可复现安装，后端补充锁定方案或至少在 CI 中执行漏洞审计。

### P1：强烈建议发布前完成

1. 示例值降噪

   将示例配置和测试中的 `stripe_secret_placeholder`、`stripe_secret_placeholder`、`stripe_webhook_placeholder` 等改成明显不会被识别为真实供应商密钥的占位符，例如 `replace_with_stripe_secret_key`、`test_stripe_secret_placeholder`。

2. 社区健康文件

   增加 `CONTRIBUTING.md` 和 `CODE_OF_CONDUCT.md`，明确本地启动、测试、文档更新、提交信息、PR 要求、漏洞不要走普通 issue 等规则。

3. 供应链评分

   增加 OpenSSF Scorecard workflow。OpenSSF Scorecard 用于快速识别开源项目中的风险实践，可作为开源后持续改进指标。

4. 文档整理

   将内部执行计划和对外文档区分清楚。`docs/superpowers/plans/` 适合保留开发历史，但正式 README 应引导用户阅读稳定的安装、架构、API、配置、安全和贡献文档。

5. 发布前状态文档

   增加 `docs/status/open-source-readiness.md`，记录本次扫描命令、扫描结果、剩余风险和发布前签核状态。

### P2：开源后持续优化

1. CodeQL 或等价静态分析。
2. Dependabot 自动 PR 分组和自动标签。
3. 发布 SBOM，例如 CycloneDX。
4. 增加 Dockerfile 与 compose 示例，降低自托管门槛。
5. 增加 issue templates 和 pull request template。
6. 增加安全公告流程和版本化 release note。

## 文件与配置设计

### 根目录治理文件

计划新增：

- `LICENSE`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`

`SECURITY.md` 至少包含：

- 支持的版本或分支。
- 漏洞报告方式。
- 不应公开提交真实漏洞利用细节。
- 维护者响应时间预期。
- 涉及第三方平台、AI 服务、Stripe 和公开视频平台时的边界说明。

`CONTRIBUTING.md` 至少包含：

- 本地开发环境。
- 前端测试和构建命令。
- 后端测试命令。
- 文档更新规则。
- Secret scanning 要求。
- PR 描述与验证要求。
- 中文 commit message 约定。

### GitHub 自动化目录

计划新增：

```text
.github/
  workflows/
    ci.yml
    secret-scan.yml
    scorecard.yml
    codeql.yml
  dependabot.yml
  ISSUE_TEMPLATE/
  pull_request_template.md
```

`ci.yml` 设计：

- 默认 `permissions: contents: read`。
- 前端 job：`npm ci`、`npm test`、`npm run build`。
- 后端 job：创建虚拟环境、安装 `backend/requirements.txt`、运行 `pytest`。
- 可选 job：`npm audit --omit=dev --audit-level=moderate`、`pip-audit -r backend/requirements.txt`。

`secret-scan.yml` 设计：

- 使用 Gitleaks 对 PR 和 push 执行扫描。
- 输出使用 redact 模式，避免日志泄露疑似值。
- 对示例占位符误报建立显式 allowlist，但优先修改占位符文本，而不是放宽扫描。

`dependabot.yml` 设计：

- `npm`：目录 `/frontend`，每周检查。
- `pip`：目录 `/backend`，每周检查。
- `github-actions`：目录 `/`，每周检查。

`scorecard.yml` 设计：

- 每周或主分支 push 执行。
- 使用最小权限。
- 输出结果用于安全改进，不阻塞初期开发；稳定后再考虑作为强门禁。

### 示例配置与测试数据

需要将示例密钥形态统一降噪：

- `STRIPE_SECRET_KEY=replace_with_stripe_secret_key`
- `STRIPE_WEBHOOK_SECRET=replace_with_stripe_webhook_secret`
- `AI_API_KEY=`
- `INDEXNOW_KEY=`

测试中如果必须表达 Stripe live/test key 语义，使用不匹配真实密钥正则的字符串，例如：

- `stripe_secret_placeholder`
- `stripe_webhook_placeholder`
- `price_placeholder`

### 运行数据隔离

当前本地存在以下 ignored 数据类型，开源前不得进入 git：

- `backend/.env`
- `backend/runtime/`
- `runtime/`
- `output/`
- `frontend/dist/`
- `.tmp/`
- `.npm-cache/`
- `.pytest_cache/`
- `.DS_Store`

发布前检查命令：

```bash
git status --short --ignored
git ls-files
git ls-files | rg '(^|/)(\.env|runtime|output|dist|node_modules|\.tmp|\.npm-cache)|\.(mp4|m4a|wav|db|sqlite|log)$'
```

最后一条命令如果有输出，需要逐项确认是否误跟踪。

## 开源前验证流程

### 1. 文件泄露检查

```bash
git status --short --ignored
git ls-files
git grep -n -I -E '(api[_-]?key|secret|token|password|credential|private[_ -]?key|BEGIN [A-Z ]*PRIVATE KEY|sk_live|pk_live|whsec_|ghp_|github_pat_|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35})' -- .
```

预期：

- 只出现示例变量名、文档说明、测试假值。
- 不出现真实密钥、私钥、个人路径、真实邮箱、真实域名管理 token。

### 2. Secret scanner

```bash
gitleaks detect --source . --redact
detect-secrets scan --all-files $(git ls-files)
```

预期：

- 无 verified secret。
- 未验证命中项有明确解释或被修正为不会误报的占位符。

### 3. 前端供应链审计

```bash
cd frontend
npm ci
npm audit --omit=dev --audit-level=moderate
npm test
npm run build
```

预期：

- audit 无中高危生产依赖漏洞。
- 测试和构建通过。

### 4. 后端供应链审计

```bash
cd backend
python -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pytest
./.venv/bin/python -m pip_audit -r requirements.txt
```

预期：

- pytest 通过。
- `pip-audit` 能完成并无未处理的高危漏洞。

### 5. 仓库健康检查

```bash
ossf-scorecard --repo=<public-repo-url>
```

预期：

- 记录初始分数。
- 对 Branch-Protection、Token-Permissions、Dangerous-Workflow、Pinned-Dependencies、Security-Policy、License 等检查制定后续优化项。

## 验收标准

开源发布前必须满足：

- `git status --short` 中无意外未跟踪文件或本地运行数据。
- `git ls-files` 中不包含 `.env`、运行数据库、日志、下载视频、音频缓存或构建产物。
- Gitleaks 或等价扫描无真实密钥发现。
- `LICENSE`、`SECURITY.md`、`CONTRIBUTING.md` 已存在。
- GitHub Actions CI 至少覆盖前端测试/构建和后端测试。
- Dependabot 已覆盖前端、后端和 GitHub Actions。
- README 中明确项目边界：只面向有权访问的公开视频，不提供 DRM 绕过、付费内容绕过、Cookie 托管或共享账号能力。
- 发布说明记录已执行的安全审查命令和结果。

## 实施顺序

1. 新增许可证和社区健康文件。
2. 修正示例密钥和测试假值，降低 secret scanner 误报。
3. 新增 Gitleaks 配置、pre-commit 示例和 GitHub Action。
4. 新增 CI、Dependabot、Scorecard。
5. 补充 `docs/status/open-source-readiness.md`。
6. 执行完整验证流程。
7. 根据验证结果更新 README 和发布说明。

## 参考资料

- GitHub Docs: [Adding a security policy to your repository](https://docs.github.com/en/code-security/getting-started/adding-a-security-policy-to-your-repository)。
- GitHub Actions 文档：`GITHUB_TOKEN` 权限应遵循最小权限原则。
- Gitleaks 文档：支持 pre-commit hook 和 GitHub Action，可用于仓库 secret scanning。
- OpenSSF Scorecard: [scorecard.dev](https://scorecard.dev/)，用于识别开源项目供应链和安全实践风险。
- Choose a License: [No License](https://choosealicense.com/no-permission/)，没有许可证并不等于开源授权，代码仍受版权保护。
