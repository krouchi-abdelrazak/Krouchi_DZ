"""اختبارات وحدة اللغات (i18n) — العربية والإنجليزية فقط.

لا شاشة ولا شبكة: جدول النصوص، التراجع، الاتجاه، وحفظ الاختيار
في إعدادات قاعدة البيانات.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz import i18n
from krouchi_dz.db import Database


class I18nFixture(unittest.TestCase):
    def setUp(self):
        i18n.set_lang("ar")
        self.addCleanup(i18n.set_lang, "ar")


class TestStringTable(I18nFixture):
    def test_only_arabic_and_english(self):
        self.assertEqual(i18n.SUPPORTED_LANGS, ("ar", "en"))
        self.assertEqual(set(i18n.STRINGS), {"ar", "en"})

    def test_key_parity_between_languages(self):
        self.assertEqual(set(i18n.STRINGS["ar"]), set(i18n.STRINGS["en"]))

    def test_no_empty_values(self):
        for lang, table in i18n.STRINGS.items():
            for key, value in table.items():
                self.assertIsInstance(value, str, f"{lang}:{key}")
                self.assertTrue(value.strip(), f"{lang}:{key} فارغة")

    def test_arabic_entries_are_the_original_ui_texts(self):
        # عيّنة من نصوص الواجهة الأصلية — يجب أن تبقى حرفية كما كانت.
        self.assertEqual(i18n.STRINGS["ar"]["app.send"], "إرسال")
        self.assertEqual(i18n.STRINGS["ar"]["mode.ask"], "اسأل")
        self.assertEqual(i18n.STRINGS["ar"]["action.write_file"], "كتابة ملف")
        self.assertEqual(i18n.STRINGS["ar"]["decision.allowed"], "سماح ✓")


class TestLookup(I18nFixture):
    def test_default_language_is_arabic(self):
        self.assertEqual(i18n.get_lang(), "ar")
        self.assertEqual(i18n.t("app.send"), "إرسال")

    def test_english_lookup(self):
        i18n.set_lang("en")
        self.assertEqual(i18n.t("app.send"), "Send")
        self.assertEqual(i18n.t("mode.ask"), "Ask")
        self.assertEqual(i18n.t("common.allow"), "Approve")

    def test_unsupported_language_falls_back_to_arabic(self):
        self.assertEqual(i18n.set_lang("fr"), "ar")
        self.assertEqual(i18n.get_lang(), "ar")
        self.assertEqual(i18n.set_lang(""), "ar")

    def test_missing_key_returns_the_key_itself(self):
        self.assertEqual(i18n.t("no.such.key"), "no.such.key")
        i18n.set_lang("en")
        self.assertEqual(i18n.t("no.such.key"), "no.such.key")

    def test_missing_in_current_falls_back_to_arabic(self):
        saved = i18n.STRINGS["en"].pop("app.send")
        try:
            i18n.set_lang("en")
            self.assertEqual(i18n.t("app.send"), "إرسال")
        finally:
            i18n.STRINGS["en"]["app.send"] = saved

    def test_format_placeholders(self):
        self.assertEqual(
            i18n.t("approval.countdown", seconds=42),
            "يُرفض تلقائياً بعد 42 ثانية إن لم تُجب",
        )
        i18n.set_lang("en")
        self.assertEqual(
            i18n.t("addapi.success", provider="openrouter", count=3),
            "Success: “openrouter” — 3 models available",
        )

    def test_rtl_only_for_arabic(self):
        self.assertTrue(i18n.is_rtl())
        i18n.set_lang("en")
        self.assertFalse(i18n.is_rtl())


class TestPersistence(I18nFixture):
    def make_db(self, tmp: str) -> Database:
        return Database(Path(tmp) / "data" / "krouchi.db")

    def test_default_when_unset_is_arabic(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_db(tmp)
            self.assertEqual(i18n.load_lang(db), "ar")
            db.close()

    def test_save_and_reload_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_db(tmp)
            self.assertEqual(i18n.save_lang(db, "en"), "en")
            self.assertEqual(db.get_setting("ui_lang", ""), "en")
            self.assertEqual(i18n.get_lang(), "en")
            db.close()
            # قاعدة جديدة على نفس الملف: الاختيار محفوظ.
            db2 = self.make_db(tmp)
            i18n.set_lang("ar")
            self.assertEqual(i18n.load_lang(db2), "en")
            db2.close()

    def test_stored_garbage_falls_back_to_arabic(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_db(tmp)
            db.set_setting("ui_lang", "fr")
            self.assertEqual(i18n.load_lang(db), "ar")
            db.close()


class TestKrouchiAiBranding(I18nFixture):
    """علامة Krouchi AI (الإصدار 3.5.0): طبقة الذكاء المشتركة تحمل
    اسم «Krouchi AI» في عنوان حوار الواجهة المشتركة وتسمياتها
    بالعربي والإنجليزي — ومفاتيح الإعدادات الداخلية لا تتغيّر."""

    def test_shared_api_title_is_krouchi_ai(self):
        self.assertEqual(
            i18n.STRINGS["ar"]["sharedapi.title"],
            "Krouchi AI — الذكاء المشترك لكل البوتات",
        )
        self.assertEqual(
            i18n.STRINGS["en"]["sharedapi.title"],
            "Krouchi AI — the shared intelligence for all bots",
        )

    def test_shared_api_labels_carry_the_brand(self):
        for lang in ("ar", "en"):
            self.assertIn("Krouchi AI", i18n.STRINGS[lang]["sharedapi.hint"])
            self.assertIn("Krouchi AI", i18n.STRINGS[lang]["app.shared_api"])
            self.assertIn("Krouchi AI", i18n.STRINGS[lang]["bot.shared_change"])

    def test_see_screen_action_label(self):
        self.assertEqual(i18n.STRINGS["ar"]["action.see_screen"], "رؤية الشاشة")
        self.assertEqual(i18n.STRINGS["en"]["action.see_screen"], "See screen")

    def test_gui_dialog_uses_the_branded_title_key(self):
        from krouchi_dz import gui

        source = Path(gui.__file__).read_text(encoding="utf-8")
        self.assertIn("class SharedApiDialog", source)
        self.assertIn('t("sharedapi.title")', source)


if __name__ == "__main__":
    unittest.main()
