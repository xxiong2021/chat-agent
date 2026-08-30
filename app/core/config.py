import json
from copy import deepcopy
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parents[2] / "data" / "company_config.json"
DEFAULT_CONFIG = {"llm": {"provider": "local", "local_base_url": "http://127.0.0.1:11434/v1", "local_model": "qwen3:0.6b", "api_enabled": False, "api_base_url": "https://api.deepseek.com", "api_model": "deepseek-chat"}, "resources": {"files": {"enabled": True, "root": "."}, "web_search": {"enabled": False}, "email": {"enabled": False}, "crm": {"enabled": False}, "website": {"enabled": False}}}

class ConfigStore:
    def __init__(self, path: Path = CONFIG_FILE): self.path = path
    def load(self) -> dict:
        if not self.path.exists(): return deepcopy(DEFAULT_CONFIG)
        saved = json.loads(self.path.read_text(encoding="utf-8")); config = deepcopy(DEFAULT_CONFIG)
        for section, value in saved.items():
            if isinstance(value, dict) and isinstance(config.get(section), dict): config[section].update(value)
            else: config[section] = value
        return config
    def save(self, config: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True); temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"); temp.replace(self.path)
