import sqlite3
from pathlib import Path


class ConversationMemory:

    def __init__(self, db_path="data/agent.db"):

        self.db_path = Path(db_path)

        # 创建 data 目录
        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._init_database()

    def _connect(self):

        return sqlite3.connect(
            self.db_path
        )

    def _init_database(self):

        conn = self._connect()

        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.commit()
        conn.close()

    def get_history(
        self,
        user_id: str,
        limit: int = 20,
    ) -> list:

        conn = self._connect()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT role, content
            FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                user_id,
                limit,
            ),
        )

        rows = cursor.fetchall()

        conn.close()

        # 数据库是倒序取出的
        rows.reverse()

        return [
            {
                "role": role,
                "content": content,
            }
            for role, content in rows
            if content
        ]

    def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
    ):

        conn = self._connect()

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO messages
            (user_id, role, content)
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                role,
                content,
            ),
        )

        conn.commit()
        conn.close()

    def clear(self, user_id: str):

        conn = self._connect()

        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM messages
            WHERE user_id = ?
            """,
            (user_id,),
        )

        conn.commit()
        conn.close()
