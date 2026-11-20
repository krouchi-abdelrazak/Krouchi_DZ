"""اختبارات إدخال API واكتشاف المزوّدين — نقل GET وهمي، بلا شبكة."""

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock as umock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz.discovery import (
    ERR_AUTH,
    DiscoveryError,
    _urllib_get_transport,
    classify_kind,
    discover_models,
    normalize_base_url,
)
from krouchi_dz.engine import ChatEngine
from krouchi_dz.providers import ChatResult, MockProvider

PLANTED_KEY = "SK-DISCOVERY-TEST-KEY-1122334455"


class FakeGetTransport:
    """يلتقط طلبات GET ويعيد ردّاً مُعدّاً أو يرفع خطأ اكتشاف مُعدّاً."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def __call__(self, url, headers, timeout=30.0):
        self.calls.append({"url": url, "headers": dict(headers)})
        if self.error is not None:
            raise self.error
        return self.response


class TestNormalizeUrl(unittest.TestCase):
    def test_openai_variants_collapse_to_one_canonical(self):
        expected = "https://api.deepseek.com/v1"
        for raw in (
            "https://api.deepseek.com",
            "https://api.deepseek.com/",
            "https://api.deepseek.com/v1",
            "https://api.deepseek.com/v1/",
            "api.deepseek.com",
            "https://api.deepseek.com/v1/chat/completions",
            "  https://api.deepseek.com/v1/models  ",
        ):
            self.assertEqual(normalize_base_url(raw, "openai"), expected, raw)

    def test_existing_seed_bases_unchanged(self):
        self.assertEqual(
            normalize_base_url("https://openrouter.ai/api/v1/", "openai"),
            "https://openrouter.ai/api/v1",
        )
        self.assertEqual(
            normalize_base_url("https://api.groq.com/openai", "openai"),
            "https://api.groq.com/openai/v1",
        )
        self.assertEqual(
            normalize_base_url("https://api.z.ai/api/paas/v4/", "openai"),
            "https://api.z.ai/api/paas/v4",
        )

    def test_gemini_gets_v1beta(self):
        self.assertEqual(
            normalize_base_url("https://generativelanguage.googleapis.com", "gemini"),
            "https://generativelanguage.googleapis.com/v1beta",
        )
        self.assertEqual(
            normalize_base_url(
                "https://generativelanguage.googleapis.com/v1beta/", "gemini"
            ),
            "https://generativelanguage.googleapis.com/v1beta",
        )

    def test_bad_urls_rejected(self):
        for raw in ("", "   ", "http://", "ftp://example.com/v1", "://"):
            with self.assertRaises(ValueError, msg=raw):
                normalize_base_url(raw, "openai")


class TestClassifyKind(unittest.TestCase):
    def test_gemini_host_detected(self):
        self.assertEqual(
            classify_kind("https://generativelanguage.googleapis.com/v1beta"),
            "gemini",
        )

    def test_other_hosts_are_openai(self):
        self.assertEqual(classify_kind("https://api.deepseek.com"), "openai")
        self.assertEqual(classify_kind("http://localhost:11434/v1"), "openai")

    def test_manual_override_wins(self):
        self.assertEqual(
            classify_kind("https://generativelanguage.googleapis.com", "openai"),
            "openai",
        )
        self.assertEqual(classify_kind("https://api.example.com", "gemini"), "gemini")
        with self.assertRaises(ValueError):
            classify_kind("https://api.example.com", "bogus")


class _FakeHTTPResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestDefaultGetTransport(unittest.TestCase):
    """النقل الافتراضي الحقيقي مع urlopen مُستبدَل — بلا شبكة فعلية."""

    def _patch(self, side_effect=None, body=b"{}"):
        if side_effect is not None:
            return umock.patch(
                "krouchi_dz.discovery.urllib.request.urlopen",
                side_effect=side_effect,
            )
        return umock.patch(
            "krouchi_dz.discovery.urllib.request.urlopen",
            return_value=_FakeHTTPResponse(body),
        )

    def test_success_parses_json(self):
        with self._patch(body=b'{"data": []}'):
            data = _urllib_get_transport("https://x.example/v1/models", {})
        self.assertEqual(data, {"data": []})

    def test_non_json_is_distinct_error(self):
        with self._patch(body=b"<html>not an api</html>"):
            with self.assertRaises(DiscoveryError) as ctx:
                _urllib_get_transport("https://x.example/", {})
        self.assertEqual(ctx.exception.kind, "not_json")

    def test_401_and_403_are_auth_errors(self):
        for code in (401, 403):
            err = urllib.error.HTTPError(
                "https://x.example/", code, "no", hdrs=None, fp=io.BytesIO(b"")
            )
            with self._patch(side_effect=err):
                with self.assertRaises(DiscoveryError) as ctx:
                    _urllib_get_transport("https://x.example/", {})
            self.assertEqual(ctx.exception.kind, "auth")
            self.assertEqual(ctx.exception.message, ERR_AUTH)

    def test_500_is_http_error(self):
        err = urllib.error.HTTPError(
            "https://x.example/", 500, "boom", hdrs=None, fp=io.BytesIO(b"")
        )
        with self._patch(side_effect=err):
            with self.assertRaises(DiscoveryError) as ctx:
                _urllib_get_transport("https://x.example/", {})
        self.assertEqual(ctx.exception.kind, "http")
        self.assertIn("500", ctx.exception.message)

    def test_unreachable_host(self):
        with self._patch(side_effect=urllib.error.URLError("no route")):
            with self.assertRaises(DiscoveryError) as ctx:
                _urllib_get_transport("https://x.example/", {})
        self.assertEqual(ctx.exception.kind, "unreachable")


class TestDiscoverModelsParsing(unittest.TestCase):
    def test_openai_shape(self):
        transport = FakeGetTransport(
            {"data": [{"id": "a-model"}, {"id": "b-model"}, {"id": "a-model"}]}
        )
        models = discover_models(
            "https://api.example.com/v1", "KEY", "openai", get_transport=transport
        )
        self.assertEqual(models, ["a-model", "b-model"])  # بلا تكرار
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://api.example.com/v1/models")
        self.assertEqual(call["headers"]["Authorization"], "Bearer KEY")

    def test_gemini_shape_strips_prefix(self):
        transport = FakeGetTransport(
            {
                "models": [
                    {"name": "models/gemini-2.0-flash"},
                    {"name": "models/gemini-1.5-pro"},
                ]
            }
        )
        models = discover_models(
            "https://generativelanguage.googleapis.com/v1beta",
            "GKEY",
            "gemini",
            get_transport=transport,
        )
        self.assertEqual(models, ["gemini-2.0-flash", "gemini-1.5-pro"])
        self.assertEqual(
            transport.calls[0]["headers"]["x-goog-api-key"], "GKEY"
        )

    def test_bad_shape_and_empty_are_distinct(self):
        with self.assertRaises(DiscoveryError) as ctx:
            discover_models(
                "https://api.example.com/v1", "K", "openai",
                get_transport=FakeGetTransport({"unexpected": True}),
            )
        self.assertEqual(ctx.exception.kind, "bad_shape")
        with self.assertRaises(DiscoveryError) as ctx:
            discover_models(
                "https://api.example.com/v1", "K", "openai",
                get_transport=FakeGetTransport({"data": []}),
            )
        self.assertEqual(ctx.exception.kind, "empty")


class DiscoveryFixture(unittest.TestCase):
    """محرّك في مجلد مؤقت: محادثة بمزوّد وهمي، واكتشاف بنقل GET وهمي."""

    def make_engine(self, get_transport=None, mock_provider=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.mock_provider = (
            mock_provider if mock_provider is not None else MockProvider()
        )
        engine = ChatEngine(
            Path(self.tmp.name) / "data",
            provider_factory=lambda cfg, key: self.mock_provider,
            get_transport=get_transport,
        )
        self.addCleanup(engine.close)
        self.addCleanup(self.tmp.cleanup)
        return engine


class TestAddApi(DiscoveryFixture):
    def test_discovers_openai_provider_end_to_end(self):
        transport = FakeGetTransport(
            {"data": [{"id": "model-one"}, {"id": "model-two"}]}
        )
        engine = self.make_engine(get_transport=transport)
        result = engine.add_api("https://api.example.com/v1/", PLANTED_KEY)
        self.assertTrue(result.ok)
        self.assertEqual(result.provider, "example")  # مشتق من الخادم
        self.assertEqual(result.models, ["model-one", "model-two"])
        self.assertTrue(result.verified)
        self.assertEqual(result.base_url, "https://api.example.com/v1")
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://api.example.com/v1/models")
        self.assertEqual(call["headers"]["Authorization"], f"Bearer {PLANTED_KEY}")
        cfg = engine.providers["example"]
        self.assertTrue(cfg.verified)
        self.assertEqual(cfg.default_model, "model-one")
        # المفتاح في الأسرار فقط: لا في ملف المزوّدين ولا في القاعدة
        data_dir = engine.data_dir
        self.assertIn(
            PLANTED_KEY.encode(), (data_dir / "secrets.json").read_bytes()
        )
        self.assertNotIn(
            PLANTED_KEY.encode(), (data_dir / "providers.json").read_bytes()
        )
        self.assertNotIn(
            PLANTED_KEY.encode(), (data_dir / "krouchi_dz.db").read_bytes()
        )

    def test_discovers_gemini_by_host(self):
        transport = FakeGetTransport(
            {"models": [{"name": "models/gemini-2.0-flash"}]}
        )
        engine = self.make_engine(get_transport=transport)
        result = engine.add_api(
            "https://generativelanguage.googleapis.com", "GKEY-9"
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.models, ["gemini-2.0-flash"])
        self.assertEqual(
            transport.calls[0]["url"],
            "https://generativelanguage.googleapis.com/v1beta/models",
        )
        cfg = engine.providers[result.provider]
        self.assertEqual(cfg.kind, "gemini")

    def test_explicit_name_and_kind_override(self):
        transport = FakeGetTransport({"models": [{"name": "models/gx-1"}]})
        engine = self.make_engine(get_transport=transport)
        result = engine.add_api(
            "https://api.example.com/v1",
            "K",
            name="My Provider",
            kind="gemini",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.provider, "my-provider")
        self.assertEqual(result.models, ["gx-1"])
        self.assertEqual(
            transport.calls[0]["headers"]["x-goog-api-key"], "K"
        )

    def test_auth_failure_saves_unverified_with_clear_error(self):
        transport = FakeGetTransport(error=DiscoveryError("auth", ERR_AUTH))
        engine = self.make_engine(get_transport=transport)
        result = engine.add_api("https://api.example.com/v1", "BAD-KEY")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_kind, "auth")
        self.assertIn("مفتاح", result.error)
        self.assertFalse(result.verified)
        # المزوّد محفوظ لكن مُعلَّم غير مُتحقَّق — لا يُقدَّم على أنه يعمل
        cfg = engine.providers["example"]
        self.assertFalse(cfg.verified)
        self.assertEqual(cfg.models, [])
        self.assertTrue(engine.provider_configured("example"))

    def test_unreachable_and_empty_and_bad_shape(self):
        cases = [
            (DiscoveryError("unreachable", "تعذّر الوصول"), "unreachable"),
            (None, "empty"),
            (None, "bad_shape"),
        ]
        responses = {
            "empty": {"data": []},
            "bad_shape": {"weird": 1},
        }
        for error, kind in cases:
            transport = FakeGetTransport(
                response=responses.get(kind), error=error
            )
            engine = self.make_engine(get_transport=transport)
            result = engine.add_api("https://api.example.com/v1", "K")
            self.assertFalse(result.ok, kind)
            self.assertEqual(result.error_kind, kind)
            self.assertFalse(engine.providers["example"].verified)

    def test_bad_url_saves_nothing(self):
        engine = self.make_engine(get_transport=FakeGetTransport({"data": []}))
        before = set(engine.providers)
        result = engine.add_api("http://", "K")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_kind, "bad_url")
        self.assertTrue(result.error)
        self.assertEqual(set(engine.providers), before)

    def test_models_cached_within_ttl(self):
        transport = FakeGetTransport({"data": [{"id": "m1"}]})
        engine = self.make_engine(get_transport=transport)
        first = engine.add_api("https://api.example.com/v1", "K")
        self.assertTrue(first.ok)
        self.assertEqual(len(transport.calls), 1)
        cached = engine.fetch_models("example")
        self.assertTrue(cached.ok)
        self.assertTrue(cached.from_cache)
        self.assertEqual(cached.models, ["m1"])
        self.assertEqual(len(transport.calls), 1)  # لم تُلمس الشبكة
        fresh = engine.fetch_models("example", force=True)
        self.assertTrue(fresh.ok)
        self.assertFalse(fresh.from_cache)
        self.assertEqual(len(transport.calls), 2)

    def test_readding_same_url_updates_key_no_duplicate(self):
        transport = FakeGetTransport({"data": [{"id": "m1"}]})
        engine = self.make_engine(get_transport=transport)
        engine.add_api("https://api.example.com/v1", "KEY-OLD")
        result = engine.add_api("https://api.example.com", "KEY-NEW")
        self.assertEqual(result.provider, "example")
        self.assertEqual(engine.secrets.get("example"), "KEY-NEW")
        self.assertEqual(
            transport.calls[-1]["headers"]["Authorization"], "Bearer KEY-NEW"
        )
        names = [n for n in engine.providers if n.startswith("example")]
        self.assertEqual(names, ["example"])

    def test_name_collision_gets_suffix(self):
        transport = FakeGetTransport({"data": [{"id": "m1"}]})
        engine = self.make_engine(get_transport=transport)
        first = engine.add_api("https://api.example.com/v1", "K1")
        second = engine.add_api("https://example.com/v1", "K2")
        self.assertEqual(first.provider, "example")
        self.assertEqual(second.provider, "example-2")

    def test_custom_provider_survives_restart(self):
        transport = FakeGetTransport({"data": [{"id": "m1"}]})
        engine = self.make_engine(get_transport=transport)
        result = engine.add_api("https://api.example.com/v1", "K")
        data_dir = engine.data_dir
        engine.close()

        def forbidden_transport(url, headers, timeout=30.0):
            raise AssertionError("لا شبكة مع كاش حديث")

        engine2 = ChatEngine(
            data_dir,
            provider_factory=lambda cfg, key: MockProvider(),
            get_transport=forbidden_transport,
        )
        self.addCleanup(engine2.close)
        self.assertIn("example", engine2.providers)
        self.assertTrue(engine2.providers["example"].verified)
        cached = engine2.fetch_models("example")
        self.assertTrue(cached.ok)
        self.assertTrue(cached.from_cache)
        self.assertEqual(cached.models, ["m1"])
        self.assertTrue(result.ok)

    def test_chat_works_on_discovered_provider(self):
        mock_provider = MockProvider([ChatResult(text="ردّ من مزوّد مكتشَف")])
        transport = FakeGetTransport(
            {"data": [{"id": "disc-model-1"}, {"id": "disc-model-2"}]}
        )
        engine = self.make_engine(
            get_transport=transport, mock_provider=mock_provider
        )
        result = engine.add_api("https://api.example.com/v1", "K")
        self.assertTrue(result.ok)
        bot_id = engine.create_bot(
            "بوت مكتشَف", result.provider, model=result.models[1]
        )
        # تحويل v3.4 (الواجهة المشتركة): الإرسال يستعمل الواجهة
        # المشتركة وحدها — تُضبَط هنا على المزوّد المكتشَف ونموذجه
        # الثاني، فيصل للمزوّد النموذج نفسه كما كان قبل التحويل.
        engine.set_shared_api(result.provider, result.models[1])
        reply = engine.send_message(bot_id, "سلام")
        self.assertEqual(reply, "ردّ من مزوّد مكتشَف")
        # النموذج المختار من القائمة المكتشفة هو ما وصل للمزوّد فعلاً
        self.assertEqual(mock_provider.calls[0]["model"], "disc-model-2")

    def test_register_and_fetch_alias(self):
        transport = FakeGetTransport({"data": [{"id": "m1"}]})
        engine = self.make_engine(get_transport=transport)
        result = engine.register_and_fetch("https://api.example.com/v1", "K")
        self.assertTrue(result.ok)
        self.assertEqual(result.models, ["m1"])


if __name__ == "__main__":
    unittest.main()
