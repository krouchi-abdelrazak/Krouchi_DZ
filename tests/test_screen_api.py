"""اختبارات الشاشة الحية والإدخال عن بُعد (الإصدار 3.3): بثّ MJPEG
وحقن إدخال عبر HTTP حقيقي، بمصدر شاشة ومغرَز إدخال وهميين محقونين
(FakeScreenSource/FakeInputSink) فلا تُلتقط شاشة ولا يُحقن إدخال
حقيقي في الاختبار أبداً.

تُغطّى: مصادقة البث (الترويسة أو ?token= — الاستثناء الموثّق
الوحيد لعنصر <img>) وحصر الاستثناء بهذا المسار، بوّابة
control_enabled، 501 للمنصّات غير المدعومة، تحويل إحداثيات
الفأرة النسبية إلى بكسلات حجم المصدر، أحداث المفاتيح والنص،
وعدّاد screen_viewers في /api/status.

الإصدار 3.3.2 — إطار الشاشة المفرد /api/screen/frame: حمولة
JPEG صالحة الفكّ مع العرض/الارتفاع من المصدر، مصادقة الترويسة
حصراً (لا استثناء ?token= هنا)، بوّابة control_enabled، 501
لغير المدعوم، وعدّ طلب الإطار مشاهدةً حديثة في screen_viewers.
"""

import base64
import http.client
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_server import TOKEN, ServerFixture  # noqa: E402

from krouchi_dz import remote  # noqa: E402


class AdvancingScreenSource(remote.FakeScreenSource):
    """مصدر وهمي يتقدّم عدّاده مع كل التقاط: إطارات متغيّرة دائماً،
    فلا يحذفها مُزيل التكرار في iter_mjpeg_frames ويستمرّ البث."""

    def grab_jpeg(self, max_width=1280, quality=60):
        self.advance()
        return super().grab_jpeg(max_width=max_width, quality=quality)


class ScreenFixture(ServerFixture):
    """خادم بمصدر شاشة وهمي (800×600) ومغرَز إدخال مسجِّل لنداءاته."""

    def make_screen_server(self, **kwargs):
        self.screen_source = AdvancingScreenSource(800, 600)
        self.input_sink = remote.FakeInputSink()
        kwargs.setdefault("screen_source", self.screen_source)
        kwargs.setdefault("input_sink", self.input_sink)
        return self.make_server(**kwargs)

    def open_stream(self, path, token=TOKEN, header=True):
        """يفتح اتصال بثّ ويعيد (الاتصال، الردّ) دون قراءة الجسم.

        الإغلاق النظيف يبدأ بالردّ ثم الاتصال: ردّ http.client يشارك
        المقبس نفسه عبر قارئه المُخزّن، فإغلاق الاتصال وحده لا يرسل
        FIN فعلياً ما دام الردّ مفتوحاً — والخادم لا يكتشف الرحيل.
        """
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.port, timeout=15
        )
        headers = {}
        if header and token is not None:
            headers["X-Krouchi-Token"] = token
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()

        def _close():
            resp.close()
            conn.close()

        self.addCleanup(_close)
        return conn, resp

    def read_until(self, resp, needle, timeout=5.0):
        """يقرأ من البثّ حتى يظهر needle أو تنتهي المهلة؛ يعيد ما قُرئ."""
        data = b""
        deadline = time.monotonic() + timeout
        while needle not in data and time.monotonic() < deadline:
            chunk = resp.read1(65536)
            if not chunk:
                break
            data += chunk
        return data


class TestStreamAuth(ScreenFixture):
    def test_stream_without_token_is_401(self):
        self.make_screen_server()
        status, data = self.request("GET", "/api/screen/stream", token=None)
        self.assertEqual(status, 401)
        self.assertIn("error", data)

    def test_stream_wrong_query_token_is_401(self):
        self.make_screen_server()
        status, _ = self.request(
            "GET", "/api/screen/stream?token=not-the-token", token=None
        )
        self.assertEqual(status, 401)

    def test_query_token_does_not_auth_other_endpoints(self):
        self.make_screen_server()
        status, _ = self.request("GET", f"/api/ping?token={TOKEN}", token=None)
        self.assertEqual(status, 401)
        status, _ = self.request(
            "POST",
            f"/api/input?token={TOKEN}",
            body={"type": "key", "key": "enter"},
            token=None,
        )
        self.assertEqual(status, 401)
        self.assertEqual(self.input_sink.calls, [])


class TestScreenStream(ScreenFixture):
    def test_stream_query_token_serves_multipart(self):
        self.make_screen_server()
        conn, resp = self.open_stream(
            f"/api/screen/stream?token={TOKEN}&fps=20", header=False
        )
        self.assertEqual(resp.status, 200)
        content_type = resp.getheader("Content-Type")
        self.assertIn("multipart/x-mixed-replace", content_type)
        self.assertIn("boundary=krouchiframe", content_type)
        data = self.read_until(resp, b"Content-Type: image/jpeg")
        self.assertIn(b"--krouchiframe", data)
        self.assertIn(b"Content-Type: image/jpeg", data)
        resp.close()
        conn.close()

    def test_stream_header_token_also_works(self):
        self.make_screen_server()
        conn, resp = self.open_stream("/api/screen/stream?fps=20")
        self.assertEqual(resp.status, 200)
        data = self.read_until(resp, b"--krouchiframe")
        self.assertIn(b"--krouchiframe", data)
        resp.close()
        conn.close()

    def test_stream_control_disabled_is_403(self):
        self.make_screen_server()
        self.server.engine_call(
            lambda e: e.db.set_setting("control_enabled", "false")
        )
        status, data = self.request("GET", "/api/screen/stream")
        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "control disabled")

    def test_stream_unsupported_source_is_501(self):
        self.make_server(
            screen_source=remote.UnsupportedScreenSource(),
            input_sink=remote.NullInputSink(),
        )
        status, data = self.request("GET", "/api/screen/stream")
        self.assertEqual(status, 501)
        self.assertIn("error", data)


class TestScreenFrame(ScreenFixture):
    """الإصدار 3.3.2: /api/screen/frame — إطار JPEG واحد في JSON."""

    def test_frame_returns_decodable_jpeg_with_size(self):
        self.make_screen_server()
        status, data = self.request("GET", "/api/screen/frame")
        self.assertEqual(status, 200)
        self.assertEqual(data["format"], "jpeg")
        self.assertEqual(data["width"], 800)
        self.assertEqual(data["height"], 600)
        raw = base64.b64decode(data["image_b64"], validate=True)
        self.assertTrue(raw.startswith(b"\xff\xd8"))  # JPEG SOI
        self.assertTrue(raw.endswith(b"\xff\xd9"))    # JPEG EOI
        self.assertIn(b"FAKEJPEG", raw)

    def test_frame_params_reach_source(self):
        self.make_screen_server()
        status, data = self.request("GET", "/api/screen/frame?w=640&q=45")
        self.assertEqual(status, 200)
        raw = base64.b64decode(data["image_b64"])
        self.assertIn(b"mw640-q45", raw)

    def test_frame_without_token_is_401(self):
        self.make_screen_server()
        status, data = self.request("GET", "/api/screen/frame", token=None)
        self.assertEqual(status, 401)
        self.assertIn("error", data)

    def test_frame_query_token_is_not_accepted(self):
        # استثناء ?token= خاصّ بمسار البثّ وحده (عنصر <img>)؛ الإطار
        # المفرد يمرّ بقناة الطلبات العادية فمصادقة الترويسة إلزامية
        self.make_screen_server()
        status, _ = self.request(
            "GET", f"/api/screen/frame?token={TOKEN}", token=None
        )
        self.assertEqual(status, 401)

    def test_frame_control_disabled_is_403(self):
        self.make_screen_server()
        self.server.engine_call(
            lambda e: e.db.set_setting("control_enabled", "false")
        )
        status, data = self.request("GET", "/api/screen/frame")
        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "control disabled")

    def test_frame_unsupported_source_is_501(self):
        self.make_server(
            screen_source=remote.UnsupportedScreenSource(),
            input_sink=remote.NullInputSink(),
        )
        status, data = self.request("GET", "/api/screen/frame")
        self.assertEqual(status, 501)
        self.assertIn("error", data)

    def test_frame_counts_as_recent_viewer_in_status(self):
        self.make_screen_server()
        status, data = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["screen_viewers"], 0)
        status, _ = self.request("GET", "/api/screen/frame")
        self.assertEqual(status, 200)
        status, data = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["screen_viewers"], 1)


class TestInputApi(ScreenFixture):
    def test_mouse_down_dispatches_pixel_coords(self):
        self.make_screen_server()
        status, data = self.request(
            "POST",
            "/api/input",
            body={"type": "mouse_down", "x": 0.5, "y": 0.5},
        )
        self.assertEqual(status, 200)
        self.assertEqual(data, {"ok": True, "type": "mouse_down"})
        # 0.5×0.5 من مصدر 800×600 = البكسل (400, 300)، زرّ أيسر مضغوط
        self.assertEqual(
            self.input_sink.calls,
            [("mouse_button", 400, 300, "left", True)],
        )

    def test_mouse_move_and_wheel_dispatch(self):
        self.make_screen_server()
        status, _ = self.request(
            "POST",
            "/api/input",
            body={"type": "mouse_move", "x": 0.0, "y": 1.0},
        )
        self.assertEqual(status, 200)
        status, _ = self.request(
            "POST",
            "/api/input",
            body={"type": "wheel", "x": 1.0, "y": 0.0, "delta": -2},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            self.input_sink.calls,
            [("mouse_move", 0, 599), ("wheel", 799, 0, -2)],
        )

    def test_key_and_text_dispatch(self):
        self.make_screen_server()
        status, data = self.request(
            "POST", "/api/input", body={"type": "key", "key": "ctrl+c"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data, {"ok": True, "type": "key"})
        status, data = self.request(
            "POST", "/api/input", body={"type": "text", "text": "مرحبا"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data, {"ok": True, "type": "text"})
        self.assertEqual(
            self.input_sink.calls, [("key", "ctrl+c"), ("text", "مرحبا")]
        )

    def test_invalid_event_is_400(self):
        self.make_screen_server()
        status, data = self.request(
            "POST", "/api/input", body={"type": "bogus"}
        )
        self.assertEqual(status, 400)
        self.assertIn("error", data)
        status, data = self.request(
            "POST",
            "/api/input",
            body={"type": "mouse_down", "x": "شرق", "y": 0.5},
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.input_sink.calls, [])

    def test_input_unsupported_source_is_501(self):
        self.make_server(
            screen_source=remote.UnsupportedScreenSource(),
            input_sink=remote.NullInputSink(),
        )
        status, data = self.request(
            "POST", "/api/input", body={"type": "key", "key": "enter"}
        )
        self.assertEqual(status, 501)
        self.assertIn("error", data)

    def test_input_unsupported_sink_is_501(self):
        self.make_server(
            screen_source=remote.FakeScreenSource(),
            input_sink=remote.NullInputSink(),
        )
        status, data = self.request(
            "POST", "/api/input", body={"type": "key", "key": "enter"}
        )
        self.assertEqual(status, 501)
        self.assertIn("error", data)


class TestScreenViewers(ScreenFixture):
    def test_status_reports_screen_viewers(self):
        self.make_screen_server()
        status, data = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertIsInstance(data["screen_viewers"], int)
        self.assertEqual(data["screen_viewers"], 0)

        conn, resp = self.open_stream("/api/screen/stream?fps=20")
        self.assertEqual(resp.status, 200)
        self.read_until(resp, b"--krouchiframe")
        status, data = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["screen_viewers"], 1)

        resp.close()
        conn.close()
        viewers = None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            _, data = self.request("GET", "/api/status")
            viewers = data["screen_viewers"]
            if viewers == 0:
                break
            time.sleep(0.05)
        self.assertEqual(viewers, 0)


if __name__ == "__main__":
    unittest.main()
