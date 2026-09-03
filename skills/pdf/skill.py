"""PDF skill: 读取并提取本地 PDF 文本。"""

from pathlib import Path

from pypdf import PdfReader

from app.tools.files import _safe_path


def _resolve(path: str) -> Path:
    """复用文件工具的安全路径校验（限制在工作目录内、拒绝隐藏/越界）。"""
    return _safe_path(path)


def pdf_read(path: str, from_page: int = 1, to_page: int | None = None) -> dict:
    """提取 PDF 文本。返回页面数、页码范围与文本（超长截断）。"""
    target = _resolve(path)
    if not target.exists():
        return {"success": False, "error": f"文件不存在：{path}", "path": path}
    if not target.is_file() or target.suffix.lower() != ".pdf":
        return {"success": False, "error": f"目标不是 PDF 文件：{path}", "path": path}

    try:
        reader = PdfReader(str(target))
        total = len(reader.pages)
        start = max(1, int(from_page or 1))
        end = min(total, int(to_page) if to_page else total)
        if start > end:
            return {"success": False, "error": f"页码范围无效：{from_page}-{to_page}（共 {total} 页）", "path": path}
        parts = []
        for i in range(start - 1, end):
            parts.append(reader.pages[i].extract_text() or "")
        text = "\n\n".join(parts).strip()
        max_chars = 20000
        truncated = len(text) > max_chars
        return {
            "success": True,
            "path": path,
            "pages": total,
            "from_page": start,
            "to_page": end,
            "content": text[:max_chars],
            "truncated": truncated,
            "note": "内容较长已截断" if truncated else "",
        }
    except Exception as e:
        return {"success": False, "error": f"PDF 读取失败：{e}", "path": path}


SKILL_META = {
    "tools": {"pdf_read": pdf_read},
}
