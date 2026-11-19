"""Tests for krouchi_dz.remote (v3.3 remote-desktop core).

Runs on Linux: Windows backends must refuse cleanly (Arabic RuntimeError)
and the module must import without touching any Windows DLL.
"""

import sys
import unittest

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from krouchi_dz import remote
from krouchi_dz.remote import (
    FakeInputSink,
    FakeScreenSource,
    NullInputSink,
    UnsupportedScreenSource,
    create_input_sink,
    create_screen_source,
    dispatch_input,
    iter_mjpeg_frames,
    mjpeg_part,
    norm_to_pixel,
    validate_input_event,
)


class TestNormToPixel(unittest.TestCase):
    def test_corners(self):
        self.assertEqual(norm_to_pixel(0, 0, 800, 600), (0, 0))
        self.assertEqual(norm_to_pixel(1, 1, 800, 600), (799, 599))
        self.assertEqual(norm_to_pixel(0, 1, 800, 600), (0, 599))
        self.assertEqual(norm_to_pixel(1, 0, 800, 600), (799, 0))

    def test_middle(self):
        self.assertEqual(norm_to_pixel(0.5, 0.5, 800, 600), (400, 300))
        self.assertEqual(norm_to_pixel(0.25, 0.75, 800, 600), (200, 450))

    def test_clamping(self):
        self.assertEqual(norm_to_pixel(-0.5, -3, 800, 600), (0, 0))
        self.assertEqual(norm_to_pixel(1.5, 99, 800, 600), (799, 599))
        self.assertEqual(norm_to_pixel(2, -1, 100, 100), (99, 0))

    def test_int_inputs(self):
        self.assertEqual(norm_to_pixel(0, 1, 640, 480), (0, 479))

    def test_bad_size(self):
        with self.assertRaises(ValueError):
            norm_to_pixel(0.5, 0.5, 0, 600)
        with self.assertRaises(ValueError):
            norm_to_pixel(0.5, 0.5, 800, -1)

    def test_bad_coords(self):
        with self.assertRaises(ValueError):
            norm_to_pixel("x", 0.5, 800, 600)
        with self.assertRaises(ValueError):
            norm_to_pixel(float("nan"), 0.5, 800, 600)


class TestValidateInputEvent(unittest.TestCase):
    # -- accepted ------------------------------------------------------
    def test_mouse_move(self):
        ev = validate_input_event({"type": "mouse_move", "x": 0.5, "y": 0.25})
        self.assertEqual(ev, {"type": "mouse_move", "x": 0.5, "y": 0.25})

    def test_mouse_down_default_button(self):
        ev = validate_input_event({"type": "mouse_down", "x": 0, "y": 1})
        self.assertEqual(ev["button"], "left")

    def test_mouse_up_button_case_insensitive(self):
        ev = validate_input_event(
            {"type": "mouse_up", "x": 0.1, "y": 0.2, "button": "RIGHT"})
        self.assertEqual(ev["button"], "right")

    def test_wheel_delta_coerced_and_clamped(self):
        ev = validate_input_event({"type": "wheel", "x": 0, "y": 0, "delta": 99})
        self.assertEqual(ev["delta"], 5)
        ev = validate_input_event(
            {"type": "wheel", "x": 0, "y": 0, "delta": -99})
        self.assertEqual(ev["delta"], -5)
        ev = validate_input_event(
            {"type": "wheel", "x": 0, "y": 0, "delta": "3"})
        self.assertEqual(ev["delta"], 3)
        ev = validate_input_event(
            {"type": "wheel", "x": 0, "y": 0, "delta": 2.9})
        self.assertEqual(ev["delta"], 2)

    def test_named_keys(self):
        for name in ("enter", "esc", "tab", "backspace", "delete", "insert",
                     "up", "down", "left", "right", "home", "end",
                     "pageup", "pagedown", "space", "win",
                     "f1", "f6", "f12"):
            ev = validate_input_event({"type": "key", "key": name})
            self.assertEqual(ev["key"], name)

    def test_key_case_normalized(self):
        ev = validate_input_event({"type": "key", "key": "ENTER"})
        self.assertEqual(ev["key"], "enter")

    def test_single_char_key(self):
        ev = validate_input_event({"type": "key", "key": "a"})
        self.assertEqual(ev["key"], "a")

    def test_combos(self):
        cases = {
            "ctrl+c": "ctrl+c",
            "CTRL+C": "ctrl+c",
            "Alt+Tab": "alt+tab",
            "ctrl+shift+esc": "ctrl+shift+esc",
            "ctrl+alt+delete": "ctrl+alt+delete",
            "win+r": "win+r",
            "shift+f5": "shift+f5",
        }
        for raw, expected in cases.items():
            ev = validate_input_event({"type": "key", "key": raw})
            self.assertEqual(ev["key"], expected, raw)

    def test_text(self):
        ev = validate_input_event({"type": "text", "text": "مرحبا بالعالم"})
        self.assertEqual(ev["text"], "مرحبا بالعالم")
        ev = validate_input_event({"type": "text", "text": "x" * 2000})
        self.assertEqual(len(ev["text"]), 2000)

    def test_input_dict_not_mutated(self):
        original = {"type": "mouse_down", "x": 0.5, "y": 0.5}
        validate_input_event(original)
        self.assertNotIn("button", original)

    # -- rejected ------------------------------------------------------
    def assertBad(self, ev):
        with self.assertRaises(ValueError):
            validate_input_event(ev)

    def test_reject_non_dict_and_unknown_type(self):
        self.assertBad(None)
        self.assertBad("mouse_move")
        self.assertBad({})
        self.assertBad({"type": "scroll"})
        self.assertBad({"type": "MOUSE_MOVE", "x": 0, "y": 0})

    def test_reject_bad_coords(self):
        self.assertBad({"type": "mouse_move", "y": 0.5})
        self.assertBad({"type": "mouse_move", "x": "0.5", "y": 0.5})
        self.assertBad({"type": "mouse_move", "x": True, "y": 0.5})
        self.assertBad({"type": "mouse_move", "x": float("inf"), "y": 0})

    def test_reject_bad_button(self):
        self.assertBad({"type": "mouse_down", "x": 0, "y": 0,
                        "button": "fourth"})
        self.assertBad({"type": "mouse_down", "x": 0, "y": 0, "button": 1})
        self.assertBad({"type": "mouse_up", "x": 0, "y": 0, "button": ""})

    def test_reject_bad_wheel(self):
        self.assertBad({"type": "wheel", "x": 0, "y": 0})
        self.assertBad({"type": "wheel", "x": 0, "y": 0, "delta": 0})
        self.assertBad({"type": "wheel", "x": 0, "y": 0, "delta": "abc"})
        self.assertBad({"type": "wheel", "x": 0, "y": 0, "delta": True})
        self.assertBad({"type": "wheel", "x": 0, "y": 0, "delta": 0.4})

    def test_reject_bad_keys(self):
        for bad in ("", "banana", "f13", "f0", "ctrl", "shift", "ctrl+",
                    "+c", "ctrl++c", "ctrl+banana", "ctrl+ab", "meta+c",
                    "ctrl+ctrl+c", "ctrl+shift", "alt+ctrl", None, 42):
            self.assertBad({"type": "key", "key": bad})

    def test_reject_bad_text(self):
        self.assertBad({"type": "text", "text": ""})
        self.assertBad({"type": "text", "text": None})
        self.assertBad({"type": "text", "text": 123})
        self.assertBad({"type": "text", "text": "x" * 2001})

    def test_errors_are_arabic(self):
        try:
            validate_input_event({"type": "nope"})
        except ValueError as exc:
            self.assertTrue(any("؀" <= ch <= "ۿ" for ch in str(exc)))
        else:
            self.fail("expected ValueError")


class TestDispatchInput(unittest.TestCase):
    SIZE = (800, 600)

    def setUp(self):
        self.sink = FakeInputSink()

    def test_mouse_move_pixels(self):
        result = dispatch_input(
            self.sink, self.SIZE, {"type": "mouse_move", "x": 0.5, "y": 0.5})
        self.assertEqual(result, {"ok": True, "type": "mouse_move"})
        self.assertEqual(self.sink.calls, [("mouse_move", 400, 300)])

    def test_mouse_down_up(self):
        dispatch_input(self.sink, self.SIZE,
                       {"type": "mouse_down", "x": 1, "y": 1,
                        "button": "right"})
        dispatch_input(self.sink, self.SIZE,
                       {"type": "mouse_up", "x": 0, "y": 0})
        self.assertEqual(self.sink.calls, [
            ("mouse_button", 799, 599, "right", True),
            ("mouse_button", 0, 0, "left", False),
        ])

    def test_wheel(self):
        dispatch_input(self.sink, self.SIZE,
                       {"type": "wheel", "x": 0.25, "y": 0.75, "delta": -2})
        self.assertEqual(self.sink.calls, [("wheel", 200, 450, -2)])

    def test_key_and_text_need_no_size(self):
        dispatch_input(self.sink, None, {"type": "key", "key": "CTRL+C"})
        dispatch_input(self.sink, None, {"type": "text", "text": "سلام"})
        self.assertEqual(self.sink.calls,
                         [("key", "ctrl+c"), ("text", "سلام")])

    def test_invalid_event_reaches_no_sink(self):
        with self.assertRaises(ValueError):
            dispatch_input(self.sink, self.SIZE, {"type": "bogus"})
        self.assertEqual(self.sink.calls, [])

    def test_mouse_without_size_rejected(self):
        with self.assertRaises(ValueError):
            dispatch_input(self.sink, None,
                           {"type": "mouse_move", "x": 0, "y": 0})


class ScriptedFakeSource(FakeScreenSource):
    """FakeScreenSource whose counter follows a script, one step per grab."""

    def __init__(self, script, width=800, height=600):
        super().__init__(width, height)
        self._script = list(script)
        self._idx = 0

    def grab_jpeg(self, max_width=1280, quality=60):
        if self._idx < len(self._script):
            self.counter = self._script[self._idx]
            self._idx += 1
        return super().grab_jpeg(max_width=max_width, quality=quality)


class TestMjpeg(unittest.TestCase):
    def test_part_structure(self):
        frame = b"\xff\xd8abc\xff\xd9"
        part = mjpeg_part(frame)
        self.assertTrue(part.startswith(b"--krouchiframe\r\n"))
        self.assertIn(b"Content-Type: image/jpeg\r\n", part)
        self.assertIn(b"Content-Length: 7\r\n", part)
        self.assertTrue(part.endswith(frame + b"\r\n"))

    def test_part_custom_boundary(self):
        part = mjpeg_part(b"xy", boundary=b"zz")
        self.assertTrue(part.startswith(b"--zz\r\n"))
        self.assertIn(b"Content-Length: 2\r\n", part)

    def test_fake_source_deterministic(self):
        src = FakeScreenSource(320, 240)
        self.assertEqual(src.size(), (320, 240))
        a = src.grab_jpeg()
        self.assertEqual(a, src.grab_jpeg())  # unchanged counter
        src.advance()
        self.assertNotEqual(a, src.grab_jpeg())

    def test_iter_distinct_frames(self):
        src = ScriptedFakeSource([0, 1, 2])
        frames = list(iter_mjpeg_frames(src, max_frames=3))
        self.assertEqual(len(frames), 3)
        self.assertEqual(len(set(frames)), 3)

    def test_iter_dedupes_unchanged(self):
        src = ScriptedFakeSource([0, 0, 0, 1, 1, 2])
        frames = list(iter_mjpeg_frames(src, max_frames=3))
        self.assertEqual(len(frames), 3)
        self.assertEqual(len(set(frames)), 3)

    def test_iter_respects_max_frames(self):
        src = ScriptedFakeSource([0, 1, 2, 3, 4, 5])
        frames = list(iter_mjpeg_frames(src, max_frames=2))
        self.assertEqual(len(frames), 2)

    def test_iter_first_frame_always_yielded(self):
        src = FakeScreenSource()
        frames = list(iter_mjpeg_frames(src, max_frames=1))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0], src.grab_jpeg())

    def test_iter_propagates_source_errors(self):
        class Boom:
            def grab_jpeg(self, max_width=1280, quality=60):
                raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            list(iter_mjpeg_frames(Boom(), max_frames=1))


class TestPlatformFactories(unittest.TestCase):
    def test_module_imported(self):
        self.assertTrue(hasattr(remote, "WindowsScreenSource"))
        self.assertTrue(hasattr(remote, "WindowsInputSink"))

    @unittest.skipIf(sys.platform == "win32", "Linux-only expectations")
    def test_screen_source_unsupported_on_linux(self):
        src = create_screen_source()
        self.assertIsInstance(src, UnsupportedScreenSource)
        with self.assertRaises(RuntimeError):
            src.size()
        with self.assertRaises(RuntimeError):
            src.grab_jpeg()

    @unittest.skipIf(sys.platform == "win32", "Linux-only expectations")
    def test_input_sink_null_on_linux(self):
        sink = create_input_sink()
        self.assertIsInstance(sink, NullInputSink)
        with self.assertRaises(RuntimeError):
            sink.mouse_move(0, 0)
        with self.assertRaises(RuntimeError):
            sink.mouse_button(0, 0, "left", True)
        with self.assertRaises(RuntimeError):
            sink.wheel(0, 0, 1)
        with self.assertRaises(RuntimeError):
            sink.key("enter")
        with self.assertRaises(RuntimeError):
            sink.text("x")

    @unittest.skipIf(sys.platform == "win32", "Linux-only expectations")
    def test_windows_classes_refuse_construction_on_linux(self):
        with self.assertRaises(RuntimeError):
            remote.WindowsScreenSource()
        with self.assertRaises(RuntimeError):
            remote.WindowsInputSink()

    @unittest.skipIf(sys.platform == "win32", "Linux-only expectations")
    def test_factory_errors_are_arabic(self):
        sink = create_input_sink()
        try:
            sink.key("enter")
        except RuntimeError as exc:
            self.assertTrue(any("؀" <= ch <= "ۿ" for ch in str(exc)))
        else:
            self.fail("expected RuntimeError")


if __name__ == "__main__":
    unittest.main()
