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


class TestSkillsAndMemory(unittest.TestCase):
    """جدولا skills وbot_memory (الإصدار 3.6.0): ذهاب وإياب كامل."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_skill_round_trip_and_origins(self):
        skill_id = self.db.save_skill(
            "محضر اجتماع", "صيغة كتابة المحاضر", "1- الترويسة…",
            origin="installed",
        )
        self.assertGreater(skill_id, 0)
        skill = self.db.get_skill("محضر اجتماع")
        self.assertEqual(skill["description"], "صيغة كتابة المحاضر")
        self.assertEqual(skill["instructions"], "1- الترويسة…")
        self.assertEqual(skill["origin"], "installed")
        self.assertEqual(
            [s["name"] for s in self.db.list_skills()], ["محضر اجتماع"]
        )

    def test_skill_update_keeps_origin_and_creation(self):
        self.db.save_skill("مهارة", "وصف أول", "تعليمات أولى", origin="bot")
        before = self.db.get_skill("مهارة")
        self.db.save_skill("مهارة", "وصف جديد", "تعليمات جديدة", origin="taught")
        after = self.db.get_skill("مهارة")
        self.assertEqual(after["id"], before["id"])
        self.assertEqual(after["description"], "وصف جديد")
        self.assertEqual(after["instructions"], "تعليمات جديدة")
        self.assertEqual(after["origin"], "bot")  # المصدر الأصلي يبقى
        self.assertEqual(after["created_at"], before["created_at"])
        self.assertEqual(len(self.db.list_skills()), 1)

    def test_skill_bad_origin_rejected(self):
        with self.assertRaises(ValueError):
            self.db.save_skill("مهارة", "", "", origin="مجهول")

    def test_skill_delete(self):
        self.db.save_skill("مهارة", "", "تعليمات")
        self.assertTrue(self.db.delete_skill("مهارة"))
        self.assertIsNone(self.db.get_skill("مهارة"))
        self.assertFalse(self.db.delete_skill("مهارة"))

    def test_memory_shared_and_per_bot(self):
        self.db.add_memory(None, "حقيقة مشتركة")
        self.db.add_memory(5, "حقيقة البوت 5")
        self.db.add_memory(7, "حقيقة البوت 7")
        self.assertEqual(len(self.db.list_memory()), 3)
        self.assertEqual(
            [n["fact"] for n in self.db.list_memory(5)], ["حقيقة البوت 5"]
        )
        prompt_notes = self.db.memory_for_prompt(5)
        self.assertEqual(
            [n["fact"] for n in prompt_notes],
            ["حقيقة مشتركة", "حقيقة البوت 5"],
        )

    def test_memory_for_prompt_latest_20_oldest_first(self):
        for i in range(25):
            self.db.add_memory(3, f"حقيقة {i}")
        notes = self.db.memory_for_prompt(3)
        self.assertEqual(len(notes), 20)
        self.assertEqual(notes[0]["fact"], "حقيقة 5")
        self.assertEqual(notes[-1]["fact"], "حقيقة 24")

    def test_memory_delete(self):
        note_id = self.db.add_memory(None, "تُحذف")
        self.assertTrue(self.db.delete_memory(note_id))
        self.assertEqual(self.db.list_memory(), [])
        self.assertFalse(self.db.delete_memory(note_id))


if __name__ == "__main__":
    unittest.main()
