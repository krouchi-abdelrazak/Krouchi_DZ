"""اختبارات التشغيل مع بدء ويندوز (autostart) — اختصار مجلد بدء التشغيل.

بلا شاشة وبلا PowerShell فعلي أبداً: منفّذ إنشاء الاختصار وهمي
بالحقن (runner)، وفحص الوجود وهمي بالحقن (exists)، ومحاكاة ويندوز
بحقن ثابت المنصّة في الوحدة (IS_WINDOWS) — فتعمل الاختبارات على
أي نظام تشغيل.
"""

import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock as umock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz import autostart


class AutostartFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)


class TestShortcutPath(AutostartFixture):
    def test_path_composition_from_explicit_appdata(self):
        result = autostart.startup_shortcut_path(self.base / "Roaming")
        self.assertEqual(
            result,
            self.base
            / "Roaming"
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
            / "Krouchi_DZ.lnk",
        )

    def test_path_composition_accepts_str_appdata(self):
        result = autostart.startup_shortcut_path(str(self.base))
        self.assertEqual(result.name, "Krouchi_DZ.lnk")
        self.assertEqual(result.parent.name, "Startup")
        self.assertTrue(str(result).startswith(str(self.base)))

    def test_appdata_env_fallback(self):
        fake_appdata = str(self.base / "EnvRoaming")
        with umock.patch.dict(os.environ, {"APPDATA": fake_appdata}):
            result = autostart.startup_shortcut_path()
        self.assertEqual(
            result,
            Path(fake_appdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
            / "Krouchi_DZ.lnk",
        )

    def test_home_fallback_without_appdata(self):
        with umock.patch.dict(os.environ, {}, clear=True):
            with umock.patch.object(
                Path, "home", classmethod(lambda cls: self.base)
            ):
                result = autostart.startup_shortcut_path()
        self.assertEqual(
            result,
            self.base
            / "AppData"
            / "Roaming"
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
            / "Krouchi_DZ.lnk",
        )


class TestIsStartupEnabled(AutostartFixture):
    def test_true_with_fake_exists(self):
        seen = []

        def fake_exists(p):
            seen.append(p)
            return True

        shortcut = self.base / "Krouchi_DZ.lnk"
        self.assertTrue(autostart.is_startup_enabled(shortcut, exists=fake_exists))
        self.assertEqual(seen, [shortcut])

    def test_false_with_fake_exists(self):
        shortcut = self.base / "Krouchi_DZ.lnk"
        self.assertFalse(
            autostart.is_startup_enabled(shortcut, exists=lambda p: False)
        )

    def test_default_path_comes_from_appdata_env(self):
        fake_appdata = str(self.base / "EnvRoaming")
        expected = autostart.startup_shortcut_path(fake_appdata)
        with umock.patch.dict(os.environ, {"APPDATA": fake_appdata}):
            self.assertTrue(
                autostart.is_startup_enabled(exists=lambda p: p == expected)
            )
            self.assertFalse(
                autostart.is_startup_enabled(exists=lambda p: False)
            )


class TestDefaultTarget(AutostartFixture):
    def test_dev_tree_uses_python_and_quoted_run_gui(self):
        root = Path(autostart.__file__).resolve().parent.parent
        exe = root / "Krouchi_DZ.exe"
        target, args = autostart.default_target()
        if exe.is_file():
            # تخطيط مجمّع/مثبَّت: الهدف هو exe نفسه بلا وسائط.
            self.assertEqual(target, str(exe))
            self.assertEqual(args, "")
        else:
            # شجرة المصدر: المفسّر الحالي + مسار run_gui.py مقتبساً.
            self.assertEqual(target, sys.executable)
            self.assertEqual(args, f'"{root / "run_gui.py"}"')


class TestSetStartupEnabled(AutostartFixture):
    def make_fake_runner(self, rc=0, stderr=""):
        calls = []

        def fake_runner(argv):
            calls.append(list(argv))
            return rc, "", stderr

        return calls, fake_runner

    def test_disable_removes_existing_shortcut(self):
        shortcut = self.base / "Startup" / "Krouchi_DZ.lnk"
        shortcut.parent.mkdir(parents=True)
        shortcut.write_bytes(b"lnk")
        result = autostart.set_startup_enabled(False, shortcut_path=shortcut)
        self.assertFalse(result)
        self.assertFalse(shortcut.exists())

    def test_disable_missing_shortcut_is_not_an_error(self):
        shortcut = self.base / "Krouchi_DZ.lnk"
        self.assertFalse(
            autostart.set_startup_enabled(False, shortcut_path=shortcut)
        )

    def test_enable_builds_powershell_shortcut_script(self):
        calls, fake_runner = self.make_fake_runner()
        shortcut = self.base / "Startup" / "Krouchi_DZ.lnk"
        target = str(self.base / "Krouchi_DZ.exe")
        with umock.patch.object(autostart, "IS_WINDOWS", True):
            result = autostart.set_startup_enabled(
                True,
                shortcut_path=shortcut,
                target=target,
                runner=fake_runner,
            )
        self.assertTrue(result)
        self.assertEqual(len(calls), 1)
        argv = calls[0]
        self.assertEqual(argv[0], "powershell")
        joined = " ".join(argv)
        self.assertIn("WScript.Shell", joined)
        self.assertIn("CreateShortcut", joined)
        self.assertIn(str(shortcut), joined)
        self.assertIn(target, joined)
        self.assertIn("$s.Save()", joined)

    def test_enable_passes_args_and_default_icon_when_present(self):
        icon = self.base / "assets" / "icon.ico"
        icon.parent.mkdir(parents=True)
        icon.write_bytes(b"ico")
        calls, fake_runner = self.make_fake_runner()
        target = str(self.base / "Krouchi_DZ.exe")
        with umock.patch.object(autostart, "IS_WINDOWS", True):
            autostart.set_startup_enabled(
                True,
                shortcut_path=self.base / "Krouchi_DZ.lnk",
                target=target,
                args="--from-startup",
                runner=fake_runner,
            )
        joined = " ".join(calls[0])
        self.assertIn("$s.Arguments = '--from-startup'", joined)
        self.assertIn(f"$s.IconLocation = '{icon}'", joined)
        self.assertIn(f"$s.WorkingDirectory = '{self.base}'", joined)

    def test_enable_without_icon_file_omits_icon_location(self):
        calls, fake_runner = self.make_fake_runner()
        with umock.patch.object(autostart, "IS_WINDOWS", True):
            autostart.set_startup_enabled(
                True,
                shortcut_path=self.base / "Krouchi_DZ.lnk",
                target=str(self.base / "Krouchi_DZ.exe"),
                runner=fake_runner,
            )
        self.assertNotIn("IconLocation", " ".join(calls[0]))

    def test_default_runner_passes_create_no_window(self):
        captured = {}

        def fake_run(argv, **kwargs):
            captured["argv"] = list(argv)
            captured["kwargs"] = kwargs
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        with umock.patch.object(autostart, "IS_WINDOWS", True):
            with umock.patch.object(autostart.subprocess, "run", fake_run):
                result = autostart.set_startup_enabled(
                    True,
                    shortcut_path=self.base / "Krouchi_DZ.lnk",
                    target=str(self.base / "Krouchi_DZ.exe"),
                )
        self.assertTrue(result)
        self.assertEqual(
            captured["kwargs"].get("creationflags"),
            getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(captured["argv"][0], "powershell")

    def test_apostrophe_in_target_is_doubled_in_script(self):
        calls, fake_runner = self.make_fake_runner()
        target = "/opt/O'Brien/Krouchi_DZ.exe"
        with umock.patch.object(autostart, "IS_WINDOWS", True):
            autostart.set_startup_enabled(
                True,
                shortcut_path=self.base / "Krouchi_DZ.lnk",
                target=target,
                runner=fake_runner,
            )
        joined = " ".join(calls[0])
        self.assertIn("O''Brien", joined)
        self.assertIn("$s.TargetPath = '/opt/O''Brien/Krouchi_DZ.exe'", joined)

    def test_powershell_failure_raises_runtime_error(self):
        calls, fake_runner = self.make_fake_runner(rc=1, stderr="boom")
        with umock.patch.object(autostart, "IS_WINDOWS", True):
            with self.assertRaises(RuntimeError) as ctx:
                autostart.set_startup_enabled(
                    True,
                    shortcut_path=self.base / "Krouchi_DZ.lnk",
                    target=str(self.base / "Krouchi_DZ.exe"),
                    runner=fake_runner,
                )
        self.assertIn("boom", str(ctx.exception))

    def test_non_windows_guard_raises(self):
        calls, fake_runner = self.make_fake_runner()
        with umock.patch.object(autostart, "IS_WINDOWS", False):
            with umock.patch.object(os, "name", "posix"):
                with self.assertRaises(RuntimeError):
                    autostart.set_startup_enabled(
                        True,
                        shortcut_path=self.base / "Krouchi_DZ.lnk",
                        target=str(self.base / "Krouchi_DZ.exe"),
                        runner=fake_runner,
                    )
        self.assertEqual(calls, [])  # المنفّذ لم يُستدعَ أصلاً


if __name__ == "__main__":
    unittest.main()
