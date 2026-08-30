import json

from app.agent.permissions import PermissionManager
from app.llm.router import LLMRouter
from app.tools.calculator import calculator
from app.tools.files import file_delete, file_list, file_read, file_write


SYSTEM_PROMPT = """
你是一个 AI Agent，帮助用户实际完成任务。

## 工作方式

1. 理解用户真正想完成的目标。
2. 判断是否需要使用工具；需要时直接调用工具，不要用普通文字代替。
3. 工具返回结果后，根据真实结果继续完成任务。
4. 全部必要步骤完成后，再向用户返回最终答案。

## 工具

- calculator：计算数学表达式。
- web_search：搜索互联网，获取最新或实时信息。
- file_list：列出应用目录中的文件和子目录。
- file_read：读取应用目录内的文本文件。
- file_write：创建或修改应用目录内的文本文件。
- file_delete：删除应用目录内的文件。

## 文件操作规则

当用户明确要求创建、新建、写入、修改、保存、覆盖、编辑文件时，必须调用 file_write。
当用户明确要求删除、移除文件时，必须调用 file_delete。
不要只用普通文字声称操作已完成。

## 权限确认

file_write 和 file_delete 是敏感操作。程序会在真正执行前拦截并保存 pending action（带确认口令）。
你只需要正常调用工具，不要自己询问用户是否确认，也不要声称文件已写入或已删除。
只有程序返回成功结果后，才能告诉用户操作成功。

## 文件路径

文件工具以应用根目录为基础目录。
例如用户说“创建 test.txt”，path 应该是 test.txt；不要添加绝对路径。
只能操作应用目录内部的文件。

## 对话

结合历史对话理解“刚才、上一个、它、这个文件”等指代。
不要暴露内部思考过程，直接回答用户。
"""


TOOL_FUNCTIONS = {
    "calculator": calculator,
    "file_list": file_list,
    "file_read": file_read,
    "file_write": file_write,
    "file_delete": file_delete,
}


TOOL_SCHEMAS = {
    "calculator": {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算数学表达式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式，例如 123 * 456"},
                },
                "required": ["expression"],
            },
        },
    },
    "web_search": {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网，获取最新或实时信息。如果任务需要多个不同角度的信息，可以多次调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或问题"},
                },
                "required": ["query"],
            },
        },
    },
    "file_list": {
        "type": "function",
        "function": {
            "name": "file_list",
            "description": "列出应用目录中的文件和子目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "应用目录内的相对路径，例如 . 或 app/tools"},
                },
                "required": [],
            },
        },
    },
    "file_read": {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "读取应用目录内的文本文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "应用目录内的文件相对路径"},
                },
                "required": ["path"],
            },
        },
    },
    "file_write": {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "创建或修改应用目录内的文本文件。用户明确要求创建、写入、修改、保存文件时必须调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "应用目录内的文件相对路径"},
                    "content": {"type": "string", "description": "要写入文件的完整文本内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    "file_delete": {
        "type": "function",
        "function": {
            "name": "file_delete",
            "description": "删除应用目录内的文件。用户明确要求删除文件时必须调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "应用目录内的文件相对路径，例如 test.txt"},
                },
                "required": ["path"],
            },
        },
    },
}


permission_manager = PermissionManager()


def build_tools(config: dict):
    """根据管理配置生成启用的工具。返回 (schemas, functions)。"""
    resources = config.get("resources", {})
    functions = dict(TOOL_FUNCTIONS)
    schemas = [TOOL_SCHEMAS["calculator"]]

    if resources.get("web_search", {}).get("enabled"):
        try:
            from app.tools.web import web_search
        except Exception:
            web_search = None
        if web_search:
            schemas.append(TOOL_SCHEMAS["web_search"])
            functions["web_search"] = web_search
        else:
            functions.pop("web_search", None)
    else:
        functions.pop("web_search", None)

    if resources.get("files", {}).get("enabled", True):
        schemas.extend(
            [
                TOOL_SCHEMAS["file_list"],
                TOOL_SCHEMAS["file_read"],
                TOOL_SCHEMAS["file_write"],
                TOOL_SCHEMAS["file_delete"],
            ]
        )
    else:
        for name in ("file_list", "file_read", "file_write", "file_delete"):
            functions.pop(name, None)

    return schemas, functions


def is_confirmation(message: str, confirmation_token: str) -> bool:
    text = message.strip().lower()
    return text in {f"确认 {confirmation_token}".lower(), f"confirm {confirmation_token}".lower()}


def is_cancellation(message: str) -> bool:
    return message.strip().lower() in {
        "取消",
        "不要",
        "不用",
        "拒绝",
        "否",
        "不",
        "no",
        "n",
        "cancel",
    }


def create_pending_action(user_id: str, tool_name: str, arguments: dict) -> str:
    permission_manager.set_pending_action(user_id, tool_name, arguments)
    saved = permission_manager.get_pending_action(user_id)
    if not saved:
        return "无法保存待确认操作，因此没有执行文件操作。"
    arguments_text = json.dumps(arguments, ensure_ascii=False, indent=2)
    return (
        "这个操作需要你的确认才能执行。\n\n"
        f"操作：{tool_name}\n"
        f"参数：\n{arguments_text}\n\n"
        "此操作将在 5 分钟后过期。\n"
        f"请回复“确认 {saved['confirmation_token']}”执行，或回复“取消”放弃。"
    )


def execute_pending_action(user_id: str, functions: dict) -> str:
    pending = permission_manager.get_pending_action(user_id)
    if not pending:
        return "当前没有等待确认的操作。"
    tool_name = pending["tool_name"]
    arguments = pending["arguments"]
    function = functions.get(tool_name)
    if not function:
        permission_manager.clear_pending_action(user_id)
        return f"确认失败：未知工具 {tool_name}"
    try:
        result = function(**arguments)
    except Exception as e:
        permission_manager.clear_pending_action(user_id)
        return f"操作执行失败：{e}"
    permission_manager.clear_pending_action(user_id)
    if isinstance(result, dict):
        if result.get("success") is True:
            if tool_name == "file_write":
                return f"文件操作成功。\n路径：{result.get('path', '')}\n信息：{result.get('message', '完成')}"
            if tool_name == "file_delete":
                return f"文件删除成功。\n路径：{result.get('path', '')}\n信息：{result.get('message', '文件已删除')}"
        return json.dumps(result, ensure_ascii=False, indent=2)
    return str(result)


def run_agent(user_id: str, messages: list[dict], config: dict) -> str:
    """Web Agent 主入口：多轮工具调用 + 权限确认。"""
    tools, functions = build_tools(config)

    pending = permission_manager.get_pending_action(user_id)
    if pending:
        last = messages[-1]["content"] if messages else ""
        if is_confirmation(last, pending["confirmation_token"]):
            return execute_pending_action(user_id, functions)
        if is_cancellation(last):
            permission_manager.clear_pending_action(user_id)
            return f"已取消操作：{pending['tool_name']}"
        arguments_text = json.dumps(pending["arguments"], ensure_ascii=False, indent=2)
        return (
            "当前有一个操作正在等待你的确认。\n\n"
            f"待执行操作：{pending['tool_name']}\n"
            f"参数：\n{arguments_text}\n\n"
            "此操作将在 5 分钟后过期。\n"
            f"请回复“确认 {pending['confirmation_token']}”执行，或回复“取消”放弃。"
        )

    llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]

    for _round in range(1, 9):
        response = LLMRouter().complete(llm_messages, tools=tools)
        assistant = response.choices[0].message
        tool_calls = getattr(assistant, "tool_calls", None)

        if not tool_calls:
            return assistant.content or ""

        tool_calls_for_history = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in tool_calls
        ]
        llm_messages.append(
            {
                "role": "assistant",
                "content": assistant.content or "",
                "tool_calls": tool_calls_for_history,
            }
        )

        for tc in tool_calls:
            name = tc.function.name
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                llm_messages.append({"role": "tool", "tool_call_id": tc.id, "content": "工具参数格式错误，无法执行。"})
                continue

            if permission_manager.requires_confirmation(name):
                return create_pending_action(user_id, name, arguments)

            function = functions.get(name)
            if not function:
                llm_messages.append({"role": "tool", "tool_call_id": tc.id, "content": f"未知工具：{name}"})
                continue

            try:
                result = function(**arguments)
            except Exception as e:
                result = f"工具执行失败：{e}"

            if isinstance(result, (dict, list)):
                content = json.dumps(result, ensure_ascii=False, indent=2)
            else:
                content = str(result)
            llm_messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    return "这个任务执行步骤过多，我先停止了。你可以把任务拆成几个步骤再试。"
