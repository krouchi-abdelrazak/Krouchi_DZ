"""اختبارات طبقة قاعدة البيانات: ذهاب وإياب كامل للبوتات والرسائل والإعدادات."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz.db import Database


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_bot_round_trip(self):
        bot_id = self.db.create_bot(
            "مساعد البحث", "openrouter", model="m1",
            system_prompt="أنت مساعد", avatar="🔎", approval_mode="ask",
        )
        bot = self.db.get_bot(bot_id)
        self.assertEqual(bot["name"], "مساعد البحث")
        self.assertEqual(bot["provider_name"], "openrouter")
        self.assertEqual(bot["model"], "m1")
        self.assertEqual(bot["approval_mode"], "ask")
        self.assertEqual(len(self.db.list_bots()), 1)

    def test_invalid_approval_mode_rejected(self):
        with self.assertRaises(ValueError):
            self.db.create_bot("بوت", "openrouter", approval_mode="sometimes")

    def test_bot_default_avatar_is_empty_monogram(self):
        # بوت جديد بلا أفاتار صريح: "" (أحادي الحرف عند العرض)،
        # لا الإيموجي الافتراضي القديم "🤖".
        bot_id = self.db.create_bot("بلا صورة", "openrouter")
        self.assertEqual(self.db.get_bot(bot_id)["avatar"], "")

    def test_bot_gallery_avatar_round_trip_and_update(self):
        bot_id = self.db.create_bot(
            "بصورة", "openrouter", avatar="bot_1.png"
        )
        self.assertEqual(self.db.get_bot(bot_id)["avatar"], "bot_1.png")
        self.db.update_bot(bot_id, avatar="bot_4.png")
        self.assertEqual(self.db.get_bot(bot_id)["avatar"], "bot_4.png")
        # والعودة إلى «بلا صورة» قيمة صريحة أيضاً ("" ليست None).
        self.db.update_bot(bot_id, avatar="")
        self.assertEqual(self.db.get_bot(bot_id)["avatar"], "")

    def test_bot_legacy_emoji_avatar_still_stored_verbatim(self):
        # صفوف قديمة لا تنكسر: الإيموجي يُخزَّن كما هو ويُفسَّر
        # «غير معرضي» وقت العرض فقط (انظر avatars.is_gallery_avatar).
        bot_id = self.db.create_bot(
            "قديم", "openrouter", avatar="🔎"
        )
        self.assertEqual(self.db.get_bot(bot_id)["avatar"], "🔎")

    def test_messages_ordered_per_conversation(self):
        b1 = self.db.create_bot("أ", "groq")
        b2 = self.db.create_bot("ب", "groq")
        c1 = self.db.get_or_create_conversation(b1)
        c2 = self.db.get_or_create_conversation(b2)
        # نفس المحادثة تُعاد للبوت نفسه
        self.assertEqual(self.db.get_or_create_conversation(b1), c1)
        self.db.add_message(c1, "user", "واحد")
        self.db.add_message(c1, "assistant", "اثنان")
        self.db.add_message(c2, "user", "لعبة أخرى")
        msgs = self.db.get_messages(c1)
        self.assertEqual([m["content"] for m in msgs], ["واحد", "اثنان"])
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant"])
        self.assertEqual(len(self.db.get_messages(c2)), 1)

    def test_provider_mirror_has_ref_only(self):
        self.db.upsert_provider("openrouter", "openai", "https://x", "openrouter", "m")
        row = self.db.get_provider("openrouter")
        self.assertEqual(row["secret_ref"], "openrouter")
        self.assertNotIn("api_key", row)

    def test_settings_round_trip(self):
        self.assertEqual(self.db.get_setting("lang", "ar"), "ar")
        self.db.set_setting("lang", "ar")
        self.db.set_setting("lang", "fr")
        self.assertEqual(self.db.get_setting("lang"), "fr")

    def test_audit_round_trip(self):
        self.db.log_audit(7, "write_file", "denied", "رفض المستخدم", {"path": "a"})
        rows = self.db.get_audit(bot_id=7)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "write_file")
        self.assertEqual(rows[0]["decision"], "denied")
        self.assertEqual(self.db.get_audit(bot_id=99), [])


if __name__ == "__main__":
    unittest.main()
