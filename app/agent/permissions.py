import secrets
import time


class PermissionManager:

    AUTO = "auto"
    CONFIRM = "confirm"

    def __init__(self, pending_ttl_seconds: int = 300):
        self.tool_permissions = {
            "web_search": self.AUTO,
            "calculator": self.AUTO,
            "file_list": self.AUTO,
            "file_read": self.AUTO,
            "file_write": self.CONFIRM,
            "file_delete": self.CONFIRM,
            "send_email": self.CONFIRM,
            "send_whatsapp": self.CONFIRM,
        }
        self.pending_actions = {}
        self.pending_ttl_seconds = pending_ttl_seconds

    def get_permission(self, tool_name: str) -> str:
        return self.tool_permissions.get(tool_name, self.CONFIRM)

    def requires_confirmation(self, tool_name: str) -> bool:
        return self.get_permission(tool_name) == self.CONFIRM

    def set_pending_action(
        self,
        user_id: str,
        tool_name: str,
        arguments: dict,
    ) -> None:
        created_at = time.monotonic()
        self.pending_actions[user_id] = {
            "tool_name": tool_name,
            "arguments": arguments,
            "confirmation_token": secrets.token_urlsafe(6),
            "created_at": created_at,
            "expires_at": created_at + self.pending_ttl_seconds,
        }

    def get_pending_action(self, user_id: str):
        action = self.pending_actions.get(user_id)
        if not action:
            return None

        if time.monotonic() >= action["expires_at"]:
            self.clear_pending_action(user_id)
            return None

        return action

    def clear_pending_action(self, user_id: str) -> None:
        self.pending_actions.pop(user_id, None)
