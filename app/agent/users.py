import json
from pathlib import Path


USERS_FILE = Path(__file__).resolve().parents[2] / "data" / "users.json"


class UserManager:

    def __init__(self):
        self.users = self._load_users()

    def _load_users(self):
        if not USERS_FILE.exists():
            return {}

        with USERS_FILE.open(
            "r",
            encoding="utf-8-sig",
        ) as f:
            data = json.load(f)

        return data.get("users", {})

    def get_user(self, telegram_id: int):
        return self.users.get(str(telegram_id))

    def is_allowed(self, telegram_id: int) -> bool:
        user = self.get_user(telegram_id)

        if not user:
            return False

        return user.get("enabled", False)

    def get_role(self, telegram_id: int) -> str:
        user = self.get_user(telegram_id)

        if not user:
            return "none"

        return user.get("role", "user")

    def get_name(self, telegram_id: int) -> str:
        user = self.get_user(telegram_id)

        if not user:
            return "未知用户"

        return user.get("name", "未命名用户")
