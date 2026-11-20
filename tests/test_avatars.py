"""اختبارات وحدة معرض أفاتار البوتات (krouchi_dz.avatars).

بلا شاشة وبلا شبكة: الدوال نقية، ومجلد المعرض يُوجَّه بمتغيّر
البيئة KROUCHI_AVATARS_DIR إلى مجلد مؤقت فيه ملفات وهمية.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz.avatars import (
    GALLERY_FILES,
    avatar_image_path,
    display_avatar_text,
    find_avatars_dir,
    is_gallery_avatar,
    monogram_for_name,
)


class TestIsGalleryAvatar(unittest.TestCase):
    def test_gallery_filenames_are_recognized(self):
        self.assertEqual(
            GALLERY_FILES,
            [f"bot_{i}.png" for i in range(1, 7)],
        )
        for name in GALLERY_FILES:
            self.assertTrue(is_gallery_avatar(name), name)
        self.assertTrue(is_gallery_avatar("bot_3.png"))

    def test_non_gallery_values_are_rejected(self):
        for value in (
            "🤖",          # قيمة قديمة (إيموجي افتراضي قبل المعرض)
            "🔎",          # إيموجي قديم آخر
            "",            # فارغة = بلا صورة (أحادي)
            "bot_99.png",  # خارج المعرض
            "bot_0.png",
            "bot_1.jpg",
            "BOT_1.PNG",
            "avatars/bot_1.png",  # بالمسار ليست اسم ملف حرفياً
            " bot_1.png",
            None,
            3,
        ):
            self.assertFalse(is_gallery_avatar(value), repr(value))


class TestFindAvatarsDir(unittest.TestCase):
    def test_env_var_points_at_tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ, {"KROUCHI_AVATARS_DIR": tmp}
            ):
                self.assertEqual(find_avatars_dir(), Path(tmp))

    def test_env_var_non_directory_is_skipped(self):
        # مرشّح البيئة ليس مجلداً ⇒ لا يُقبل؛ يقع البحث على التالي
        # (مجلد المعرض الحقيقي بجانب الحزمة في شجرة المصدر هذه).
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "no_such_dir")
            with mock.patch.dict(
                os.environ, {"KROUCHI_AVATARS_DIR": missing}
            ):
                found = find_avatars_dir()
                self.assertNotEqual(found, Path(missing))
                if found is not None:
                    self.assertTrue(found.is_dir())

    def test_repo_gallery_found_without_env(self):
        # شجرة المصدر هذه تحمل assets/avatars فعلاً بجانب الحزمة.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KROUCHI_AVATARS_DIR", None)
            found = find_avatars_dir()
            self.assertIsNotNone(found)
            self.assertTrue((found / "bot_1.png").is_file())


class TestAvatarImagePath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.gallery = Path(self.tmp.name) / "avatars"
        self.gallery.mkdir()
        (self.gallery / "bot_1.png").write_bytes(b"\x89PNG-dummy")
        patcher = mock.patch.dict(
            os.environ, {"KROUCHI_AVATARS_DIR": str(self.gallery)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_existing_gallery_file_resolves(self):
        self.assertEqual(
            avatar_image_path("bot_1.png"), self.gallery / "bot_1.png"
        )

    def test_missing_gallery_file_is_none(self):
        self.assertIsNone(avatar_image_path("bot_2.png"))

    def test_non_gallery_values_are_none(self):
        for value in ("🤖", "", "bot_99.png", None):
            self.assertIsNone(avatar_image_path(value), repr(value))

    def test_missing_dir_is_none_not_crash(self):
        with mock.patch.dict(
            os.environ,
            {"KROUCHI_AVATARS_DIR": str(Path(self.tmp.name) / "gone")},
        ):
            # البيئة تشير لغائب فيسقط المرشّح؛ إن وُجد مجلد آخر صالح
            # في سلسلة البحث فقد يجد bot_1.png فيه — المهم: لا انهيار
            # والنتيجة مسار موجود فعلاً أو None.
            result = avatar_image_path("bot_1.png")
            self.assertTrue(result is None or result.is_file())


class TestMonogram(unittest.TestCase):
    def test_first_letter_of_trimmed_name(self):
        self.assertEqual(monogram_for_name("مساعد"), "م")
        self.assertEqual(monogram_for_name("  Alpha "), "A")
        self.assertEqual(monogram_for_name(""), "؟")
        self.assertEqual(monogram_for_name(None), "؟")

    def test_display_text_never_shows_stored_value(self):
        # إيموجي قديم أو اسم ملف معرض: النصّ المعروض أحادي دائماً.
        self.assertEqual(
            display_avatar_text({"name": "بوت", "avatar": "🤖"}), "ب"
        )
        self.assertEqual(
            display_avatar_text({"name": "بوت", "avatar": "bot_3.png"}),
            "ب",
        )
        self.assertEqual(
            display_avatar_text({"name": "بوت", "avatar": ""}), "ب"
        )


if __name__ == "__main__":
    unittest.main()
