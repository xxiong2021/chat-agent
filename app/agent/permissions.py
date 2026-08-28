class PermissionManager:

    AUTO = "auto"
    CONFIRM = "confirm"

    def __init__(self):

        self.tool_permissions = {

            # 低风险
            "web_search": self.AUTO,
            "calculator": self.AUTO,

            # 未来加入
            "send_email": self.CONFIRM,
            "send_whatsapp": self.CONFIRM,
            "delete_file": self.CONFIRM,
        }

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
