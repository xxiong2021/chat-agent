class PermissionManager:

    AUTO = "auto"
    CONFIRM = "confirm"

    def __init__(self):

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

        # 按用户保存等待确认的操作
        #
        # 例如：
        #
        # {
        #     "telegram:123456": {
        #         "tool_name": "file_write",
        #         "arguments": {
        #             "path": "test.txt",
        #             "content": "hello",
        #         },
        #     }
        # }
        self.pending_actions = {}

    def get_permission(
        self,
        tool_name: str,
    ) -> str:

        return self.tool_permissions.get(
            tool_name,
            self.CONFIRM,
        )

    def requires_confirmation(
        self,
        tool_name: str,
    ) -> bool:

        return (
            self.get_permission(tool_name)
            == self.CONFIRM
        )

    def set_pending_action(
        self,
        user_id: str,
        tool_name: str,
        arguments: dict,
    ) -> None:

        self.pending_actions[user_id] = {
            "tool_name": tool_name,
            "arguments": arguments,
        }

    def get_pending_action(
        self,
        user_id: str,
    ):

        return self.pending_actions.get(
            user_id
        )

    def clear_pending_action(
        self,
        user_id: str,
    ) -> None:

        self.pending_actions.pop(
            user_id,
            None,
        )
