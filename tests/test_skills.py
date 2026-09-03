from pathlib import Path
from copy import deepcopy

from pypdf import PdfWriter

from app.agent.web_agent import build_tools, handle_skill_request
from app.core.config import DEFAULT_CONFIG
from app.skills.loader import (
    discover_skills,
    list_skills,
    load_skill_module,
    set_skill_enabled,
    skill_enabled,
)
from app.tools.files import set_root


def test_skill_discovery_finds_pdf():
    found = discover_skills()
    assert "pdf" in found
    assert "pdf_read" in found["pdf"]["tools"]
    names = [s["name"] for s in list_skills()]
    assert "pdf" in names


def test_enabled_skill_tools_registered_in_build_tools():
    config = deepcopy(DEFAULT_CONFIG)
    tools, functions, descriptions = build_tools(config)
    assert "pdf_read" not in [s["function"]["name"] for s in tools]
    assert "pdf_read" not in functions

    config = deepcopy(DEFAULT_CONFIG)
    assert set_skill_enabled(config, "pdf", True)
    assert skill_enabled(config, "pdf")
    tools, functions, descriptions = build_tools(config)
    assert "pdf_read" in [s["function"]["name"] for s in tools]
    assert "pdf_read" in functions
    assert any("PDF" in d for d in descriptions)


def test_conversation_enables_skill_only_for_admin():
    from app.core.config import ConfigStore

    class MemoryStore(ConfigStore):
        def __init__(self, cfg):
            self._cfg = cfg

        def load(self):
            return self._cfg

        def save(self, config):
            self._cfg = config

    cfg = deepcopy(DEFAULT_CONFIG)
    store = MemoryStore(cfg)
    reply = handle_skill_request("web:employee", "启用 pdf skill", cfg, is_admin=False)
    assert "管理员" in reply
    assert not skill_enabled(cfg, "pdf")

    reply = handle_skill_request("web:admin", "安装 pdf skill", cfg, is_admin=True, config_store=store)
    assert "已启用" in reply
    assert skill_enabled(cfg, "pdf")

    reply = handle_skill_request("web:admin", "enable pdf skill", cfg, is_admin=True)
    assert "已经启用" in reply


def test_pdf_skill_reads_pdf_within_configured_root(tmp_path):
    work = tmp_path / "work"
    (work / "docs").mkdir(parents=True)
    pdf_path = work / "docs" / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    set_root(str(work))
    module = load_skill_module(discover_skills()["pdf"])
    assert module is not None
    result = module.SKILL_META["tools"]["pdf_read"]("docs/sample.pdf")
    assert result["success"] is True
    assert result["pages"] == 2

    import pytest

    with pytest.raises(PermissionError):
        module.SKILL_META["tools"]["pdf_read"]("../outside.pdf")


def test_pdf_requests_route_to_pdf_tool_not_file_read(tmp_path):
    """上传的 PDF 请求必须走 pdf_read，而不是被 file_read 当作 UTF-8 文本。"""
    from app.agent.web_agent import run_agent
    from app.core.config import DEFAULT_CONFIG
    from app.skills.loader import set_skill_enabled
    from app.tools.files import set_root

    work = tmp_path / "work"
    (work / "uploads").mkdir(parents=True)
    pdf_path = work / "uploads" / "report.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    # pypdf cannot draw text without reportlab; the routing itself is what matters,
    # so create a PDF and assert the reply mentions the pdf skill path (pages info).
    with open(pdf_path, "wb") as f:
        writer.write(f)

    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["resources"]["files"]["root"] = str(work)
    set_skill_enabled(cfg, "pdf", True)
    set_root(str(work))

    reply = run_agent(
        "web:admin",
        [{"role": "user", "content": "读取 uploads/report.pdf 并总结"}],
        cfg,
        is_admin=True,
    )
    assert "共 1 页" in reply or "pages" in reply or "文件 uploads/report.pdf" in reply
    assert "不是 UTF-8" not in reply


def test_list_uploads_and_find_pdfs(tmp_path, monkeypatch):
    """列出上传文件、查找各目录 PDF 都能给出文件级结果。"""
    import app.agent.web_agent as wa
    import app.tools.files as files_tools

    work = tmp_path / "work"
    (work / "uploads").mkdir(parents=True)
    (work / "uploads" / "doc.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    (work / "uploads" / "note.txt").write_text("hi", encoding="utf-8")
    (work / "docs").mkdir()
    (work / "docs" / "guide.pdf").write_bytes(b"%PDF-1.4\n%%EOF")

    monkeypatch.setattr(files_tools, "PROJECT_ROOT", work)

    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["resources"]["files"]["root"] = str(work)

    reply = wa.run_agent(
        "web:admin",
        [{"role": "user", "content": "列出已经上传的文件"}],
        cfg,
        is_admin=True,
    )
    assert "doc.pdf" in reply and "note.txt" in reply

    reply = wa.run_agent(
        "web:admin",
        [{"role": "user", "content": "寻找各目录里有没有pdf 文件"}],
        cfg,
        is_admin=True,
    )
    assert "uploads/doc.pdf" in reply and "docs/guide.pdf" in reply
