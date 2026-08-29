import os
from openai import OpenAI
from app.core.config import ConfigStore
class LLMRouter:
    def __init__(self, config_store: ConfigStore | None = None, client_factory=OpenAI): self.config_store = config_store or ConfigStore(); self.client_factory = client_factory
    def _candidates(self):
        settings = self.config_store.load()["llm"]
        yield settings["local_base_url"], "ollama", settings["local_model"]
        if settings.get("api_enabled") and (key := os.getenv("API_LLM_KEY") or os.getenv("LLM_API_KEY")): yield settings["api_base_url"], key, settings["api_model"]
    def complete(self, messages: list[dict], tools: list[dict] | None = None):
        errors = []
        for base_url, api_key, model in self._candidates():
            try: return self.client_factory(api_key=api_key, base_url=base_url).chat.completions.create(model=model, messages=messages, tools=tools, tool_choice="auto" if tools else None)
            except Exception as error: errors.append(str(error))
        raise RuntimeError("本地 LLM 不可用，且没有可用的 API 回退。" + " | ".join(errors))
