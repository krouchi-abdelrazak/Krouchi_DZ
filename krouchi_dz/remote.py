"""Remote desktop core for Krouchi_DZ v3.3 (screen streaming + input injection).

Python standard library ONLY.

Design rules:
- This module imports cleanly on any platform (including Linux): every piece
  of Windows ``ctypes`` code lives inside methods/classes that only run on
  win32.  ``WindowsScreenSource`` / ``WindowsInputSink`` raise ``RuntimeError``
  (Arabic message) at construction time on non-Windows platforms.
- Coordinates exchanged with the phone are *normalized* (0..1) so phone and
  PC resolutions never need to match; ``norm_to_pixel`` converts them to PC
  pixel indices.
- ``FakeScreenSource`` / ``FakeInputSink`` are deterministic test doubles used
  by the unit tests and by any dev harness.
"""

import ctypes
import math
import sys

__all__ = [
    "norm_to_pixel",
    "validate_input_event",
    "ScreenSource",
    "FakeScreenSource",
    "WindowsScreenSource",
    "UnsupportedScreenSource",
    "create_screen_source",
    "InputSink",
    "FakeInputSink",
    "WindowsInputSink",
    "NullInputSink",
    "create_input_sink",
    "dispatch_input",
    "mjpeg_part",
    "iter_mjpeg_frames",
    "DEFAULT_BOUNDARY",
]

DEFAULT_BOUNDARY = b"krouchiframe"

_BUTTONS = ("left", "right", "middle")
_MODIFIERS = ("ctrl", "alt", "shift", "win")
_NAMED_KEYS = (
    "enter", "esc", "tab", "backspace", "delete", "insert",
    "up", "down", "left", "right", "home", "end",
    "pageup", "pagedown", "space", "win",
) + tuple("f%d" % i for i in range(1, 13))
_NAMED_KEY_SET = frozenset(_NAMED_KEYS)
_MOUSE_TYPES = ("mouse_move", "mouse_down", "mouse_up", "wheel")
_ALL_TYPES = _MOUSE_TYPES + ("key", "text")
_MAX_TEXT_LEN = 2000


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------

def norm_to_pixel(x, y, width, height):
    """Map normalized coords (0..1, clamped) to pixel indices.

    Returns ``(px, py)`` with ``0 <= px < width`` and ``0 <= py < height``
    (for positive width/height).  (0, 0) is the top-left corner and
    (1, 1) is the bottom-right pixel.
    """
    if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
        raise ValueError("عرض الشاشة غير صالح")
    if not isinstance(height, int) or isinstance(height, bool) or height <= 0:
        raise ValueError("ارتفاع الشاشة غير صالح")
    try:
        fx = float(x)
        fy = float(y)
    except (TypeError, ValueError):
        raise ValueError("إحداثيات غير صالحة")
    if not (math.isfinite(fx) and math.isfinite(fy)):
        raise ValueError("إحداثيات غير صالحة")
    cx = min(1.0, max(0.0, fx))
    cy = min(1.0, max(0.0, fy))
    px = int(cx * width)
    py = int(cy * height)
    if px >= width:
        px = width - 1
    if py >= height:
        py = height - 1
    return (px, py)


def _coord(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("إحداثي %s مفقود أو غير صالح" % name)
    fv = float(value)
    if not math.isfinite(fv):
        raise ValueError("إحداثي %s غير صالح" % name)
    return fv


def _validate_key_spec(raw):
    """Normalize a key spec or raise ValueError (Arabic)."""
    if not isinstance(raw, str):
        raise ValueError("المفتاح غير صالح")
    spec = raw.strip().lower()
    if not spec:
        raise ValueError("المفتاح فارغ")
    if "+" not in spec:
        if spec in _NAMED_KEY_SET:
            return spec
        if len(spec) == 1 and spec.isprintable():
            return spec
        raise ValueError("مفتاح غير معروف: %s" % raw)
    parts = [p.strip() for p in spec.split("+")]
    if len(parts) < 2 or any(not p for p in parts):
        raise ValueError("تركيبة مفاتيح غير صالحة: %s" % raw)
    mods, last = parts[:-1], parts[-1]
    seen = set()
    for mod in mods:
        if mod not in _MODIFIERS:
            raise ValueError("مفتاح تعديل غير معروف: %s" % mod)
        if mod in seen:
            raise ValueError("مفتاح تعديل مكرر: %s" % mod)
        seen.add(mod)
    if last in _MODIFIERS:
        raise ValueError("تركيبة مفاتيح غير صالحة: %s" % raw)
    if last in _NAMED_KEY_SET:
        return "+".join(parts)
    if len(last) == 1 and last.isprintable():
        return "+".join(parts)
    raise ValueError("مفتاح غير معروف: %s" % last)


def validate_input_event(ev):
    """Validate + normalize one input event dict.

    Returns a NEW normalized dict.  Raises ``ValueError`` with an Arabic
    message on any problem.
    """
    if not isinstance(ev, dict):
        raise ValueError("حدث إدخال غير صالح")
    etype = ev.get("type")
    if etype not in _ALL_TYPES:
        raise ValueError("نوع حدث غير معروف: %s" % (etype,))

    if etype in _MOUSE_TYPES:
        out = {
            "type": etype,
            "x": _coord(ev.get("x"), "x"),
            "y": _coord(ev.get("y"), "y"),
        }
        if etype in ("mouse_down", "mouse_up"):
            button = ev.get("button", "left")
            if not isinstance(button, str):
                raise ValueError("زر فأرة غير صالح")
            button = button.strip().lower()
            if button not in _BUTTONS:
                raise ValueError("زر فأرة غير معروف: %s" % button)
            out["button"] = button
        if etype == "wheel":
            raw_delta = ev.get("delta")
            if isinstance(raw_delta, bool):
                raise ValueError("قيمة تمرير غير صالحة")
            try:
                delta = int(raw_delta)
            except (TypeError, ValueError):
                raise ValueError("قيمة تمرير غير صالحة")
            # int() truncates floats; a fractional string like "2.5" already
            # raised above.  Clamp to [-5, 5]; zero is meaningless -> reject.
            delta = max(-5, min(5, delta))
            if delta == 0:
                raise ValueError("قيمة التمرير لا يمكن أن تكون صفراً")
            out["delta"] = delta
        return out

    if etype == "key":
        return {"type": "key", "key": _validate_key_spec(ev.get("key"))}

    # etype == "text"
    text = ev.get("text")
    if not isinstance(text, str) or not text:
        raise ValueError("النص فارغ أو غير صالح")
    if len(text) > _MAX_TEXT_LEN:
        raise ValueError("النص أطول من الحد المسموح (2000 حرف)")
    return {"type": "text", "text": text}


# --------------------------------------------------------------------------
# Screen sources
# --------------------------------------------------------------------------

class ScreenSource:
    """Duck-typed protocol: size() -> (w, h); grab_jpeg(...) -> bytes."""

    def size(self):
        raise NotImplementedError

    def grab_jpeg(self, max_width=1280, quality=60):
        raise NotImplementedError


class FakeScreenSource(ScreenSource):
    """Deterministic fake frames for tests / dev harness.

    Frame bytes depend only on an internal counter; call :meth:`advance`
    to move to the next (different) frame.  Unchanged counter -> identical
    bytes (so MJPEG dedupe can be tested).
    """

    def __init__(self, width=800, height=600):
        self._width = int(width)
        self._height = int(height)
        self.counter = 0

    def advance(self):
        self.counter += 1
        return self.counter

    def size(self):
        return (self._width, self._height)

    def grab_jpeg(self, max_width=1280, quality=60):
        payload = "FAKEJPEG-%d-%dx%d-mw%d-q%d" % (
            self.counter, self._width, self._height, int(max_width),
            int(quality))
        return b"\xff\xd8" + payload.encode("ascii") + b"\xff\xd9"


class UnsupportedScreenSource(ScreenSource):
    """Placeholder for non-Windows platforms."""

    def size(self):
        raise RuntimeError("الشاشة غير مدعومة على هذا النظام")

    def grab_jpeg(self, max_width=1280, quality=60):
        raise RuntimeError("الشاشة غير مدعومة على هذا النظام")


# --- Windows GDI / GDI+ implementation (only ever runs on win32) ----------

class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _Guid(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid_from_string(text):
    # "{557CF401-1A04-11D3-9A73-0000F81EF32E}" style parsing, no uuid needed
    # for the byte layout (uuid would also work, this keeps it explicit).
    import uuid
    return _Guid.from_buffer_copy(uuid.UUID(text).bytes_le)


# JPEG encoder CLSID for GDI+.
_JPEG_ENCODER_CLSID = "{557CF401-1A04-11D3-9A73-0000F81EF32E}"


def _import_pillow():
    """(Image, ImageGrab) من Pillow إن توفّرت، وإلا None."""
    try:
        from PIL import Image, ImageGrab
    except Exception:
        return None
    return Image, ImageGrab


def _grab_screen(image_grab):
    """لقطة الشاشة كاملة عبر ImageGrab (كل الشاشات إن دعم الإصدار)."""
    try:
        return image_grab.grab(all_screens=True)
    except TypeError:
        return image_grab.grab()


class WindowsScreenSource(ScreenSource):
    """Real screen capture on Windows. Preferred path: Pillow's
    ImageGrab end-to-end (bundled with the Windows package). Fallback
    when Pillow is absent: GDI capture (ctypes) + GDI+ JPEG encode."""

    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    SRCCOPY = 0x00CC0020
    CAPTUREBLT = 0x40000000
    DIB_RGB_COLORS = 0
    BI_RGB = 0

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("مصدر شاشة ويندوز يعمل على ويندوز فقط")
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._vx = self._user32.GetSystemMetrics(self.SM_XVIRTUALSCREEN)
        self._vy = self._user32.GetSystemMetrics(self.SM_YVIRTUALSCREEN)
        self._vw = self._user32.GetSystemMetrics(self.SM_CXVIRTUALSCREEN)
        self._vh = self._user32.GetSystemMetrics(self.SM_CYVIRTUALSCREEN)
        if self._vw <= 0 or self._vh <= 0:  # fall back to primary screen
            self._vx, self._vy = 0, 0
            self._vw = self._user32.GetSystemMetrics(0)  # SM_CXSCREEN
            self._vh = self._user32.GetSystemMetrics(1)  # SM_CYSCREEN
        self._gdiplus = None
        self._gdiplus_token = None
        self._size_cache = None  # يُحسَب مرة واحدة في size()

    # -- geometry ------------------------------------------------------
    def size(self):
        if self._size_cache is None:
            self._size_cache = self._compute_size()
        return self._size_cache

    def _compute_size(self):
        # مع Pillow: مقاس اللقطة الفعلي من ImageGrab — هو ما ستعيده
        # grab_jpeg فعلاً، فيطابق إحداثيات النقر حجم الصورة المعروضة.
        pillow = _import_pillow()
        if pillow is not None:
            try:
                _image, image_grab = pillow
                width, height = _grab_screen(image_grab).size
                if width > 0 and height > 0:
                    return (int(width), int(height))
            except Exception:
                pass
        return (self._vw, self._vh)

    # -- raw capture ---------------------------------------------------
    def _capture_hbitmap(self, width, height):
        """BitBlt the virtual screen into a new HBITMAP of width x height.

        Returns (hbitmap, src_dc, mem_dc); caller must clean up with
        :meth:`_release_capture`.  When width/height differ from the
        virtual screen size, StretchBlt performs the downscale.
        """
        gdi32, user32 = self._gdi32, self._user32
        src_dc = user32.GetDC(0)
        if not src_dc:
            raise RuntimeError("تعذر الوصول إلى سطح المكتب")
        mem_dc = gdi32.CreateCompatibleDC(src_dc)
        hbitmap = gdi32.CreateCompatibleBitmap(src_dc, width, height)
        if not mem_dc or not hbitmap:
            if hbitmap:
                gdi32.DeleteObject(hbitmap)
            if mem_dc:
                gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(0, src_dc)
            raise RuntimeError("تعذر إنشاء صورة الشاشة")
        old = gdi32.SelectObject(mem_dc, hbitmap)
        try:
            if (width, height) == (self._vw, self._vh):
                ok = gdi32.BitBlt(
                    mem_dc, 0, 0, width, height, src_dc, self._vx, self._vy,
                    self.SRCCOPY | self.CAPTUREBLT)
            else:
                # HALFTONE gives a decent shrink; nearest-neighbour fallback
                # is acceptable per spec if the mode call is ignored.
                gdi32.SetStretchBltMode(mem_dc, 4)  # HALFTONE
                ok = gdi32.StretchBlt(
                    mem_dc, 0, 0, width, height, src_dc,
                    self._vx, self._vy, self._vw, self._vh,
                    self.SRCCOPY | self.CAPTUREBLT)
            if not ok:
                raise RuntimeError("تعذر التقاط الشاشة")
        except Exception:
            gdi32.SelectObject(mem_dc, old)
            raise
        gdi32.SelectObject(mem_dc, old)
        return hbitmap, src_dc, mem_dc

    def _release_capture(self, hbitmap, src_dc, mem_dc):
        if hbitmap:
            self._gdi32.DeleteObject(hbitmap)
        if mem_dc:
            self._gdi32.DeleteDC(mem_dc)
        if src_dc:
            self._user32.ReleaseDC(0, src_dc)

    # -- JPEG عبر GDI+ (المسار الاحتياطي عند غياب Pillow) ----------------
    def _ensure_gdiplus(self):
        if self._gdiplus is not None:
            return self._gdiplus
        gdiplus = ctypes.windll.gdiplus

        class _StartupInput(ctypes.Structure):
            _fields_ = [
                ("GdiplusVersion", ctypes.c_uint32),
                ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", ctypes.c_int),
                ("SuppressExternalCodecs", ctypes.c_int),
            ]

        token = ctypes.c_void_p()
        inp = _StartupInput(1, None, 0, 0)
        status = gdiplus.GdiplusStartup(
            ctypes.byref(token), ctypes.byref(inp), None)
        if status != 0:
            raise RuntimeError("تعذر تشغيل مكتبة الصور (GDI+)")
        self._gdiplus = gdiplus
        self._gdiplus_token = token
        return gdiplus

    def _encode_jpeg_gdiplus(self, hbitmap, quality):
        """Encode an HBITMAP as JPEG through GDI+ and an in-memory stream."""
        gdiplus = self._ensure_gdiplus()
        ole32 = ctypes.windll.ole32
        gp_bitmap = ctypes.c_void_p()
        status = gdiplus.GdipCreateBitmapFromHBITMAP(
            ctypes.c_void_p(hbitmap), None, ctypes.byref(gp_bitmap))
        if status != 0 or not gp_bitmap:
            raise RuntimeError("تعذر إنشاء صورة (GDI+)")
        stream = ctypes.c_void_p()
        try:
            hr = ole32.CreateStreamOnHGlobal(None, True, ctypes.byref(stream))
            if hr != 0 or not stream:
                raise RuntimeError("تعذر إنشاء تدفق الصورة")
            clsid = _guid_from_string(_JPEG_ENCODER_CLSID)
            status = gdiplus.GdipSaveImageToStream(
                gp_bitmap, stream, ctypes.byref(clsid), None)
            if status != 0:
                raise RuntimeError("تعذر حفظ الصورة (GDI+)")
            return self._read_stream_bytes(ole32, stream)
        finally:
            if stream:
                self._com_release(stream)
            gdiplus.GdipDisposeImage(gp_bitmap)

    @staticmethod
    def _com_release(ptr):
        vtable = ctypes.cast(
            ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p))
        release_type = ctypes.WINFUNCTYPE(
            ctypes.c_ulong, ctypes.c_void_p)
        release = release_type(vtable[2])
        release(ptr)

    def _read_stream_bytes(self, ole32, stream):
        """Read all bytes from an IStream created on an HGLOBAL."""
        kernel32 = ctypes.windll.kernel32
        hglobal = ctypes.c_void_p()
        hr = ole32.GetHGlobalFromStream(stream, ctypes.byref(hglobal))
        if hr == 0 and hglobal:
            size = kernel32.GlobalSize(hglobal)
            locked = kernel32.GlobalLock(hglobal)
            if locked and size:
                try:
                    return ctypes.string_at(locked, size)
                finally:
                    kernel32.GlobalUnlock(hglobal)
        # Fallback: Seek(0, STREAM_SEEK_SET) + Read loop via the vtable.
        vtable = ctypes.cast(
            ctypes.cast(stream, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p))
        seek_type = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.c_int64, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint64))
        seek = seek_type(vtable[5])
        new_pos = ctypes.c_uint64(0)
        if seek(stream, 0, 0, ctypes.byref(new_pos)) != 0:
            raise RuntimeError("تعذر قراءة تدفق الصورة")
        read_type = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong))
        read = read_type(vtable[3])
        chunks = []
        buf = ctypes.create_string_buffer(65536)
        while True:
            got = ctypes.c_ulong(0)
            hr = read(stream, buf, 65536, ctypes.byref(got))
            if hr != 0 or got.value == 0:
                break
            chunks.append(buf.raw[:got.value])
        data = b"".join(chunks)
        if not data:
            raise RuntimeError("تعذر قراءة تدفق الصورة")
        return data

    # -- public ----------------------------------------------------------
    def grab_jpeg(self, max_width=1280, quality=60):
        pillow = _import_pillow()
        if pillow is not None:
            # المسار المفضّل: Pillow/ImageGrab من الالتقاط إلى الترميز.
            return self._grab_jpeg_pillow(pillow, max_width, quality)
        # احتياطي بلا Pillow: التقاط GDI (مصغّراً بـStretchBlt عند
        # الحاجة) ثم ترميز GDI+.
        width, height = self._vw, self._vh
        if max_width and width > int(max_width):
            scale = float(max_width) / float(width)
            tw = int(max_width)
            th = max(1, int(round(height * scale)))
        else:
            tw, th = width, height
        hbitmap, src_dc, mem_dc = self._capture_hbitmap(tw, th)
        try:
            return self._encode_jpeg_gdiplus(hbitmap, quality)
        finally:
            self._release_capture(hbitmap, src_dc, mem_dc)

    def _grab_jpeg_pillow(self, pillow, max_width, quality):
        import io

        image_mod, image_grab = pillow
        img = _grab_screen(image_grab)
        if img.mode != "RGB":
            img = img.convert("RGB")
        width, height = img.size
        if max_width and width > int(max_width):
            scale = float(max_width) / float(width)
            img = img.resize(
                (int(max_width), max(1, int(round(height * scale)))),
                image_mod.LANCZOS,
            )
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=int(quality))
        return out.getvalue()


def create_screen_source():
    """WindowsScreenSource on win32, else UnsupportedScreenSource."""
    if sys.platform == "win32":
        return WindowsScreenSource()
    return UnsupportedScreenSource()


# --------------------------------------------------------------------------
# Input sinks
# --------------------------------------------------------------------------

class InputSink:
    """Duck-typed protocol for injected input (pixel coordinates)."""

    def mouse_move(self, px, py):
        raise NotImplementedError

    def mouse_button(self, px, py, button, down):
        raise NotImplementedError

    def wheel(self, px, py, delta):
        raise NotImplementedError

    def key(self, spec):
        raise NotImplementedError

    def text(self, s):
        raise NotImplementedError


class FakeInputSink(InputSink):
    """Records every call in ``.calls`` as tuples, for tests."""

    def __init__(self):
        self.calls = []

    def mouse_move(self, px, py):
        self.calls.append(("mouse_move", px, py))

    def mouse_button(self, px, py, button, down):
        self.calls.append(("mouse_button", px, py, button, bool(down)))

    def wheel(self, px, py, delta):
        self.calls.append(("wheel", px, py, delta))

    def key(self, spec):
        self.calls.append(("key", spec))

    def text(self, s):
        self.calls.append(("text", s))


class NullInputSink(InputSink):
    """Used on non-Windows platforms: every method raises RuntimeError."""

    _MSG = "حقن الإدخال غير مدعوم على هذا النظام"

    def mouse_move(self, px, py):
        raise RuntimeError(self._MSG)

    def mouse_button(self, px, py, button, down):
        raise RuntimeError(self._MSG)

    def wheel(self, px, py, delta):
        raise RuntimeError(self._MSG)

    def key(self, spec):
        raise RuntimeError(self._MSG)

    def text(self, s):
        raise RuntimeError(self._MSG)


# --- Windows SendInput implementation (only ever runs on win32) -----------

_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1
_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040
_MOUSEEVENTF_WHEEL = 0x0800
_MOUSEEVENTF_ABSOLUTE = 0x8000
_MOUSEEVENTF_VIRTUALDESK = 0x4000
_WHEEL_DELTA = 120
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004

_VK_NAMED = {
    "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "backspace": 0x08,
    "delete": 0x2E, "insert": 0x2D, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "space": 0x20, "win": 0x5B,
}
for _i in range(1, 13):
    _VK_NAMED["f%d" % _i] = 0x70 + (_i - 1)
_VK_MODIFIERS = {
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
}
_MOUSE_BUTTON_FLAGS = {
    "left": (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP),
    "right": (_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP),
    "middle": (_MOUSEEVENTF_MIDDLEDOWN, _MOUSEEVENTF_MIDDLEUP),
}


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _KeybdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_uint16),
        ("wScan", ctypes.c_uint16),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_uint32),
        ("wParamL", ctypes.c_uint16),
        ("wParamH", ctypes.c_uint16),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [
        ("mi", _MouseInput),
        ("ki", _KeybdInput),
        ("hi", _HardwareInput),
    ]


class _Input(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("union", _InputUnion),
    ]


def _vk_for_token(token):
    if token in _VK_NAMED:
        return _VK_NAMED[token]
    if len(token) == 1:
        ch = token
        if "a" <= ch <= "z":
            return ord(ch.upper())
        if "0" <= ch <= "9":
            return ord(ch)
        # Punctuation etc.: ask Windows for the virtual-key code.
        vk = ctypes.windll.user32.VkKeyScanW(ch)
        if vk != -1:
            return vk & 0xFF
    raise ValueError("مفتاح غير معروف: %s" % token)


class WindowsInputSink(InputSink):
    """Real input injection on Windows via SendInput (ctypes)."""

    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("حقن إدخال ويندوز يعمل على ويندوز فقط")
        self._user32 = ctypes.windll.user32
        self._vx = self._user32.GetSystemMetrics(self.SM_XVIRTUALSCREEN)
        self._vy = self._user32.GetSystemMetrics(self.SM_YVIRTUALSCREEN)
        self._vw = self._user32.GetSystemMetrics(self.SM_CXVIRTUALSCREEN)
        self._vh = self._user32.GetSystemMetrics(self.SM_CYVIRTUALSCREEN)
        if self._vw <= 0 or self._vh <= 0:
            self._vx, self._vy = 0, 0
            self._vw = self._user32.GetSystemMetrics(0)
            self._vh = self._user32.GetSystemMetrics(1)

    # -- low level -----------------------------------------------------
    def _send(self, inputs):
        arr = (_Input * len(inputs))(*inputs)
        sent = self._user32.SendInput(
            len(inputs), arr, ctypes.sizeof(_Input))
        if sent != len(inputs):
            raise RuntimeError("تعذر إرسال الإدخال إلى النظام")

    def _absolute(self, px, py):
        """Pixel (in virtual-screen coords) -> SendInput 0..65535 scale."""
        vw = max(1, self._vw - 1)
        vh = max(1, self._vh - 1)
        dx = int(round((int(px) - self._vx) * 65535.0 / vw))
        dy = int(round((int(py) - self._vy) * 65535.0 / vh))
        return (max(0, min(65535, dx)), max(0, min(65535, dy)))

    def _mouse_input(self, px, py, flags, data=0):
        dx, dy = self._absolute(px, py)
        inp = _Input()
        inp.type = _INPUT_MOUSE
        inp.union.mi = _MouseInput(
            dx, dy, ctypes.c_uint32(data & 0xFFFFFFFF).value,
            flags | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK,
            0, None)
        return inp

    def _key_input(self, vk, scan=0, flags=0):
        inp = _Input()
        inp.type = _INPUT_KEYBOARD
        inp.union.ki = _KeybdInput(vk, scan, flags, 0, None)
        return inp

    # -- protocol --------------------------------------------------------
    def mouse_move(self, px, py):
        self._send([self._mouse_input(px, py, _MOUSEEVENTF_MOVE)])

    def mouse_button(self, px, py, button, down):
        down_flag, up_flag = _MOUSE_BUTTON_FLAGS[button]
        self._send([self._mouse_input(
            px, py, down_flag if down else up_flag)])

    def wheel(self, px, py, delta):
        data = int(delta) * _WHEEL_DELTA
        # WHEEL data is a signed value carried in the unsigned field.
        self._send([self._mouse_input(
            px, py, _MOUSEEVENTF_WHEEL, data & 0xFFFFFFFF)])

    def key(self, spec):
        spec = _validate_key_spec(spec)
        if "+" in spec:
            parts = spec.split("+")
            mods, last = parts[:-1], parts[-1]
            vk_mods = [_VK_MODIFIERS[m] for m in mods]
            vk_main = _vk_for_token(last)
            seq = [self._key_input(vk) for vk in vk_mods]
            seq.append(self._key_input(vk_main))
            seq.append(self._key_input(vk_main, flags=_KEYEVENTF_KEYUP))
            for vk in reversed(vk_mods):
                seq.append(self._key_input(vk, flags=_KEYEVENTF_KEYUP))
            self._send(seq)
            return
        vk = _vk_for_token(spec)
        self._send([
            self._key_input(vk),
            self._key_input(vk, flags=_KEYEVENTF_KEYUP),
        ])

    def text(self, s):
        if not isinstance(s, str) or not s:
            raise ValueError("النص فارغ أو غير صالح")
        data = s.encode("utf-16-le")
        units = [
            data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)
        ]
        inputs = []
        for unit in units:  # each UTF-16 code unit (surrogates included)
            inputs.append(self._key_input(
                0, scan=unit, flags=_KEYEVENTF_UNICODE))
            inputs.append(self._key_input(
                0, scan=unit,
                flags=_KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP))
        # SendInput in chunks so very long texts stay within sane limits.
        chunk = 200
        for i in range(0, len(inputs), chunk):
            self._send(inputs[i:i + chunk])


def create_input_sink():
    """WindowsInputSink on win32, else NullInputSink (raises on use)."""
    if sys.platform == "win32":
        return WindowsInputSink()
    return NullInputSink()


# --------------------------------------------------------------------------
# Dispatch + MJPEG framing
# --------------------------------------------------------------------------

def dispatch_input(sink, source_size, event):
    """Validate ``event``, convert coords via ``source_size``, drive ``sink``.

    Returns ``{"ok": True, "type": <event type>}``.
    """
    ev = validate_input_event(event)
    etype = ev["type"]
    if etype in _MOUSE_TYPES:
        if not source_size:
            raise ValueError("حجم الشاشة غير معروف")
        width, height = source_size
        px, py = norm_to_pixel(ev["x"], ev["y"], width, height)
        if etype == "mouse_move":
            sink.mouse_move(px, py)
        elif etype == "mouse_down":
            sink.mouse_button(px, py, ev["button"], True)
        elif etype == "mouse_up":
            sink.mouse_button(px, py, ev["button"], False)
        elif etype == "wheel":
            sink.wheel(px, py, ev["delta"])
    elif etype == "key":
        sink.key(ev["key"])
    elif etype == "text":
        sink.text(ev["text"])
    return {"ok": True, "type": etype}


def mjpeg_part(frame_bytes, boundary=DEFAULT_BOUNDARY):
    """One complete multipart/x-mixed-replace part for ``frame_bytes``."""
    if isinstance(boundary, str):
        boundary = boundary.encode("ascii")
    frame = bytes(frame_bytes)
    header = (
        b"--" + boundary + b"\r\n"
        b"Content-Type: image/jpeg\r\n"
        b"Content-Length: " + str(len(frame)).encode("ascii") + b"\r\n"
        b"\r\n"
    )
    return header + frame + b"\r\n"


def iter_mjpeg_frames(source, max_width=1280, quality=60, max_frames=None):
    """Yield JPEG frame bytes from ``source``, skipping unchanged frames.

    The first frame is always yielded.  A frame whose bytes equal the
    previously yielded frame is skipped.  ``max_frames`` (if given) caps
    the number of *yielded* frames.  Errors from the source propagate
    (RuntimeError included).
    """
    produced = 0
    last = None
    while True:
        if max_frames is not None and produced >= int(max_frames):
            return
        frame = source.grab_jpeg(max_width=max_width, quality=quality)
        frame = bytes(frame)
        if last is not None and frame == last:
            continue
        last = frame
        produced += 1
        yield frame
