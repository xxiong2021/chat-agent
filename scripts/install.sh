#!/usr/bin/env sh
set -eu
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:8b
echo "Installed. Create an admin: .venv/bin/python -m app.bootstrap admin 'change-this-password' --admin"
