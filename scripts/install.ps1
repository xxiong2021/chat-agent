$ErrorActionPreference = "Stop"
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
winget install --id Ollama.Ollama --exact --accept-package-agreements --accept-source-agreements
ollama pull qwen3:8b
Write-Host "Installed. Create an admin: .\.venv\Scripts\python.exe -m app.bootstrap admin 'change-this-password' --admin"
