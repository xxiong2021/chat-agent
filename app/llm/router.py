import os
from types import SimpleNamespace

import httpx
from openai import OpenAI

from app.core.config import ConfigStore


class LLMRouter:
    """Calls Ollama first and uses an external API only when it is enabled."""

    def __init__(
        self,
        config_store: ConfigStore | None = None,
        client_factory=OpenAI,
        timeout_seconds: float = 180,
    ):
        self.config_store = config_store or ConfigStore()
        self.client_factory = client_factory
        self.timeout_seconds = timeout_seconds

    def _candidates(self):
        settings = self.config_store.load()["llm"]
        yield "local", settings["local_base_url"], "ollama", settings["local_model"]

        api_key = os.getenv("API_LLM_KEY") or os.getenv("LLM_API_KEY")
        if settings.get("api_enabled") and api_key:
            yield "api", settings["api_base_url"], api_key, settings["api_model"]

    def _complete_local(self, base_url: str, model: str, messages: list[dict]):
        # Ollama 原生 /api/chat 才可靠支持 think=false；
        # OpenAI 兼容的 /v1 接口会忽略 qwen3 的 think 参数和 /no_think 指令。
        api_url = base_url.replace("/v1", "").rstrip("/") + "/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": -1,
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(api_url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        message = data.get("message", {})
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=message.get("content", ""),
                        reasoning=message.get("reasoning", ""),
                    )
                )
            ]
        )

    def complete(self, messages: list[dict], tools: list[dict] | None = None):
        errors = []

        for provider, base_url, api_key, model in self._candidates():
            try:
                if provider == "local":
                    # qwen3 模板识别用户消息末尾的 /no_think，双保险关闭思考。
                    local_messages = list(messages)
                    if local_messages and local_messages[-1].get("role") == "user":
                        last = dict(local_messages[-1])
                        last["content"] = str(last.get("content", "")) + "\n/no_think"
                        local_messages[-1] = last
                    else:
                        local_messages.append({"role": "user", "content": "/no_think"})
                    return self._complete_local(base_url, model, local_messages)

                client = self.client_factory(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=self.timeout_seconds,
                )
                request = {"model": model, "messages": messages}
                if tools:
                    request["tools"] = tools
                    request["tool_choice"] = "auto"
                return client.chat.completions.create(**request)
            except Exception as error:
                errors.append(f"{provider}: {error}")

        raise RuntimeError(
            "模型暂时不可用。请确认 Ollama 已启动、模型已下载，"
            "或在管理页启用 API 回退。"
        ) from Exception(" | ".join(errors))
