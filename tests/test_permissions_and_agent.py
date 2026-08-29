from types import SimpleNamespace

from app.agent import agent
from app.agent.permissions import PermissionManager
from app.agent.users import UserManager


def test_pending_action_requires_matching_confirmation_token(monkeypatch):
    manager = PermissionManager()
    calls = []

    monkeypatch.setattr(agent, "permission_manager", manager)
    monkeypatch.setitem(
        agent.TOOL_FUNCTIONS,
        "file_delete",
        lambda path: calls.append(path) or {
            "success": True,
            "path": path,
            "message": "文件已删除",
        },
    )

    prompt = agent.create_pending_action(
        "user-1",
        "file_delete",
        {"path": "draft.txt"},
    )
    pending = manager.get_pending_action("user-1")

    assert f"确认 {pending['confirmation_token']}" in prompt
    assert "等待你的确认" in agent.ask_agent("好", user_id="user-1")
    assert calls == []

    response = agent.ask_agent(
        f"确认 {pending['confirmation_token']}",
        user_id="user-1",
    )
    assert "文件删除成功" in response
    assert calls == ["draft.txt"]


def test_expired_pending_action_is_removed():
    manager = PermissionManager(pending_ttl_seconds=0)
    manager.set_pending_action("user-1", "file_delete", {"path": "draft.txt"})

    assert manager.get_pending_action("user-1") is None
    assert manager.pending_actions == {}


def test_file_write_confirmation_uses_an_action_specific_token(monkeypatch):
    manager = PermissionManager()
    writes = []

    monkeypatch.setattr(agent, "permission_manager", manager)
    monkeypatch.setitem(
        agent.TOOL_FUNCTIONS,
        "file_write",
        lambda path, content: writes.append((path, content)) or {
            "success": True,
            "path": path,
            "message": "文件写入成功",
        },
    )

    agent.create_pending_action(
        "user-1",
        "file_write",
        {"path": "draft.txt", "content": "new content"},
    )
    token = manager.get_pending_action("user-1")["confirmation_token"]

    agent.ask_agent(f"确认 {token}", user_id="user-1")
    assert writes == [("draft.txt", "new content")]


def test_chinese_postfix_delete_request_extracts_path():
    assert agent.extract_file_path_for_delete("把 test.txt 删除") == {
        "path": "test.txt"
    }


def test_user_manager_enforces_enabled_status_and_roles():
    manager = UserManager()
    manager.users = {
        "1": {"name": "Disabled", "enabled": False, "role": "user"},
        "2": {"name": "Admin", "enabled": True, "role": "admin"},
    }

    assert manager.is_allowed(1) is False
    assert manager.is_allowed(2) is True
    assert manager.get_role(2) == "admin"
    assert manager.get_role(999) == "none"


def test_agent_tool_loop_with_mocked_llm(monkeypatch):
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="calculator",
            arguments='{"expression": "3 + 4"}',
        ),
    )
    responses = iter([
        SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[tool_call])
            )]
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="结果是 7", tool_calls=None)
            )]
        ),
    ])
    create_calls = []

    def create(**kwargs):
        create_calls.append(kwargs)
        return next(responses)

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(agent, "client", fake_client)
    monkeypatch.setattr(agent, "permission_manager", PermissionManager())

    assert agent.ask_agent("计算 3 + 4", user_id="mock-user") == "结果是 7"
    assert len(create_calls) == 2
