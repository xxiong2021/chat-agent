from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def set_root(root: str | Path | None) -> None:
    """设置文件工具的工作根目录（由管理配置驱动）。"""
    global PROJECT_ROOT
    if root is None or str(root).strip() == "":
        return
    raw = Path(str(root)).expanduser()
    candidate = raw if raw.is_absolute() else (PROJECT_ROOT / raw)
    candidate = candidate.resolve()
    if not candidate.is_dir():
        raise ValueError(f"目录不存在：{candidate}")
    PROJECT_ROOT = candidate


def _safe_path(path: str, root: Path | None = None) -> Path:
    """
    将用户提供的路径限制在项目目录内。
    """

    if root is not None:
        raw_root = Path(root).expanduser()
        base = raw_root if raw_root.is_absolute() else (PROJECT_ROOT / raw_root)
    else:
        base = PROJECT_ROOT
    base = base.resolve()

    if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        raise PermissionError(
            "禁止使用绝对路径。"
        )

    target = (base / path).resolve()

    try:
        target.relative_to(base)
    except ValueError:
        raise PermissionError(
            "禁止访问项目目录之外的文件。"
        )

    relative_parts = target.relative_to(base).parts
    if any(part.startswith(".") for part in relative_parts):
        raise PermissionError(
            "禁止访问隐藏或敏感文件。"
        )

    return target


def file_list(path: str = ".", _root: Path | None = None) -> dict:
    """
    列出目录内容。
    """

    target = _safe_path(path, _root)

    if not target.exists():
        return {
            "success": False,
            "error": "目录不存在",
            "path": path,
        }

    if not target.is_dir():
        return {
            "success": False,
            "error": "目标不是目录",
            "path": path,
        }

    items = []

    for item in sorted(target.iterdir()):
        if item.name.startswith("."):
            continue
        items.append(
            {
                "name": item.name,
                "type": (
                    "directory"
                    if item.is_dir()
                    else "file"
                ),
            }
        )

    return {
        "success": True,
        "path": path,
        "items": items,
    }


def file_read(path: str, _root: Path | None = None) -> dict:
    """
    读取文本文件。
    """

    target = _safe_path(path, _root)

    if not target.exists():
        return {
            "success": False,
            "error": "文件不存在",
            "path": path,
        }

    if not target.is_file():
        return {
            "success": False,
            "error": "目标不是文件",
            "path": path,
        }

    try:
        content = target.read_text(
            encoding="utf-8"
        )
    except UnicodeDecodeError:
        return {
            "success": False,
            "error": "文件不是 UTF-8 文本文件",
            "path": path,
        }

    return {
        "success": True,
        "path": path,
        "content": content,
    }


def file_write(
    path: str,
    content: str,
    _root: Path | None = None,
) -> dict:
    """
    写入文本文件。
    """

    target = _safe_path(path, _root)

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        target.write_text(
            content,
            encoding="utf-8",
        )
    except Exception as e:
        return {
            "success": False,
            "error": f"文件写入失败：{e}",
            "path": path,
        }

    return {
        "success": True,
        "path": path,
        "message": "文件写入成功",
    }


def file_delete(path: str, _root: Path | None = None) -> dict:
    """
    删除项目目录内的文件。
    """

    target = _safe_path(path, _root)

    if not target.exists():
        return {
            "success": False,
            "error": "文件不存在",
            "path": path,
        }

    if not target.is_file():
        return {
            "success": False,
            "error": "目标不是文件",
            "path": path,
        }

    try:
        target.unlink()
    except Exception as e:
        return {
            "success": False,
            "error": f"文件删除失败：{e}",
            "path": path,
        }

    # 二次验证：确认文件真的不存在
    if target.exists():
        return {
            "success": False,
            "error": "删除操作返回后文件仍然存在",
            "path": path,
        }

    return {
        "success": True,
        "path": path,
        "message": "文件已删除",
    }
