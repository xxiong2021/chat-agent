import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from app.agent.permissions import PermissionManager
from app.tools.web import web_search
from app.tools.calculator import calculator


load_dotenv()

api_key = os.getenv("LLM_API_KEY")

if not api_key:
    raise RuntimeError(
        "没有找到 LLM_API_KEY，请检查 .env 文件"
    )


client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "搜索互联网，获取最新或实时信息。"
                "如果任务需要多个不同角度的信息，可以多次调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或问题",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算数学表达式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，例如 123 * 456",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]


TOOL_FUNCTIONS = {
    "web_search": web_search,
    "calculator": calculator,
}


# 权限管理器
permission_manager = PermissionManager()


SYSTEM_PROMPT = """
你是一个个人 AI Agent。

你不仅负责回答问题，还负责完成用户交给你的任务。

工作方式：

1. 先理解用户真正想完成的目标。
2. 判断是否需要工具。
3. 如果需要工具，调用合适的工具。
4. 工具返回结果后，分析结果。
5. 如果任务还没有完成，可以继续调用工具。
6. 所有必要步骤完成后，再给用户最终答案。

工具规则：

- 数学计算使用 calculator。
- 最新信息、新闻、实时信息使用 web_search。
- web_search 返回结构化数据。使用搜索结果时，应读取 results 中的 title、url、published_date、content 等字段，不要把工具返回值当作普通字符串。
- 不要假装自己搜索过。
- 如果搜索结果不足，可以换关键词再次搜索。
- 不要为了调用工具而调用工具。
- 最终答案应该直接回答用户的目标，而不是描述你的内部思考过程。

任务执行规则：

- 简单问题：直接回答。
- 单工具问题：调用一次工具并回答。
- 多步骤问题：可以连续调用多个工具。
- 如果前一个工具的结果影响下一步，可以根据结果继续执行。
- 最多连续执行 8 个工具调用，避免无限循环。

上下文规则：

- 记住之前的对话。
- “刚才”“上一条”“哪一个”“它”“这个”等词，
  要结合历史对话理解。
"""


def ask_agent(message: str, history=None) -> str:

    if history is None:
        history = []

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    messages.extend(history)

    messages.append(
        {
            "role": "user",
            "content": message,
        }
    )

    tool_round = 0

    while True:

        tool_round += 1

        if tool_round > 8:
            return (
                "这个任务执行步骤过多，我先停止了。"
                "你可以把任务拆成几个步骤再试。"
            )

        print(
            f"\n[Agent] 第 {tool_round} 步..."
        )

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        assistant_message = response.choices[0].message

        # Agent 决定不需要工具
        if not assistant_message.tool_calls:

            return assistant_message.content or ""

        # 保存 assistant 的 tool calls
        tool_calls_for_history = []

        for tool_call in assistant_message.tool_calls:

            tool_calls_for_history.append(
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
            )

        messages.append(
            {
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": tool_calls_for_history,
            }
        )

        # 执行工具
        for tool_call in assistant_message.tool_calls:

            function_name = tool_call.function.name

            try:
                arguments = json.loads(
                    tool_call.function.arguments
                )
            except json.JSONDecodeError:
                arguments = {}

            print(
                f"[Tool] {function_name}"
            )

            # 检查权限
            if permission_manager.requires_confirmation(
                function_name
            ):

                result = (
                    "这个工具需要用户确认，"
                    "当前暂时不能自动执行。"
                )

                print(
                    f"[Permission] "
                    f"{function_name} requires confirmation"
                )

            else:

                function = TOOL_FUNCTIONS.get(
                    function_name
                )

                if not function:

                    result = (
                        f"未知工具：{function_name}"
                    )

                else:

                    try:

                        result = function(
                            **arguments
                        )

                    except Exception as e:

                        result = (
                            f"工具执行失败：{e}"
                        )

            print(
                f"[Result] {str(result)[:1000]}"
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                }
            )
