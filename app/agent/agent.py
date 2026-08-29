import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from app.agent.permissions import PermissionManager

from app.tools.web import web_search
from app.tools.calculator import calculator
from app.tools.files import (
    file_list,
    file_read,
    file_write,
    file_delete,
)


# ============================================================
# 环境变量
# ============================================================

load_dotenv()

api_key = os.getenv("LLM_API_KEY")

if not api_key:
    raise RuntimeError(
        "没有找到 LLM_API_KEY，请检查 .env 文件"
    )


# ============================================================
# OpenAI Client
# ============================================================

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
)


# ============================================================
# Agent Tools
# ============================================================

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
                        "description": (
                            "数学表达式，例如 123 * 456"
                        ),
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_list",
            "description": (
                "列出项目目录中的文件和子目录。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "项目目录内的相对路径。"
                            "例如 . 或 app/tools"
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": (
                "读取项目目录内的文本文件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "项目目录内的文件相对路径。"
                        ),
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": (
                "创建或修改项目目录内的文本文件。"
                "当用户明确要求创建、写入、修改、保存文件时，"
                "必须调用此工具。"
                "不要用普通文字代替工具调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "项目目录内的文件相对路径。"
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "要写入文件的完整文本内容。"
                        ),
                    },
                },
                "required": [
                    "path",
                    "content",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_delete",
            "description": (
                "删除项目目录内的文件。"
                "这是敏感的文件删除操作，"
                "必须经过用户明确确认。"
                "当用户明确要求删除文件时，必须调用此工具，"
                "不要只用普通文字回答。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "项目目录内的文件相对路径。"
                            "例如 test.txt"
                        ),
                    }
                },
                "required": [
                    "path",
                ],
            },
        },
    },
]


# ============================================================
# Tool Function Mapping
# ============================================================

TOOL_FUNCTIONS = {
    "web_search": web_search,
    "calculator": calculator,
    "file_list": file_list,
    "file_read": file_read,
    "file_write": file_write,
    "file_delete": file_delete,
}


# ============================================================
# Permission Manager
# ============================================================

permission_manager = PermissionManager()


# ============================================================
# System Prompt
# ============================================================

SYSTEM_PROMPT = """
你是一个 AI Agent。

你的任务不仅是回答用户问题，还要帮助用户实际完成任务。

## 工作方式

1. 理解用户真正想完成的目标。
2. 判断是否需要使用工具。
3. 如果需要工具，调用合适的工具。
4. 工具返回结果后，根据真实结果继续完成任务。
5. 如果任务还没有完成，可以继续调用工具。
6. 所有必要步骤完成后，再向用户返回最终答案。

## 工具规则

- 数学计算使用 calculator。
- 最新信息、新闻或实时信息使用 web_search。
- 列出项目目录中的文件使用 file_list。
- 读取项目文件使用 file_read。
- 创建或修改项目文件使用 file_write。
- 删除项目文件使用 file_delete。

## 文件写入规则

当用户明确要求：

- 创建文件
- 新建文件
- 建立文件
- 写入文件
- 修改文件
- 保存文件
- 覆盖文件
- 编辑文件

必须调用 file_write。

不要只用普通文字回答。

不要自己询问用户是否确认。

file_write 是否需要确认，由程序的 PermissionManager 负责。

程序会在真正执行 file_write 之前拦截操作并保存 pending action。

## 文件删除规则

当用户明确要求：

- 删除文件
- 删除某个文件
- 移除文件
- 把文件删掉
- 删除 test.txt
- delete file
- remove file

必须调用 file_delete。

不要直接用普通文字声称文件已经删除。

不要自己询问用户是否确认。

file_delete 是否需要确认，由程序的 PermissionManager 负责。

程序会在真正执行 file_delete 之前拦截操作并保存 pending action。

## 权限确认

file_write 和 file_delete 都属于敏感操作。

第一次请求：

1. 调用对应工具，或者由程序识别明确操作意图。
2. PermissionManager 检查权限。
3. 如果需要确认，保存 pending action。
4. 停止执行。
5. 向用户请求确认。

用户回复“确认”后：

1. 程序直接读取 pending action。
2. 不要把“确认”再次交给 LLM。
3. 直接执行之前保存的工具调用。
4. 只有工具真实返回成功结果后，才能告诉用户操作成功。

用户回复“取消”后：

1. 清除 pending action。
2. 不执行工具。
3. 告诉用户操作已取消。

## 工具结果真实性

绝对不能假装工具已经执行。

只有工具真实返回成功结果之后，才能告诉用户操作成功。

例如：

用户要求删除 test.txt。

不能直接回答：

“test.txt 已删除。”

必须实际执行：

file_delete

并且只有收到 file_delete 的真实成功结果后才能报告删除成功。

## 文件路径

文件工具使用项目根目录作为基础目录。

例如用户说：

“项目根目录创建 test.txt”

file_write 的 path 应该是：

test.txt

例如用户说：

“项目根目录删除 test.txt”

file_delete 的 path 应该是：

test.txt

不要自行添加绝对路径。

## 安全规则

文件工具只能操作项目目录内部的文件。

不要尝试访问项目目录之外的文件。

## 对话上下文

结合历史对话理解：

- 刚才
- 上一个
- 它
- 这个文件
- 这个操作

不要忽略已有上下文。

不要暴露内部思考过程。

最终直接回答用户目标。
"""


# ============================================================
# Confirmation / Cancellation
# ============================================================

def is_confirmation(message: str) -> bool:
    """
    判断用户是否明确确认执行。
    """

    text = message.strip().lower()

    confirmation_words = {
        "确认",
        "确定",
        "可以",
        "执行",
        "批准",
        "同意",
        "好的",
        "好",
        "yes",
        "y",
        "ok",
        "okay",
    }

    return text in confirmation_words


def is_cancellation(message: str) -> bool:
    """
    判断用户是否取消操作。
    """

    text = message.strip().lower()

    cancellation_words = {
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

    return text in cancellation_words


# ============================================================
# 文件写入意图检测
# ============================================================

def looks_like_file_write_request(message: str) -> bool:
    """
    判断用户是否明显在要求创建/修改/写入文件。
    """

    text = message.strip().lower()

    write_keywords = [
        "创建文件",
        "新建文件",
        "建立文件",
        "写入文件",
        "修改文件",
        "编辑文件",
        "保存文件",
        "覆盖文件",
        "写文件",
        "创建一个文件",
        "新建一个文件",
        "帮我创建",
        "帮我新建",
        "帮我写入",
        "帮我修改",
        "帮我编辑",
        "create file",
        "new file",
        "write file",
        "modify file",
        "edit file",
        "save file",
    ]

    return any(
        keyword in text
        for keyword in write_keywords
    )


# ============================================================
# 文件删除意图检测
# ============================================================

def looks_like_file_delete_request(message: str) -> bool:
    """
    判断用户是否明显在要求删除文件。

    例如：

        删除文件test.txt
        删除 test.txt
        项目根目录下删除 test.txt
        把 test.txt 删除
        移除 test.txt
        delete file test.txt
        remove test.txt
    """

    text = message.strip().lower()

    delete_keywords = [
        "删除文件",
        "删除一个文件",
        "删掉文件",
        "删掉一个文件",
        "删除",
        "删掉",
        "移除文件",
        "移除一个文件",
        "移除",
        "把文件删除",
        "把文件删掉",
        "delete file",
        "remove file",
        "delete",
        "remove",
    ]

    return any(
        keyword in text
        for keyword in delete_keywords
    )


# ============================================================
# 提取文件名
# ============================================================

def extract_file_path_for_delete(message: str):
    """
    从常见删除请求中提取文件路径。

    支持：

        删除文件test.txt
        删除文件 test.txt
        删除 test.txt
        项目根目录下删除文件test.txt
        把 test.txt 删除

    如果无法可靠提取，返回 None。
    """

    text = message.strip()

    # --------------------------------------------------------
    # 去掉常见位置描述
    # --------------------------------------------------------

    prefixes = [
        "在项目根目录下",
        "在项目根目录",
        "项目根目录下",
        "项目根目录中",
        "项目根目录里",
        "根目录下",
        "根目录中",
        "根目录里",
    ]

    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip(
                " ：:，,。"
            )
            break

    # --------------------------------------------------------
    # 常见删除表达式
    # --------------------------------------------------------

    patterns = [
        "删除文件",
        "删掉文件",
        "移除文件",
        "删除一个文件",
        "删掉一个文件",
        "移除一个文件",
        "删除",
        "删掉",
        "移除",
        "delete file",
        "remove file",
        "delete",
        "remove",
    ]

    path = None

    for pattern in patterns:

        if pattern not in text:
            continue

        before, after = text.split(
            pattern,
            1
        )

        after = after.strip(
            " ：:，,。"
        )

        # ----------------------------------------------------
        # 处理：
        # “把 test.txt 删除”
        # ----------------------------------------------------

        if not after and before.strip():

            candidate = before.strip()

        else:

            candidate = after

        # ----------------------------------------------------
        # 去掉常见描述
        # ----------------------------------------------------

        candidate = candidate.strip(
            " `\"'“”‘’"
        )

        candidate = candidate.replace(
            "文件：",
            ""
        ).strip()

        # ----------------------------------------------------
        # 如果后面还有“文件”
        # 例如：
        # 删除 test.txt 文件
        # ----------------------------------------------------

        if candidate.endswith("文件"):
            candidate = candidate[:-2].strip()

        # ----------------------------------------------------
        # 去掉句尾标点
        # ----------------------------------------------------

        candidate = candidate.rstrip(
            " 。！？!?,，；;"
        ).strip()

        if candidate:
            path = candidate
            break

    if not path:
        return None

    # --------------------------------------------------------
    # 防止错误把自然语言整句当成路径
    # --------------------------------------------------------

    invalid_fragments = [
        "吗",
        "可以吗",
        "能否",
        "帮我",
        "请",
        "然后",
    ]

    for fragment in invalid_fragments:
        if fragment in path:
            return None

    return {
        "path": path,
    }


# ============================================================
# 从用户消息中提取简单 file_write 参数
# ============================================================

def extract_file_write_arguments(message: str):
    """
    对常见中文文件创建请求进行简单解析。
    """

    text = message.strip()

    path = None

    markers = [
        "创建文件",
        "新建文件",
        "建立文件",
        "创建一个文件",
        "新建一个文件",
    ]

    for marker in markers:

        if marker not in text:
            continue

        after = text.split(
            marker,
            1
        )[1].strip()

        after = after.lstrip(
            " ：:，,"
        )

        if after.startswith("在项目根目录"):
            after = after[
                len("在项目根目录"):
            ].strip(
                " ：:，,"
            )

        content_markers = [
            "，内容是",
            ",内容是",
            "，内容为",
            ",内容为",
            " 内容是",
            " 内容为",
            "，内容：",
            ",内容:",
            "，内容",
            ",内容",
        ]

        filename_part = after
        content_part = None

        for cm in content_markers:

            if cm in after:

                filename_part, content_part = (
                    after.split(
                        cm,
                        1
                    )
                )

                break

        filename_part = filename_part.strip(
            " `\"'“”‘’"
        )

        if filename_part.endswith("文件"):
            filename_part = (
                filename_part[:-2]
                .strip()
            )

        if filename_part:
            path = filename_part

        if content_part is not None:

            content = content_part.strip()

            content = content.strip(
                " ：:,"
            )

            return {
                "path": path,
                "content": content,
            }

        break

    return None


# ============================================================
# Execute Pending Action
# ============================================================

def execute_pending_action(
    user_id: str,
) -> str:
    """
    执行指定用户之前等待确认的操作。
    """

    print(
        f"[Permission] checking pending action "
        f"user_id={user_id}"
    )

    pending_action = (
        permission_manager.get_pending_action(
            user_id
        )
    )

    print(
        f"[Permission] pending_action="
        f"{pending_action}"
    )

    if not pending_action:
        return "当前没有等待确认的操作。"

    tool_name = pending_action["tool_name"]
    arguments = pending_action["arguments"]

    print(
        f"[Permission] 用户已确认：{tool_name}"
    )

    function = TOOL_FUNCTIONS.get(
        tool_name
    )

    if not function:

        permission_manager.clear_pending_action(
            user_id
        )

        return (
            f"确认失败：未知工具 {tool_name}"
        )

    print(
        f"[Tool] {tool_name}"
    )

    print(
        f"[Tool Arguments] {arguments}"
    )

    # --------------------------------------------------------
    # 真正执行工具
    # --------------------------------------------------------

    try:

        result = function(
            **arguments
        )

    except Exception as e:

        permission_manager.clear_pending_action(
            user_id
        )

        print(
            f"[Result] 工具执行失败：{e}"
        )

        return (
            f"操作执行失败：{e}"
        )

    # --------------------------------------------------------
    # 打印真实工具结果
    # --------------------------------------------------------

    print(
        f"[Result] {result}"
    )

    # --------------------------------------------------------
    # 执行完成后清除 pending
    # --------------------------------------------------------

    permission_manager.clear_pending_action(
        user_id
    )

    # --------------------------------------------------------
    # 根据真实结果返回
    # --------------------------------------------------------

    if isinstance(result, dict):

        if result.get("success") is True:

            if tool_name == "file_write":

                return (
                    "文件操作成功。\n"
                    f"路径：{result.get('path', '')}\n"
                    f"信息：{result.get('message', '完成')}"
                )

            if tool_name == "file_delete":

                return (
                    "文件删除成功。\n"
                    f"路径：{result.get('path', '')}\n"
                    f"信息：{result.get('message', '文件已删除')}"
                )

        return json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )

    return str(result)


# ============================================================
# 创建 Pending Action
# ============================================================

def create_pending_action(
    user_id: str,
    tool_name: str,
    arguments: dict,
) -> str:
    """
    创建需要确认的 pending action。
    """

    print(
        f"[Permission] "
        f"程序直接创建 {tool_name} pending action"
    )

    print(
        f"[Permission] user_id={user_id}"
    )

    print(
        f"[Permission] arguments={arguments}"
    )

    permission_manager.set_pending_action(
        user_id,
        tool_name,
        arguments,
    )

    saved_action = (
        permission_manager.get_pending_action(
            user_id
        )
    )

    print(
        f"[Permission] "
        f"saved pending_action={saved_action}"
    )

    if not saved_action:

        print(
            "[Permission] "
            "ERROR: pending action 保存失败"
        )

        return (
            "无法保存待确认操作，"
            "因此没有执行文件操作。"
        )

    arguments_text = json.dumps(
        arguments,
        ensure_ascii=False,
        indent=2,
    )

    return (
        "这个操作需要你的确认才能执行。\n\n"
        f"操作：{tool_name}\n"
        f"参数：\n{arguments_text}\n\n"
        "请回复“确认”执行，"
        "或回复“取消”放弃。"
    )


# ============================================================
# Ask Agent
# ============================================================

def ask_agent(
    message: str,
    history=None,
    user_id: str = "default",
) -> str:
    """
    Agent 主入口。
    """

    if history is None:
        history = []

    print(
        f"[Agent] user_id={user_id}"
    )

    # ========================================================
    # 第一优先级：检查 pending action
    # ========================================================

    pending_action = (
        permission_manager.get_pending_action(
            user_id
        )
    )

    print(
        f"[Permission] pending_action="
        f"{pending_action}"
    )

    if pending_action:

        # ----------------------------------------------------
        # 用户确认
        # ----------------------------------------------------

        if is_confirmation(message):

            return execute_pending_action(
                user_id
            )

        # ----------------------------------------------------
        # 用户取消
        # ----------------------------------------------------

        if is_cancellation(message):

            tool_name = (
                pending_action["tool_name"]
            )

            permission_manager.clear_pending_action(
                user_id
            )

            print(
                f"[Permission] 用户取消："
                f"{tool_name}"
            )

            return (
                f"已取消操作：{tool_name}"
            )

        # ----------------------------------------------------
        # 用户没有明确确认
        # ----------------------------------------------------

        arguments_text = json.dumps(
            pending_action["arguments"],
            ensure_ascii=False,
            indent=2,
        )

        return (
            "当前有一个操作正在等待你的确认。\n\n"
            f"待执行操作：{pending_action['tool_name']}\n"
            f"参数：\n{arguments_text}\n\n"
            "请回复“确认”执行，"
            "或回复“取消”放弃。"
        )

    # ========================================================
    # 程序级文件写入检测
    # ========================================================

    if looks_like_file_write_request(message):

        print(
            "[Agent] 检测到文件写入意图"
        )

        forced_file_arguments = (
            extract_file_write_arguments(
                message
            )
        )

        print(
            "[Agent] 提取的 file_write 参数："
            f"{forced_file_arguments}"
        )

        if forced_file_arguments:

            return create_pending_action(
                user_id,
                "file_write",
                forced_file_arguments,
            )

    # ========================================================
    # 程序级文件删除检测
    # ========================================================

    if looks_like_file_delete_request(message):

        print(
            "[Agent] 检测到文件删除意图"
        )

        delete_arguments = (
            extract_file_path_for_delete(
                message
            )
        )

        print(
            "[Agent] 提取的 file_delete 参数："
            f"{delete_arguments}"
        )

        if delete_arguments:

            return create_pending_action(
                user_id,
                "file_delete",
                delete_arguments,
            )

    # ========================================================
    # 创建 LLM messages
    # ========================================================

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    # --------------------------------------------------------
    # 加入历史
    # --------------------------------------------------------

    if history:
        messages.extend(history)

    # --------------------------------------------------------
    # 当前用户消息
    # --------------------------------------------------------

    messages.append(
        {
            "role": "user",
            "content": message,
        }
    )

    # ========================================================
    # Tool Loop
    # ========================================================

    tool_round = 0

    while True:

        tool_round += 1

        if tool_round > 8:

            return (
                "这个任务执行步骤过多，我先停止了。"
                "你可以把任务拆成几个步骤再试。"
            )

        print(
            f"[Agent] 第 {tool_round} 步..."
        )

        # ----------------------------------------------------
        # 调用 LLM
        # ----------------------------------------------------

        try:

            print(
                "[LLM DEBUG] SYSTEM PROMPT:"
            )

            print(
                messages[0]["content"]
            )

            print(
                "[LLM DEBUG] USER MESSAGE:"
            )

            print(
                messages[-1]
            )

            response = (
                client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
            )

        except Exception as e:

            print(
                f"[Agent] LLM 调用失败：{e}"
            )

            return (
                f"Agent 调用失败：{e}"
            )

        assistant_message = (
            response.choices[0].message
        )

        print(
            "[LLM DEBUG] "
            f"content={assistant_message.content!r}"
        )

        print(
            "[LLM DEBUG] "
            f"tool_calls={assistant_message.tool_calls!r}"
        )

        # ====================================================
        # LLM 不需要工具
        # ====================================================

        if not assistant_message.tool_calls:

            return (
                assistant_message.content
                or ""
            )

        # ====================================================
        # 保存 assistant tool calls
        # ====================================================

        tool_calls_for_history = []

        for tool_call in (
            assistant_message.tool_calls
        ):

            tool_calls_for_history.append(
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": (
                            tool_call.function.name
                        ),
                        "arguments": (
                            tool_call.function.arguments
                        ),
                    },
                }
            )

        messages.append(
            {
                "role": "assistant",
                "content": (
                    assistant_message.content
                    or ""
                ),
                "tool_calls": (
                    tool_calls_for_history
                ),
            }
        )

        # ====================================================
        # 执行工具
        # ====================================================

        for tool_call in (
            assistant_message.tool_calls
        ):

            function_name = (
                tool_call.function.name
            )

            print(
                f"[Tool] {function_name}"
            )

            # ------------------------------------------------
            # 解析参数
            # ------------------------------------------------

            try:

                arguments = json.loads(
                    tool_call.function.arguments
                )

            except json.JSONDecodeError:

                result = (
                    "工具参数格式错误，无法执行。"
                )

                print(
                    f"[Result] {result}"
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": (
                            tool_call.id
                        ),
                        "content": result,
                    }
                )

                continue

            print(
                f"[Tool Arguments] "
                f"{arguments}"
            )

            # ------------------------------------------------
            # 查找工具
            # ------------------------------------------------

            function = TOOL_FUNCTIONS.get(
                function_name
            )

            if not function:

                result = (
                    f"未知工具：{function_name}"
                )

                print(
                    f"[Result] {result}"
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": (
                            tool_call.id
                        ),
                        "content": result,
                    }
                )

                continue

            # =================================================
            # 权限检查
            # =================================================

            if permission_manager.requires_confirmation(
                function_name
            ):

                print(
                    f"[Permission] "
                    f"{function_name} "
                    f"requires confirmation"
                )

                permission_manager.set_pending_action(
                    user_id,
                    function_name,
                    arguments,
                )

                saved_action = (
                    permission_manager.get_pending_action(
                        user_id
                    )
                )

                print(
                    f"[Permission] "
                    f"saved pending_action="
                    f"{saved_action}"
                )

                if not saved_action:

                    print(
                        "[Permission] "
                        "ERROR: pending action 保存失败"
                    )

                    return (
                        "无法保存待确认操作，"
                        "因此没有执行敏感操作。"
                    )

                arguments_text = json.dumps(
                    arguments,
                    ensure_ascii=False,
                    indent=2,
                )

                return (
                    "这个操作需要你的确认才能执行。\n\n"
                    f"操作：{function_name}\n"
                    f"参数：\n{arguments_text}\n\n"
                    "请回复“确认”执行，"
                    "或回复“取消”放弃。"
                )

            # =================================================
            # 自动执行普通工具
            # =================================================

            try:

                result = function(
                    **arguments
                )

            except Exception as e:

                result = (
                    f"工具执行失败：{e}"
                )

            print(
                f"[Result] {result}"
            )

            # ------------------------------------------------
            # 转换为 LLM 内容
            # ------------------------------------------------

            if isinstance(
                result,
                (dict, list),
            ):

                tool_content = json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )

            else:

                tool_content = str(result)

            # ------------------------------------------------
            # 添加 tool result
            # ------------------------------------------------

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": (
                        tool_call.id
                    ),
                    "content": tool_content,
                }
            )

        # ====================================================
        # 下一轮
        # ====================================================
