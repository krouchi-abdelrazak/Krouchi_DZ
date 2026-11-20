"""اختبارات الواجهة المشتركة (v3.4): API واحدة لكل البوتات تُدخَل مرة
واحدة — الحسم عند الإرسال، الهجرة الكسولة، التوجيه المدمج، ولقطة
إنشاء البوت. بلا شبكة وبلا شاشة: مزوّدات وهمية مسجِّلة عبر المصنع.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz import i18n
from krouchi_dz.broker import PendingApprovals
from krouchi_dz.engine import (
    ORIENTATION_AR,
    ORIENTATION_EN,
    ChatEngine,
    orientation_text,
)
from krouchi_dz.providers import TOOL_NAMES, ChatResult, MockProvider
from krouchi_dz.server import CompanionServer


def provider_entry(name):
    return {
        "name": name,
        "kind": "openai",
        "base_url": f"https://{name}.example/v1",
        "secret_ref": name,
        "default_model": "",
    }


class SharedFixture(unittest.TestCase):
    """يبني محرّكاً بملف مزوّدين مكتوب صراحة في مجلد مؤقت."""

    def make_engine(self, provider_names, provider_factory=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        providers_path = Path(self.tmp.name) / "providers.json"
        providers_path.write_text(
            json.dumps(
                {"providers": [provider_entry(n) for n in provider_names]}
            ),
            encoding="utf-8",
        )
        engine = ChatEngine(
            Path(self.tmp.name) / "data",
            providers_path=providers_path,
            provider_factory=provider_factory,
        )
        self.addCleanup(engine.close)
        return engine

    def set_activity(self, engine, bot_id, conv_at=None, message_at=None):
        """يثبّت أزمنة نشاط بوت (محادثة/رسالة) بقيم حتمية للهجرة."""
        db = engine.db
        conv_id = db.get_or_create_conversation(bot_id)
        if conv_at is not None:
            db.conn.execute(
                "UPDATE conversations SET created_at = ? WHERE id = ?",
                (conv_at, conv_id),
            )
        if message_at is not None:
            msg_id = db.add_message(conv_id, "user", "نشاط")
            db.conn.execute(
                "UPDATE messages SET created_at = ? WHERE id = ?",
                (message_at, msg_id),
            )
        db.conn.commit()


# ======================================================================
# الحسم عند الإرسال: الواجهة المشتركة وحدها
# ======================================================================
class TestSharedResolution(SharedFixture):
    def make_recording_engine(self):
        self.mocks = {}
        self.factory_calls = []

        def factory(cfg, key):
            self.factory_calls.append(cfg.name)
            return self.mocks.setdefault(cfg.name, MockProvider())

        return self.make_engine(["prov-a", "prov-b"], provider_factory=factory)

    def test_send_uses_shared_not_bot_binding(self):
        engine = self.make_recording_engine()
        bot_id = engine.create_bot("بوت", "prov-b", model="model-B")
        engine.set_shared_api("prov-a", "model-A")
        reply = engine.send_message(bot_id, "سلام")
        self.assertEqual(reply, "ردّ تجريبي")
        # المصنع بُني لمزوّد الواجهة المشتركة فقط، والنموذج الذي
        # وصله هو نموذجها — لا أثر لربط البوت المخزَّن إطلاقاً.
        self.assertEqual(self.factory_calls, ["prov-a"])
        self.assertEqual(self.mocks["prov-a"].calls[0]["model"], "model-A")
        self.assertNotIn("prov-b", self.mocks)

    def test_set_shared_api_unknown_provider_rejected(self):
        engine = self.make_recording_engine()
        with self.assertRaises(ValueError):
            engine.set_shared_api("nope", "m")

    def test_set_and_get_roundtrip(self):
        engine = self.make_recording_engine()
        engine.set_shared_api("prov-b", "model-B")
        self.assertEqual(engine.get_shared_api(), ("prov-b", "model-B"))
        self.assertEqual(engine.db.get_setting("shared_provider"), "prov-b")
        self.assertEqual(engine.db.get_setting("shared_model"), "model-B")


class TestSharedErrors(SharedFixture):
    def test_no_providers_send_raises_not_set(self):
        engine = self.make_engine([])
        bot_id = engine.db.create_bot("بوت", "ghost")
        self.assertIsNone(engine.get_shared_api())
        with self.assertRaises(ValueError) as ctx:
            engine.send_message(bot_id, "سلام")
        self.assertIn("لم تُضبط الواجهة المشتركة بعد", str(ctx.exception))

    def test_shared_provider_without_model_raises_pick_model(self):
        mock = MockProvider()
        engine = self.make_engine(
            ["prov-a"], provider_factory=lambda cfg, key: mock
        )
        bot_id = engine.create_bot("بوت", "prov-a", model="model-B")
        engine.set_shared_api("prov-a", "")
        with self.assertRaises(ValueError) as ctx:
            engine.send_message(bot_id, "سلام")
        self.assertIn("اختر نموذجاً للواجهة المشتركة أولاً", str(ctx.exception))
        self.assertEqual(mock.calls, [])  # لم يصل شيء للمزوّد


# ======================================================================
# الهجرة الكسولة إلى الواجهة المشتركة
# ======================================================================
class TestMigration(SharedFixture):
    def test_first_keyed_provider_and_latest_active_bot_model(self):
        engine = self.make_engine(["nokey", "keyed2", "keyed3"])
        engine.set_api_key("keyed2", "k2")
        engine.set_api_key("keyed3", "k3")
        old_bot = engine.create_bot("قديم", "keyed2", model="m-old")
        new_bot = engine.create_bot("جديد", "keyed2", model="m-new")
        other_bot = engine.create_bot("آخر", "keyed3", model="m-other")
        empty_bot = engine.create_bot("فارغ", "keyed2", model="")
        self.set_activity(engine, old_bot, conv_at="2026-02-01T00:00:00+00:00")
        self.set_activity(
            engine,
            new_bot,
            conv_at="2026-01-01T00:00:00+00:00",
            message_at="2026-03-01T00:00:00+00:00",
        )
        # نشاط أحدث لكن على مزوّد غير مختار / وبلا نموذج: يُتجاهَلان.
        self.set_activity(engine, other_bot, conv_at="2026-04-01T00:00:00+00:00")
        self.set_activity(engine, empty_bot, conv_at="2026-05-01T00:00:00+00:00")

        self.assertEqual(engine.get_shared_api(), ("keyed2", "m-new"))
        self.assertEqual(engine.db.get_setting("shared_provider"), "keyed2")
        self.assertEqual(engine.db.get_setting("shared_model"), "m-new")
        # bot_last_activity: الأحدث بين المحادثة والرسائل.
        activity = engine.db.bot_last_activity()
        self.assertEqual(activity[new_bot], "2026-03-01T00:00:00+00:00")
        self.assertEqual(activity[old_bot], "2026-02-01T00:00:00+00:00")

    def test_no_key_anywhere_picks_first_provider(self):
        engine = self.make_engine(["p1", "p2"])
        engine.create_bot("بوت", "p2", model="m2")
        # لا مفتاح لأي مزوّد: الأول بترتيب القاموس، ونموذجه من بوتاته
        # فقط — بوت p2 لا يُحتسَب.
        self.assertEqual(engine.get_shared_api(), ("p1", ""))

    def test_no_qualifying_bot_leaves_model_empty_but_persists_provider(self):
        engine = self.make_engine(["p1"])
        engine.create_bot("بوت", "p1", model="")
        self.assertEqual(engine.get_shared_api(), ("p1", ""))
        self.assertEqual(engine.db.get_setting("shared_provider"), "p1")
        self.assertEqual(engine.db.get_setting("shared_model", ""), "")

    def test_no_providers_leaves_everything_unset(self):
        engine = self.make_engine([])
        self.assertIsNone(engine.get_shared_api())
        engine.ensure_shared_api()
        self.assertEqual(engine.db.get_setting("shared_provider", ""), "")

    def test_migration_is_idempotent(self):
        engine = self.make_engine(["p1", "p2"])
        engine.set_api_key("p2", "k")
        bot_id = engine.create_bot("بوت", "p2", model="m-first")
        self.set_activity(engine, bot_id, conv_at="2026-01-01T00:00:00+00:00")
        self.assertEqual(engine.get_shared_api(), ("p2", "m-first"))
        # نشاط/نموذج أحدث يظهران بعد الهجرة: لا إعادة حساب أبداً.
        later = engine.create_bot("لاحق", "p2", model="m-later")
        self.set_activity(engine, later, conv_at="2027-01-01T00:00:00+00:00")
        engine.ensure_shared_api()
        self.assertEqual(engine.get_shared_api(), ("p2", "m-first"))

    def test_user_set_shared_api_is_never_overwritten(self):
        engine = self.make_engine(["nokey", "keyed2"])
        engine.set_api_key("keyed2", "k2")
        engine.create_bot("بوت", "keyed2", model="m-bot")
        engine.set_shared_api("nokey", "user-model")
        engine.ensure_shared_api()
        self.assertEqual(engine.get_shared_api(), ("nokey", "user-model"))

    def test_migration_persists_across_engine_instances(self):
        engine = self.make_engine(["nokey", "keyed2"])
        engine.set_api_key("keyed2", "k2")
        bot_id = engine.create_bot("بوت", "keyed2", model="m-persist")
        self.set_activity(engine, bot_id, conv_at="2026-01-01T00:00:00+00:00")
        self.assertEqual(engine.get_shared_api(), ("keyed2", "m-persist"))
        data_dir, providers_path = engine.data_dir, engine.providers_path
        engine.close()

        engine2 = ChatEngine(data_dir, providers_path=providers_path)
        self.addCleanup(engine2.close)
        self.assertEqual(engine2.get_shared_api(), ("keyed2", "m-persist"))


# ======================================================================
# إنشاء البوت: لقطة المزوّد المشترك عند غياب الاسم الصريح
# ======================================================================
class TestCreateBotSnapshot(SharedFixture):
    def test_no_provider_stores_shared_snapshot(self):
        engine = self.make_engine(["prov-a", "prov-b"])
        engine.set_shared_api("prov-b", "m")
        bot_id = engine.create_bot("جديد")
        self.assertEqual(engine.db.get_bot(bot_id)["provider_name"], "prov-b")

    def test_no_provider_and_no_providers_stores_empty(self):
        engine = self.make_engine([])
        bot_id = engine.create_bot("جديد")
        self.assertEqual(engine.db.get_bot(bot_id)["provider_name"], "")

    def test_explicit_provider_still_validated(self):
        engine = self.make_engine(["prov-a"])
        with self.assertRaises(ValueError):
            engine.create_bot("بوت", "nope")
        bot_id = engine.create_bot("بوت", "prov-a")
        self.assertEqual(engine.db.get_bot(bot_id)["provider_name"], "prov-a")


# ======================================================================
# التوجيه المدمج لبوتات الحاسوب
# ======================================================================
class TestOrientation(SharedFixture):
    def setUp(self):
        super().setUp()
        i18n.set_lang("ar")
        self.addCleanup(i18n.set_lang, "ar")

    def make_sending_engine(self, mock):
        engine = self.make_engine(
            ["prov-a"], provider_factory=lambda cfg, key: mock
        )
        engine.set_shared_api("prov-a", "m")
        return engine

    def test_orientation_names_every_real_tool(self):
        for name in TOOL_NAMES:
            self.assertIn(name, ORIENTATION_AR)
            self.assertIn(name, ORIENTATION_EN)
        self.assertIn("بوت حاسوب", ORIENTATION_AR)
        self.assertIn("computer bot", ORIENTATION_EN)
        self.assertEqual(orientation_text("ar"), ORIENTATION_AR)
        self.assertEqual(orientation_text("en"), ORIENTATION_EN)

    def test_orientation_precedes_bot_prompt(self):
        mock = MockProvider([ChatResult(text="ردّ")])
        engine = self.make_sending_engine(mock)
        bot_id = engine.create_bot(
            "بوت", "prov-a", system_prompt="تعليمات خاصة"
        )
        engine.send_message(bot_id, "سلام")
        sent = mock.calls[0]["messages"]
        self.assertEqual(sent[0]["role"], "system")
        content = sent[0]["content"]
        self.assertTrue(content.startswith(ORIENTATION_AR))
        self.assertIn("open_target", content)
        self.assertTrue(content.endswith("\n\nتعليمات خاصة"))
        self.assertLess(
            content.index(ORIENTATION_AR), content.index("تعليمات خاصة")
        )

    def test_orientation_alone_when_no_bot_prompt(self):
        mock = MockProvider([ChatResult(text="ردّ")])
        engine = self.make_sending_engine(mock)
        bot_id = engine.create_bot("بوت", "prov-a")
        engine.send_message(bot_id, "سلام")
        sent = mock.calls[0]["messages"]
        self.assertEqual(sent[0]["content"], ORIENTATION_AR)

    def test_english_orientation_when_ui_lang_en(self):
        i18n.set_lang("en")
        mock = MockProvider([ChatResult(text="reply")])
        engine = self.make_sending_engine(mock)
        bot_id = engine.create_bot("بوت", "prov-a", system_prompt="Be brief")
        engine.send_message(bot_id, "hi")
        content = mock.calls[0]["messages"][0]["content"]
        self.assertTrue(content.startswith(ORIENTATION_EN))
        self.assertIn("window_action", content)
        self.assertTrue(content.endswith("\n\nBe brief"))


# ======================================================================
# حمولة /api/bots: تراجع إلى قيم البوت عند غياب الواجهة المشتركة
# ======================================================================
class TestServerPayloadFallback(SharedFixture):
    def test_falls_back_to_stored_values_without_providers(self):
        engine = self.make_engine([])
        bot_id = engine.db.create_bot("شبح", "ghost", model="gm")
        server = CompanionServer(
            engine_call=lambda fn: fn(engine),
            registry=PendingApprovals(),
            token="test-token-1234567890",
            port=0,
        )
        bots = server.list_bots()
        self.assertEqual(len(bots), 1)
        self.assertEqual(bots[0]["id"], bot_id)
        self.assertEqual(bots[0]["provider"], "ghost")
        self.assertEqual(bots[0]["model"], "gm")


if __name__ == "__main__":
    unittest.main()
