import os

from openai import OpenAI

from app.core.config import ConfigStore


class LLMRouter:
    """Calls Ollama first and uses an external API only when it is enabled."""

    def __init__(
        self,
        config_store: ConfigStore | None = None,
        client_factory=OpenAI,
        timeout_seconds: float = 120,
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

    def complete(self, messages: list[dict], tools: list[dict] | None = None):
        errors = []

        for provider, base_url, api_key, model in self._candidates():
            try:
                client = self.client_factory(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=self.timeout_seconds,
                )
                request = {"model": model, "messages": messages}
                if tools:
                    request["tools"] = tools
                    request["tool_choice"] = "auto"
                if provider == "local":
                    # Qwen3 默认带思考，CPU 部署下非常慢。Ollama 的 OpenAI 兼容
                    # 接口会忽略 think=false（qwen3:4b 实测无效），所以额外在
                    # 消息里加 /no_think 指令，Qwen3 模板识别后会彻底关闭思考。
                    request["extra_body"] = {
                        "think": False,
                        "reasoning_effort": "minimal",
                    }
                    request["messages"] = [
                        {"role": "system", "content": "/no_think"},
                        *messages,
                    ]

                return client.chat.completions.create(**request)
            except Exception as error:
                errors.append(f"{provider}: {error}")

        raise RuntimeError(
            "模型暂时不可用。请确认 Ollama 已启动、模型已下载，"
            "或在管理页启用 API 回退。"
        ) from Exception(" | ".join(errors))
