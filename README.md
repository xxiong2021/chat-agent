# Company Agent

A local-first AI agent for small companies. Employees sign in with their own accounts; admins configure models and resource toggles from the web UI. By default it only calls the local model on the company server — external APIs are used solely as an explicitly enabled fallback.

## Quick Start

Windows (run PowerShell as Administrator):

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
```

Linux:

```sh
chmod +x scripts/install.sh && ./scripts/install.sh
```

The installer sets up the Python dependencies and Ollama, and pulls `qwen3:8b`. That is the recommended default model: the Ollama Qwen3 8B package is about 5.2 GB and suits a small-company server with roughly 16 GB of RAM. On machines with less memory, switch to `qwen3:4b`; choose `qwen3:14b` if you need higher throughput.

Create the admin account and start the server:

```sh
.venv/bin/python -m app.bootstrap admin "REPLACE_WITH_A_STRONG_PASSWORD_12+_CHARS" --admin
.venv/bin/uvicorn app.web:app --host 0.0.0.0 --port 8000
```

On Windows, replace `.venv/bin/` with `.venv\Scripts\`. Open `http://<server-address>:8000` and sign in with the admin account. For production, deploy behind an HTTPS reverse proxy and set a strong random `SESSION_SECRET` with `SESSION_COOKIE_SECURE=true`; never commit `.env`, the user database, or `data/company_config.json` to Git.

## Configuration & Extensions

The admin page lets you configure the local Ollama address, model, API fallback, and resource toggles. API keys are only read from the server environment variable `API_LLM_KEY` and are never stored in the web configuration. The resource catalog ships with standard placeholders for files, web search, email, CRM, and the company website; enabling a toggle does not mean third-party credentials are connected — real connectors should be implemented against your business systems with least-privilege access and auditability.

Ollama exposes an OpenAI-compatible `/v1/chat/completions` endpoint, so existing OpenAI SDK clients can talk to the local endpoint directly. This project always tries the local endpoint first and only falls back when an admin has explicitly enabled the fallback and the server has an API key.

## Verification

```sh
.venv/bin/python -m pytest -q
```

Tests cover local-first/API fallback behavior, configuration persistence, password hashing, login/admin authorization, resource toggles, file safety, and the existing agent tool loop.
