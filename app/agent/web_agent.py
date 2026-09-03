import json
import os
import re

from app.agent.permissions import PermissionManager
from app.core.config import ConfigStore
from app.llm.router import LLMRouter
from app.skills.loader import (
    discover_skills,
    load_skill_module,
    set_skill_enabled,
    skill_available,
    skill_enabled,
)
from app.tools.calculator import calculator
from app.tools.files import file_delete, file_list, file_read, file_write, set_root


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

## PDF 文件

PDF 是二进制文件，不能用 file_read 读取。处理 PDF（读取、总结、问答）必须使用 pdf_read 工具，path 传 PDF 的相对路径。

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


class _RuntimeConfig(ConfigStore):
    """让 LLMRouter 直接使用当前请求的管理配置，而不是重读磁盘。"""

    def __init__(self, config: dict):
        self._config = config

    def load(self) -> dict:
        return self._config


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
    enabled_skill_descriptions: list[str] = []

    for name, manifest in discover_skills().items():
        if not skill_enabled(config, name):
            continue
        module = load_skill_module(manifest)
        if module is None:
            continue
        module_meta = getattr(module, "SKILL_META", {})
        module_tools = module_meta.get("tools", {})
        for tool_name, tool_fn in module_tools.items():
            schema = (manifest.get("tools") or {}).get(tool_name)
            if schema is None:
                continue
            functions[tool_name] = tool_fn
            schemas.append({"type": "function", "function": {"name": tool_name, **schema}})
        desc = (manifest.get("description_zh") or manifest.get("description")) or ""
        if desc:
            enabled_skill_descriptions.append(f"- {desc}")

    if resources.get("web_search", {}).get("enabled"):
        try:
            from app.tools.web import web_search
        except Exception:
            web_search = None
        if web_search:
            schemas.append(TOOL_SCHEMAS["web_search"])
            functions.setdefault("web_search", web_search)
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

    return schemas, functions, enabled_skill_descriptions


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


def _truncate_content(content: str) -> str:
    """内容遇到“，然后/接着/再/并/同时”等后续指令时截断。"""
    parts = re.split(r"[，,。；;]\s*(?:然后|接着|再|并|同时)", content, maxsplit=1)
    return parts[0].strip()


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

    # 一次删除多个文件（paths 列表）
    if tool_name == "file_delete" and isinstance(arguments.get("paths"), list):
        lines = []
        for p in arguments["paths"]:
            try:
                r = function(path=p)
            except Exception as e:
                r = {"success": False, "error": str(e)}
            if isinstance(r, dict) and r.get("success") is True:
                lines.append(f"文件删除成功：{p}")
            else:
                err = r.get("error", "未知错误") if isinstance(r, dict) else str(r)
                lines.append(f"文件删除失败：{p}（{err}）")
        permission_manager.clear_pending_action(user_id)
        return "\n".join(lines) or "没有可执行的文件。"

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


# ============================================================
# 确定性意图检测（小模型工具调用不稳定时的兜底）
# ============================================================

def looks_like_file_write_request(message: str) -> bool:
    text = message.strip().lower()
    write_keywords = [
        "创建文件", "新建文件", "建立文件", "写入文件", "修改文件", "编辑文件",
        "保存文件", "覆盖文件", "写文件", "创建一个文件", "新建一个文件",
        "帮我创建", "帮我新建", "帮我写入", "帮我修改", "帮我编辑",
        "create file", "new file", "write file", "modify file", "edit file", "save file",
    ]
    return any(keyword in text for keyword in write_keywords)


def extract_file_write_arguments(message: str):
    text = message.strip()

    # 支持“创建 test.txt，内容是 hello”这类说法（不强制带“文件”二字）
    m = re.search(
        r"(?:创建|新建|写入|生成|建立)\s*(?:文件)?\s*([\w./\\-]+\.\w+)\s*[，,]\s*(?:内容是|内容为|内容：|内容)\s*(.+)",
        text,
    )
    if m:
        return {"path": m.group(1), "content": _truncate_content(m.group(2))}

    path = None
    markers = ["创建文件", "新建文件", "建立文件", "创建一个文件", "新建一个文件"]
    for marker in markers:
        if marker not in text:
            continue
        after = text.split(marker, 1)[1].strip()
        after = after.lstrip(" ：:，,")
        if after.startswith("在项目根目录"):
            after = after[len("在项目根目录"):].strip(" ：:，，")
        content_markers = [
            "，内容是", ",内容是", "，内容为", ",内容为", " 内容是", " 内容为",
            "，内容：", ",内容:", "，内容", ",内容",
        ]
        filename_part = after
        content_part = None
        for cm in content_markers:
            if cm in after:
                filename_part, content_part = after.split(cm, 1)
                break
        filename_part = filename_part.strip(" `\"'“”‘’")
        if filename_part.endswith("文件"):
            filename_part = filename_part[:-2].strip()
        if filename_part:
            path = filename_part
        if content_part is not None:
            content = content_part.strip().strip(" ：:,")
            return {"path": path, "content": _truncate_content(content)}
        break
    return None


def looks_like_file_delete_request(message: str) -> bool:
    text = message.strip().lower()
    delete_keywords = [
        "删除文件", "删除一个文件", "删掉文件", "删掉一个文件", "删除", "删掉",
        "移除文件", "移除一个文件", "移除", "把文件删除", "把文件删掉",
        "delete file", "remove file", "delete", "remove",
    ]
    return any(keyword in text for keyword in delete_keywords)


def extract_file_paths_for_delete(message: str):
    """提取删除请求中的文件路径，支持一次删除多个文件（用“和/与/、/，”分隔）。"""
    text = message.strip()
    prefixes = [
        "在项目根目录下", "在项目根目录", "项目根目录下", "项目根目录中", "项目根目录里",
        "根目录下", "根目录中", "根目录里",
    ]
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip(" ：:，,。")
            break
    patterns = [
        "删除文件", "删掉文件", "移除文件", "删除一个文件", "删掉一个文件", "移除一个文件",
        "删除", "删掉", "移除", "delete file", "remove file", "delete", "remove",
    ]
    candidate = None
    for pattern in patterns:
        if pattern not in text:
            continue
        before, after = text.split(pattern, 1)
        after = after.strip(" ：:，,。")
        if not after and before.strip():
            c = before.strip()
            if c.startswith("把"):
                c = c[1:].strip()
        else:
            c = after
        candidate = c
        break
    if not candidate:
        return None

    raw_parts = re.split(r"[和与、,，及]", candidate)
    paths = []
    invalid_fragments = ["吗", "可以吗", "能否", "帮我", "请", "然后", "接着"]
    for part in raw_parts:
        p = part.strip(" `\"'“”‘’").replace("文件：", "").strip()
        if p.endswith("文件"):
            p = p[:-2].strip()
        p = p.rstrip(" 。！？!?,，；;").strip()
        if not p:
            continue
        if any(frag in p for frag in invalid_fragments):
            continue
        paths.append(p)
    if not paths:
        return None
    return {"paths": paths}


def detect_file_list_request(message: str):
    text = message.strip()
    if not re.search(
        r"(列出|列举|有什么文件|有哪些文件|有哪些上传|列出上传|目录里有什么|目录中有什么|查看目录|显示目录"
        r"|寻找|查找|找找|搜索.*文件|有没有|看看 uploads|查看 uploads|uploads 目录|上传的文件)",
        text,
        re.IGNORECASE,
    ):
        return None
    return {"path": "."}


def find_pdfs(root_text: str) -> list[tuple[str, str]]:
    """在文件根目录内递归查找 PDF，返回 [(相对目录, 文件名)]。"""
    from pathlib import Path

    import app.tools.files as files_tools

    bases = [files_tools.PROJECT_ROOT]
    for extra in (root_text or "").split("|"):
        if extra and Path(extra).is_dir():
            bases.append(Path(extra))
    skip = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    for base in bases:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
            for name in filenames:
                if name.lower().endswith(".pdf"):
                    full = Path(dirpath) / name
                    try:
                        rel_dir = str(full.parent.relative_to(base))
                    except ValueError:
                        rel_dir = str(full.parent)
                    key = str(full)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append((rel_dir, name))
    return results


def detect_file_read_request(message: str):
    text = message.strip()
    m = re.search(r"(?:读取|读一下|打开|看看|查看)\s*(?:文件)?\s*([\w./\\-]+\.\w+)", text)
    if not m:
        return None
    return {"path": m.group(1)}


def detect_web_search_request(message: str):
    text = message.strip()
    m = re.search(r"(?:搜索|搜一下|查一下|查找|搜)\s*(?:关于)?\s*(.+?)[。！？!?.]*$", text)
    if not m:
        return None
    query = m.group(1).strip()
    if len(query) < 2:
        return None
    return {"query": query}


def format_tool_result(name: str, arguments: dict, result) -> str:
    if isinstance(result, dict) and result.get("success") is False:
        return f"操作失败：{result.get('error', '未知错误')}"
    if name == "file_list":
        items = result.get("items", []) if isinstance(result, dict) else []
        if not items:
            return "目录为空。"
        lines = [f"- {it['name']}/" if it.get("type") == "directory" else f"- {it['name']}" for it in items]
        return "项目目录内容：\n" + "\n".join(lines)
    if name == "file_read":
        content = result.get("content", "") if isinstance(result, dict) else str(result)
        return f"文件 {arguments.get('path', '')} 内容：\n{content}"
    if name == "web_search":
        results = result.get("results", []) if isinstance(result, dict) else []
        if not results:
            return f"没有找到与“{arguments.get('query', '')}”相关的结果。"
        lines = []
        for r in results[:5]:
            lines.append(f"- {r.get('title', '')}\n  {r.get('url', '')}\n  {r.get('content', '')[:200]}")
        return "搜索结果：\n" + "\n".join(lines)
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, indent=2)
    return str(result)


def run_auto_tool(user_id: str, name: str, arguments: dict, functions: dict) -> str:
    function = functions.get(name)
    if not function:
        return f"工具 {name} 当前不可用。"
    try:
        result = function(**arguments)
    except Exception as e:
        return f"工具执行失败：{e}"
    return format_tool_result(name, arguments, result)


def handle_skill_request(user_id: str, text: str, config: dict, is_admin: bool = False, config_store: ConfigStore | None = None) -> str | None:
    """识别“启用/安装 xx skill”类请求；命中则返回结果消息，否则返回 None。"""
    m = re.search(
        r"(?:安装|启用|开启|添加|增加|打开|enable|install|add|turn on)\s*(?:pdf\s*)?(?:skill|技能|插件|能力)"
        r"|(?:pdf\s*)?(?:skill|技能)\s*(?:安装|启用|开启|添加|打开|enable|install)",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    available = discover_skills()
    if not available:
        return "当前没有可用的技能包。"
    requested = None
    lowered = text.lower()
    for name in available:
        if name.lower() in lowered or ("pdf" in lowered and name == "pdf"):
            requested = name
            break
    if requested is None:
        names = "、".join(available)
        return f"没有识别到要启用的技能。当前可用技能：{names}。"
    if not is_admin:
        return "没有权限：启用技能需要管理员权限。"
    if skill_enabled(config, requested):
        return f"技能 {requested} 已经启用，可以直接使用（例如：读取 PDF 并总结）。"
    if not set_skill_enabled(config, requested, True):
        return f"技能 {requested} 不可用。"
    if config_store is not None:
        config_store.save(config)
    return f"技能 {requested} 已启用。现在可以让我读取并分析 PDF 文件了。"


def detect_pdf_request(text: str) -> dict | None:
    """识别“读取/总结/分析 xxx.pdf”类请求。"""
    if "pdf" not in text.lower():
        return None
    m = re.search(r"(?<![\w.\\/-])([A-Za-z0-9_./\\-]+\.pdf)", text, re.IGNORECASE)
    if m:
        return {"path": m.group(1)}
    m = re.search(r"uploads/[A-Za-z0-9_.\\/-]+\.pdf", text, re.IGNORECASE)
    if m:
        return {"path": m.group(0)}
    return None


def handle_pdf_request(text: str, config: dict) -> tuple | str | None:
    """PDF 请求路由到 pdf_read；纯读取返回文本，翻译/总结等返回 (路径, 页码, 文本)。"""
    request = detect_pdf_request(text)
    if request is None:
        return None
    if not skill_enabled(config, "pdf"):
        return "读取 PDF 需要先启用 pdf 技能。管理员可在“管理配置-技能”中勾选 PDF，或直接在聊天中说“启用 pdf 技能”。"
    found = discover_skills()
    module = load_skill_module(found.get("pdf") or {})
    if module is None:
        return "pdf 技能加载失败，请检查服务器部署。"
    pdf_tool = (getattr(module, "SKILL_META", {}) or {}).get("tools", {}).get("pdf_read")
    if pdf_tool is None:
        return "pdf 技能缺少 pdf_read 工具。"
    result = pdf_tool(request["path"])
    if not result.get("success", False):
        return f"PDF 读取失败：{result.get('error', '未知错误')}"
    content = result.get("content", "")
    text_lower = text.lower()
    wants_processing = bool(
        re.search(
            r"(翻译|总结|摘要|归纳|分析|提取|问答|转成|convert|translate|summar|abstract|analy)",
            text,
            re.IGNORECASE,
        )
    )
    if not wants_processing:
        head = f"文件 {request['path']}（共 {result['pages']} 页，已读取 {result['from_page']}-{result['to_page']} 页）：\n"
        return head + content
    return (request["path"], result.get("pages", 0), content)


def run_agent(user_id: str, messages: list[dict], config: dict, is_admin: bool = False, config_store: ConfigStore | None = None) -> str:
    """Web Agent 主入口：意图检测 + 多轮工具调用 + 权限确认。"""
    files_config = config.get("resources", {}).get("files", {})
    configured_root = files_config.get("root")
    if configured_root:
        try:
            set_root(configured_root)
        except (ValueError, OSError):
            pass
    tools, functions, skill_descriptions = build_tools(config)
    resources = config.get("resources", {})
    files_enabled = files_config.get("enabled", True)
    web_enabled = resources.get("web_search", {}).get("enabled", False)

    last_text = messages[-1]["content"] if messages else ""
    skill_result = handle_skill_request(user_id, last_text, config, is_admin=is_admin, config_store=config_store)
    if skill_result is not None:
        return skill_result

    pending = permission_manager.get_pending_action(user_id)
    if pending:
        if is_confirmation(last_text, pending["confirmation_token"]):
            return execute_pending_action(user_id, functions)
        if is_cancellation(last_text):
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

    # ---------------- 确定性意图检测兜底 ----------------
    pdf_result = handle_pdf_request(last_text, config)
    pdf_context = None
    if isinstance(pdf_result, tuple):
        pdf_context = pdf_result
    elif pdf_result is not None:
        return pdf_result
    if pdf_context is None:
        if re.search(
            r"(寻找|查找|找找|有没有|列出|列举|显示|有哪些|搜.*pdf|find.*pdf|search.*pdf|list.*pdf)",
            last_text,
            re.IGNORECASE,
        ) and "pdf" in last_text.lower():
            pdfs = find_pdfs("")
            if not pdfs:
                return "在本地工作目录中没有找到 PDF 文件。"
            lines = []
            for rel_dir, name in pdfs:
                path = (f"{rel_dir}/{name}" if rel_dir != "." else name).replace("\\", "/")
                lines.append(f"- {path}")
            return f"找到 {len(pdfs)} 个 PDF 文件：\n" + "\n".join(lines)
        if re.search(r"(上传的文件|uploads|列出上传|有哪些上传|看看 uploads|查看 uploads)", last_text, re.IGNORECASE):
            from app.tools.files import file_list as _file_list
            listing = _file_list("uploads") or {}
            if listing.get("success"):
                items = listing.get("items", [])
                if not items:
                    return "uploads 目录为空（还没有上传过文件）。"
                lines = [f"- {it['name']}" + ("/" if it.get('type') == 'directory' else "") for it in items]
                return "已上传的文件：\n" + "\n".join(lines)
    if pdf_context is not None:
        pass
    elif files_enabled:
        write_args = extract_file_write_arguments(last_text)
        if write_args:
            return create_pending_action(user_id, "file_write", write_args)
        delete_args = extract_file_paths_for_delete(last_text)
        if delete_args:
            return create_pending_action(user_id, "file_delete", delete_args)
        list_args = detect_file_list_request(last_text)
        if list_args:
            return run_auto_tool(user_id, "file_list", list_args, functions)
        read_args = detect_file_read_request(last_text)
        if read_args:
            return run_auto_tool(user_id, "file_read", read_args, functions)
    elif not files_enabled:
        # 文件功能未启用：识别文件请求并明确拒绝，避免模型编造结果。
        if (
            extract_file_write_arguments(last_text)
            or extract_file_paths_for_delete(last_text)
            or detect_file_list_request(last_text)
            or detect_file_read_request(last_text)
        ):
            return "没有权限：本地文件功能未启用。请联系管理员在“管理配置”中开启“本地文件”。"

    if pdf_context is None:
        if web_enabled:
            search_args = detect_web_search_request(last_text)
            if search_args:
                return run_auto_tool(user_id, "web_search", search_args, functions)
        else:
            if detect_web_search_request(last_text):
                return "没有权限：网站搜索功能未启用。请联系管理员在“管理配置”中开启“网站搜索”。"

    # ---------------- LLM 多轮工具调用 ----------------
    system_prompt = SYSTEM_PROMPT
    if skill_descriptions:
        system_prompt += "\n\n## 技能工具\n" + "\n".join(skill_descriptions)
    if not files_enabled:
        system_prompt += (
            "\n注意：本地文件功能当前未启用。如果用户要求创建、读取、修改、删除文件，"
            "直接告知“本地文件功能未启用，没有权限”，绝对不要声称已执行文件操作。"
        )
    if not web_enabled:
        system_prompt += (
            "\n注意：网站搜索功能当前未启用。如果用户要求搜索，"
            "直接告知“网站搜索功能未启用，没有权限”，不要声称已执行搜索。"
        )
    llm_messages = [{"role": "system", "content": system_prompt}]
    if pdf_context is not None:
        path, pages, content = pdf_context
        instruction = re.sub(r"读取\s*[^，。；,\s]*\.pdf\s*", "", last_text).strip() or "请阅读并处理这份文档"
        llm_messages.append(
            {
                "role": "user",
                "content": (
                    "以下是一份 PDF 文档提取出的文本内容"
                    f"（文件 {path}，共 {pages} 页）。\n"
                    "请直接完成这个任务，不要询问、不要复述原文、不要只返回确认消息：\n"
                    f"{instruction}\n\n"
                    f"===== PDF 文档内容开始 =====\n{content}\n===== PDF 文档内容结束 ====="
                ),
            }
        )
    else:
        llm_messages.extend(messages)

    for _round in range(1, 9):
        response = LLMRouter(config_store=_RuntimeConfig(config)).complete(llm_messages, tools=tools)
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
            raw_args = tc.function.arguments
            if isinstance(raw_args, dict):
                arguments = raw_args
            else:
                try:
                    arguments = json.loads(raw_args or "{}")
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
