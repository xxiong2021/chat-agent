import base64, hashlib, hmac, os, sqlite3
from pathlib import Path
DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "company_users.db"
def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16); digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"
def verify_password(password: str, encoded: str) -> bool:
    salt, digest = encoded.split("$", 1); actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(actual, base64.b64decode(digest))
class UserStore:
    def __init__(self, path: Path = DEFAULT_DB):
        self.path = path; self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn: conn.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)")
    def create_user(self, username: str, password: str, role: str = "employee") -> None:
        if not username or len(password) < 12: raise ValueError("用户名不能为空，密码至少需要 12 个字符。")
        if role not in {"admin", "employee"}: raise ValueError("角色必须是 admin 或 employee。")
        with sqlite3.connect(self.path) as conn: conn.execute("INSERT INTO users(username, password_hash, role, enabled) VALUES (?, ?, ?, 1)", (username, hash_password(password), role))
    def authenticate(self, username: str, password: str) -> dict | None:
        with sqlite3.connect(self.path) as conn: row = conn.execute("SELECT username, password_hash, role, enabled FROM users WHERE username = ?", (username,)).fetchone()
        if not row or not row[3] or not verify_password(password, row[1]): return None
        return {"username": row[0], "role": row[2]}
