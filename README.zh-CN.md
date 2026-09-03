# Company Agent

面向小公司的本地优先 AI Agent。员工用独立账号登录；管理员在网页中配置模型与资源开关。默认只调用公司服务器上的本地模型，外部 API 只是显式启用后的故障回退。

## 快速安装

Windows（管理员 PowerShell）：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
```

Linux：

```sh
chmod +x scripts/install.sh && ./scripts/install.sh
```

安装脚本会安装 Python 依赖、Ollama，并拉取 `qwen3:8b`。这是当前推荐的默认模型：Ollama 的 Qwen3 8B 包约 5.2GB，适合具备约 16GB RAM 的小公司服务器；内存较小可改为 `qwen3:4b`，有更高吞吐需求可选 `qwen3:14b`。

创建管理员与启动：

```sh
.venv/bin/python -m app.bootstrap admin "请换成至少12位的强密码" --admin
.venv/bin/uvicorn app.web:app --host 0.0.0.0 --port 8000
```

Windows 将 `.venv/bin/` 替换为 `.venv\Scripts\`。访问 `http://服务器地址:8000`，使用管理员账号登录。生产环境请部署在 HTTPS 反向代理之后，并设置强随机 `SESSION_SECRET` 和 `SESSION_COOKIE_SECURE=true`；不要将 `.env`、用户数据库或 `data/company_config.json` 提交到 Git。

## 配置与扩展

管理员页面可配置本地 Ollama 地址、模型、API 回退和资源开关。API 密钥只从服务器环境变量 `API_LLM_KEY` 读取，不保存在网页配置中。资源目录提供文件、网站搜索，以及邮件、CRM、企业网站的标准扩展占位；启用开关不等同于已接入第三方凭证，实际连接器应按业务系统实现并添加最小权限与审计。

Ollama 提供 OpenAI 兼容的 `/v1/chat/completions` 接口，因此现有 OpenAI SDK 可直连本地端点；本项目会优先尝试本地端点，失败时才在管理员显式启用且服务器具备 API 密钥的情况下回退。

## 技能（Skills）

技能是扩展 Agent 工具集的小型插件，不需要改动核心代码。每个技能放在 `skills/<name>/` 目录，包含 `skill.json` 清单（名称、入口模块、依赖和工具 schema）以及暴露 `SKILL_META["tools"]` 的 Python 模块。系统在运行时发现技能，只有管理员启用后才会注册其工具：

- 在管理配置页的“技能”分组中启用/停用，或
- 管理员在网页聊天中说“安装 pdf skill / 启用 pdf 技能”，可立即启用（会保存到 `data/company_config.json`）。

自带的 `pdf` 技能（`skills/pdf/`）提供 `pdf_read` 工具：读取“本地可操作目录”内的 PDF 并提取文本，让模型可以总结或问答 PDF 内容。它依赖 `pypdf`，并继承文件工具的安全规则（禁止越界、禁止隐藏文件）。

## 验证

```sh
.venv/bin/python -m pytest -q
```

测试涵盖本地优先/API 回退、配置保存、密码验证、登录/管理员权限、资源开关、文件安全与既有 Agent 工具循环。
