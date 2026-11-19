"""اختبارات ملف إعدادات المزوّدين ومخزن الأسرار (بما فيه غياب المفاتيح عن القاعدة)."""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz.config import ensure_providers_file, load_providers
from krouchi_dz.engine import ChatEngine
from krouchi_dz.secrets import SecretsStore

PLANTED_KEY = "SK-PLANTED-TEST-KEY-9876543210"


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "providers.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_written_with_five_providers(self):
        providers = load_providers(self.path)
        self.assertTrue(self.path.exists())
        for name in ("openrouter", "groq", "zai", "nvidia", "gemini"):
            self.assertIn(name, providers)
        self.assertEqual(providers["openrouter"].base_url,
                         "https://openrouter.ai/api/v1")
        self.assertEqual(providers["groq"].base_url,
                         "https://api.groq.com/openai/v1")
        self.assertEqual(providers["zai"].base_url,
                         "https://api.z.ai/api/paas/v4")
        self.assertEqual(providers["nvidia"].base_url,
                         "https://integrate.api.nvidia.com/v1")
        self.assertEqual(providers["gemini"].kind, "gemini")
        self.assertEqual(providers["openrouter"].kind, "openai")

    def test_seed_contains_no_keys(self):
        ensure_providers_file(self.path)
        self.assertNotIn("api_key", self.path.read_text(encoding="utf-8"))

    def test_user_edits_are_respected(self):
        ensure_providers_file(self.path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        raw["providers"][0]["base_url"] = "http://127.0.0.1:9999/v1"
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        providers = load_providers(self.path)
        self.assertEqual(providers["openrouter"].base_url,
                         "http://127.0.0.1:9999/v1")


class TestSecrets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "secrets.json"
        self.store = SecretsStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        self.assertEqual(self.store.get("openrouter"), "")
        self.store.set("openrouter", PLANTED_KEY)
        self.assertEqual(self.store.get("openrouter"), PLANTED_KEY)
        self.assertTrue(self.store.has("openrouter"))
        self.assertEqual(self.store.refs(), ["openrouter"])
        self.store.delete("openrouter")
        self.assertFalse(self.store.has("openrouter"))

    def test_restrictive_permissions(self):
        self.store.set("groq", "x")
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode, 0o600)

    def test_key_never_enters_database_file(self):
        """يُزرع مفتاح مميز، تُجرى عمليات كاملة، ثم تُفحص بايتات ملف القاعدة."""
        data_dir = Path(self.tmp.name) / "data"
        engine = ChatEngine(data_dir)
        try:
            engine.set_api_key("openrouter", PLANTED_KEY)
            bot_id = engine.create_bot("بوت فحص", "openrouter")
            engine.db.add_message(
                engine.db.get_or_create_conversation(bot_id), "user", "مرحبا"
            )
            engine.perform_action(bot_id, "read_file", {"path": __file__})
            db_bytes = (data_dir / "krouchi_dz.db").read_bytes()
            self.assertNotIn(PLANTED_KEY.encode(), db_bytes)
            cfg_bytes = (data_dir / "providers.json").read_bytes()
            self.assertNotIn(PLANTED_KEY.encode(), cfg_bytes)
            # والمفتاح موجود حيث يجب: ملف الأسرار فقط
            self.assertIn(PLANTED_KEY.encode(),
                          (data_dir / "secrets.json").read_bytes())
        finally:
            engine.close()


if __name__ == "__main__":
    unittest.main()
