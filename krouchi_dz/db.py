"""طبقة التخزين المحلي (SQLite) في Krouchi_DZ.

كل البيانات تعيش في ملف واحد داخل مجلد البيانات المحلي:
البوتات، المحادثات ورسائلها مرتبة، سجلّ تدقيق قرارات الوسيط،
والإعدادات العامة. جدول المزوّدين مرآة لملف الإعدادات JSON ويحمل
مرجع السرّ فقط (secret_ref) — المفتاح نفسه لا يصل هنا إطلاقاً.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS providers (
    name         TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    base_url     TEXT NOT NULL DEFAULT '',
    secret_ref   TEXT NOT NULL DEFAULT '',
    default_model TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS bots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    avatar        TEXT NOT NULL DEFAULT '🤖',
    provider_name TEXT NOT NULL,
    model         TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    approval_mode TEXT NOT NULL DEFAULT 'ask',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id     INTEGER NOT NULL REFERENCES bots(id),
    title      TEXT NOT NULL DEFAULT 'محادثة',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role           TEXT NOT NULL,
    content        TEXT NOT NULL DEFAULT '',
    tool_calls_json TEXT,
    tool_call_id   TEXT,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id     INTEGER,
    action     TEXT NOT NULL,
    decision   TEXT NOT NULL,
    reason     TEXT NOT NULL DEFAULT '',
    details    TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id      INTEGER NOT NULL REFERENCES bots(id),
    title       TEXT NOT NULL DEFAULT '',
    prompt      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'queued',
    result      TEXT,
    error       TEXT,
    log         TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);
"""

APPROVAL_MODES = ("ask", "full", "readonly")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """غلاف رفيع حول sqlite3 بكل عمليات Krouchi_DZ."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- المزوّدون (مرآة ملف الإعدادات، بلا مفاتيح) ---------------------
    def upsert_provider(
        self, name: str, kind: str, base_url: str, secret_ref: str,
        default_model: str = "",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO providers (name, kind, base_url, secret_ref, default_model)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                kind=excluded.kind, base_url=excluded.base_url,
                secret_ref=excluded.secret_ref,
                default_model=excluded.default_model
            """,
            (name, kind, base_url, secret_ref, default_model),
        )
        self.conn.commit()

    def get_provider(self, name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM providers WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def list_providers(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM providers ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    # -- البوتات ---------------------------------------------------------
    def create_bot(
        self,
        name: str,
        provider_name: str,
        model: str = "",
        system_prompt: str = "",
        avatar: str = "🤖",
        approval_mode: str = "ask",
    ) -> int:
        if approval_mode not in APPROVAL_MODES:
            raise ValueError(f"نمط موافقة غير معروف: {approval_mode}")
        cur = self.conn.execute(
            """
            INSERT INTO bots (name, avatar, provider_name, model,
                              system_prompt, approval_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, avatar, provider_name, model, system_prompt,
             approval_mode, _now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_bot(self, bot_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM bots WHERE id = ?", (bot_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_bots(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM bots ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def set_bot_approval_mode(self, bot_id: int, mode: str) -> None:
        if mode not in APPROVAL_MODES:
            raise ValueError(f"نمط موافقة غير معروف: {mode}")
        self.conn.execute(
            "UPDATE bots SET approval_mode = ? WHERE id = ?", (mode, bot_id)
        )
        self.conn.commit()

    def update_bot(
        self,
        bot_id: int,
        *,
        name: str | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        avatar: str | None = None,
        approval_mode: str | None = None,
    ) -> None:
        """يحدّث حقول بوت قائم (تُمرَّر الحقول المراد تغييرها فقط).

        إضافة خالصة لواجهة الخطوة 2 — لا يغيّر أي سلوك قائم.
        """
        if approval_mode is not None and approval_mode not in APPROVAL_MODES:
            raise ValueError(f"نمط موافقة غير معروف: {approval_mode}")
        fields: dict[str, object] = {}
        if name is not None:
            fields["name"] = name
        if provider_name is not None:
            fields["provider_name"] = provider_name
        if model is not None:
            fields["model"] = model
        if system_prompt is not None:
            fields["system_prompt"] = system_prompt
        if avatar is not None:
            fields["avatar"] = avatar
        if approval_mode is not None:
            fields["approval_mode"] = approval_mode
        if not fields:
            return
        assignments = ", ".join(f"{col} = ?" for col in fields)
        self.conn.execute(
            f"UPDATE bots SET {assignments} WHERE id = ?",
            (*fields.values(), bot_id),
        )
        self.conn.commit()

    # -- المحادثات والرسائل ----------------------------------------------
    def get_or_create_conversation(self, bot_id: int, title: str = "محادثة") -> int:
        row = self.conn.execute(
            "SELECT id FROM conversations WHERE bot_id = ? ORDER BY id LIMIT 1",
            (bot_id,),
        ).fetchone()
        if row:
            return int(row["id"])
        cur = self.conn.execute(
            "INSERT INTO conversations (bot_id, title, created_at) VALUES (?, ?, ?)",
            (bot_id, title, _now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str = "",
        tool_calls_json: str | None = None,
        tool_call_id: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content,
                                  tool_calls_json, tool_call_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conversation_id, role, content, tool_calls_json, tool_call_id, _now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_messages(self, conversation_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_bot_messages(self, bot_id: int) -> int:
        """يمسح كل رسائل محادثات هذا البوت نهائياً ويعيد عددها.

        تبقى صفوف المحادثات نفسها — تُفرَّغ الرسائل فقط، فتبدأ
        الجولة التالية من سجلّ فارغ. رسائل البوتات الأخرى لا تُمسّ.
        """
        cur = self.conn.execute(
            "DELETE FROM messages WHERE conversation_id IN "
            "(SELECT id FROM conversations WHERE bot_id = ?)",
            (bot_id,),
        )
        self.conn.commit()
        return cur.rowcount

    # -- سجلّ التدقيق -------------------------------------------------------
    def log_audit(
        self, bot_id: int | None, action: str, decision: str,
        reason: str = "", details: dict | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO audit_log (bot_id, action, decision, reason, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (bot_id, action, decision, reason,
             json.dumps(details or {}, ensure_ascii=False), _now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_audit(self, bot_id: int | None = None) -> list[dict]:
        if bot_id is None:
            rows = self.conn.execute(
                "SELECT * FROM audit_log ORDER BY id"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM audit_log WHERE bot_id = ? ORDER BY id", (bot_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -- الإعدادات العامة ---------------------------------------------------
    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default
