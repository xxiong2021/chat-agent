import pytest

from app.tools import files


@pytest.fixture
def project_root(monkeypatch, tmp_path):
    monkeypatch.setattr(files, "PROJECT_ROOT", tmp_path)
    return tmp_path


def test_file_tools_allow_regular_project_files(project_root):
    result = files.file_write("notes/todo.txt", "buy milk")

    assert result["success"] is True
    assert files.file_read("notes/todo.txt")["content"] == "buy milk"
    assert files.file_delete("notes/todo.txt")["success"] is True


def test_file_tools_reject_paths_outside_project(project_root):
    with pytest.raises(PermissionError):
        files.file_read("../outside.txt")


def test_file_tools_reject_and_hide_sensitive_files(project_root):
    (project_root / ".env").write_text("LLM_API_KEY=secret", encoding="utf-8")
    (project_root / "visible.txt").write_text("safe", encoding="utf-8")

    with pytest.raises(PermissionError):
        files.file_read(".env")

    names = [item["name"] for item in files.file_list()["items"]]
    assert names == ["visible.txt"]
