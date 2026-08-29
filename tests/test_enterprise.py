from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.auth import UserStore, verify_password
from app.core.config import ConfigStore
from app.llm.router import LLMRouter


def test_user_store_hashes_and_authenticates(tmp_path):
    store = UserStore(tmp_path / "users.db")
    store.create_user("alice", "correct-horse-battery", "admin")
    assert store.authenticate("alice", "wrong") is None
    assert store.authenticate("alice", "correct-horse-battery") == {"username": "alice", "role": "admin"}


def test_config_store_and_local_first_fallback(tmp_path, monkeypatch):
    config = ConfigStore(tmp_path / "config.json")
    saved = config.load(); saved["llm"]["api_enabled"] = True; config.save(saved)
    monkeypatch.setenv("API_LLM_KEY", "key")
    calls = []
    def factory(api_key, base_url):
        calls.append((api_key, base_url))
        if api_key == "ollama": raise RuntimeError("offline")
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: "api-result")))
    assert LLMRouter(config, factory).complete([{"role": "user", "content": "hi"}]) == "api-result"
    assert calls[0][0] == "ollama" and calls[1][0] == "key"


def test_login_and_admin_configuration(tmp_path, monkeypatch):
    from app import web
    store = UserStore(tmp_path / "users.db"); store.create_user("admin", "correct-horse-battery", "admin")
    monkeypatch.setattr(web, "users", store); monkeypatch.setattr(web, "config_store", ConfigStore(tmp_path / "config.json"))
    client = TestClient(web.app)
    assert client.get("/").status_code == 200
    assert client.post("/login", data={"username": "admin", "password": "correct-horse-battery"}).status_code == 200
    assert client.get("/admin/config").status_code == 200
