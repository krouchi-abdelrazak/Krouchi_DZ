"""تحكّم الهاتف بالحاسوب في Krouchi_DZ — مساعدات المنصّة (المكتبة القياسية فقط).

كل ما يلمس نظام التشغيل فعلاً يعيش هنا خلف دوال صغيرة قابلة للاستبدال
بالحقن من الخادم (power_executor / printer_lister / print_executor /
clipboard_getter / clipboard_setter في CompanionServer) — فالاختبارات
لا تطبع ورقة ولا تلمس حافظة حقيقية أبداً، والإنتاج يستعمل الافتراضي
هنا: PowerShell على ويندوز، وأدوات lpstat/lp والملفات /proc على لينكس.

جذر التحكّم: مجلد المستخدم الرئيسي. كل مسارات الملفات تُحَلّ وتُفحَص
ضدّه — ما خرج عنه مرفوض (403) قبل أي لمس للقرص.
"""

from __future__ import annotations

import csv
import ctypes
import io
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

IS_WINDOWS = os.name == "nt"

# ويندوز فقط: منع وميض نافذة وحدة تحكّم زرقاء عند تشغيل العمليات
# المساعدة (PowerShell خاصة). الثابت غير موجود على الأنظمة الأخرى
# فيعيد getattr صفراً — وهو القيمة الافتراضية أصلاً فلا أثر هناك.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

FILE_MAX_BYTES = 5 * 1024 * 1024        # حدّ تنزيل ملف واحد (GET /api/file)
UPLOAD_MAX_BYTES = 25 * 1024 * 1024     # حدّ رفع ملف واحد (POST /api/upload)
RUN_TIMEOUT = 120.0                     # مهلة أمر /api/run (ثوانٍ)
OUTPUT_TAIL = 4000                      # آخر حروف تُعاد من مخرجات الأمر


# ======================================================================
# حالة النظام
# ======================================================================
def _uptime_seconds() -> int | None:
    """مدة تشغيل النظام بالثواني — بأفضل جهد بحسب المنصّة."""
    try:
        if IS_WINDOWS:
            import ctypes

            return int(ctypes.windll.kernel32.GetTickCount64() // 1000)
        uptime = Path("/proc/uptime").read_text(encoding="utf-8").split()[0]
        return int(float(uptime))
    except Exception:
        return None


def _ram_mb() -> int | None:
    """حجم الذاكرة الكلي بالميغابايت — بأفضل جهد، وإلا None."""
    try:
        if IS_WINDOWS:
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _MemStatus()
            status.dwLength = ctypes.sizeof(_MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys // (1024 * 1024))
            return None
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


def system_status(version: str) -> dict:
    """حالة الحاسوب كما تخرج في GET /api/status."""
    home = Path.home()
    try:
        usage = shutil.disk_usage(home)
        disk = {
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
        }
    except OSError:
        disk = {"total_gb": 0.0, "free_gb": 0.0}
    return {
        "app": "Krouchi_DZ",
        "version": version,
        "os": platform.system(),
        "platform": platform.platform(),
        "hostname": socket.gethostname(),
        "home": str(home),
        "uptime_s": _uptime_seconds(),
        "disk": disk,
        "ram_mb": _ram_mb(),
    }


# ======================================================================
# المسارات داخل جذر التحكّم
# ======================================================================
def control_root() -> Path:
    """جذر التحكّم الافتراضي: مجلد المستخدم الرئيسي، محلولاً."""
    return Path.home().resolve()


def resolve_within_root(root: Path, raw: str | None) -> Path | None:
    """يحلّ مساراً مطلوباً ويتحقق من بقائه داخل الجذر؛ None إن خرج.

    المسار المطلق يُستعمل كما هو، والنسبي يُبنى على الجذر، والفارغ
    يعني الجذر نفسه. resolve() يطوّع «..» والروابط الرمزية قبل الفحص.
    """
    if raw is None or str(raw).strip() == "":
        return root
    candidate = Path(str(raw))
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if resolved == root or root in resolved.parents:
        return resolved
    return None


def list_dir(root: Path, target: Path) -> dict:
    """قائمة مجلد: المجلدات أولاً ثم الملفات، وكلٌّ مرتب بالاسم."""
    entries = []
    with os.scandir(target) as scan:
        for entry in scan:
            try:
                is_dir = entry.is_dir()
            except OSError:
                is_dir = False
            size = None
            if not is_dir:
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = None
            entries.append(
                {
                    "name": entry.name,
                    "kind": "dir" if is_dir else "file",
                    "size": size,
                }
            )
    entries.sort(key=lambda e: (0 if e["kind"] == "dir" else 1, e["name"].lower()))
    return {
        "path": str(target),
        "parent": None if target == root else str(target.parent),
        "entries": entries,
    }


# ======================================================================
# لقطة الشاشة والطاقة — التنفيذ الفعلي (قابل للاستبدال في الاختبارات)
# ======================================================================
def take_screenshot() -> tuple[bytes, str] | None:
    """لقطة PNG من سطح المكتب، أو None إن تعذّرت على هذه المنصّة.

    ويندوز: Pillow/ImageGrab أولاً — التقاط مباشر إلى PNG في الذاكرة
    (المكتبة تأتي مع حزمة ويندوز أصلاً لمصدر الشاشة الحيّ). غيابها أو
    فشل الالتقاط بها يهبط إلى الاحتياطي: PowerShell + System.Drawing
    إلى ملف مؤقت. غير ويندوز: None (يردّ الخادم 501) — لا أدوات
    خارجية تُفترَض.
    """
    if not IS_WINDOWS:
        return None
    try:
        from PIL import ImageGrab

        image = ImageGrab.grab()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue(), "png"
    except Exception:
        pass  # لا Pillow أو فشل الالتقاط بها: جرّب مسار PowerShell
    tmp = Path(tempfile.gettempdir()) / "krouchi_screenshot.png"
    script = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
        "$bmp=New-Object System.Drawing.Bitmap($b.Width, $b.Height);"
        "$g=[System.Drawing.Graphics]::FromImage($bmp);"
        "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
        f"$bmp.Save('{tmp}',[System.Drawing.Imaging.ImageFormat]::Png);"
        "$g.Dispose();$bmp.Dispose()"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=20, creationflags=_NO_WINDOW,
        )
        if proc.returncode != 0 or not tmp.is_file():
            return None
        data = tmp.read_bytes()
        tmp.unlink(missing_ok=True)
        return data, "png"
    except Exception:
        return None


POWER_ACTIONS = ("shutdown", "restart", "lock", "sleep", "logoff")
# أفعال الطاقة المجدولة بعد 60 ثانية؛ الباقي فوري عند الموافقة.
POWER_SCHEDULED_S = {"shutdown": 60, "restart": 60, "lock": 0, "sleep": 0, "logoff": 0}


def default_power_executor(action: str) -> None:
    """ينفّذ فعل طاقة: إيقاف/إعادة مجدولان بعد 60 ثانية، والباقي فوري.

    ويندوز: shutdown للقوى المجدولة وتسجيل الخروج، وctypes للقفل
    (LockWorkStation) والسكون (powrprof.SetSuspendState). لينكس:
    shutdown وloginctl/systemctl بأفضل جهد.
    """
    if IS_WINDOWS:
        import ctypes

        if action == "lock":
            ctypes.windll.user32.LockWorkStation()
            return
        if action == "sleep":
            ctypes.windll.powrprof.SetSuspendState(False, True, False)
            return
        argv = {
            "shutdown": ["shutdown", "/s", "/t", "60"],
            "restart": ["shutdown", "/r", "/t", "60"],
            "logoff": ["shutdown", "/l"],
        }[action]
        subprocess.Popen(
            argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
        return
    argv = {
        "shutdown": ["shutdown", "-h", "+1"],
        "restart": ["shutdown", "-r", "+1"],
        "sleep": ["systemctl", "suspend"],
        "lock": ["loginctl", "lock-session"],
        "logoff": ["loginctl", "terminate-user", os.environ.get("USER", "")],
    }[action]
    subprocess.Popen(
        argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=_NO_WINDOW,
    )


# ======================================================================
# الصوت والنوافذ والعمليات
# ======================================================================
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VOLUME_ACTIONS = ("up", "down", "mute")


def default_volume_executor(action: str) -> None:
    """يحرّك صوت النظام بمفاتيح الوسائط (ويندوز: keybd_event).

    رفع/خفض = خطوتان في النداء الواحد؛ كتم = خطوة. غير ويندوز:
    يرفع RuntimeError (يردّ الخادم 501 — لا مسار موثوق عام).
    """
    if not IS_WINDOWS:
        raise RuntimeError("تحكّم الصوت بمفاتيح الوسائط متاح على ويندوز فقط")
    import ctypes

    vk = {"up": VK_VOLUME_UP, "down": VK_VOLUME_DOWN, "mute": VK_VOLUME_MUTE}[action]
    steps = 1 if action == "mute" else 2
    for _ in range(steps):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)  # KEYEVENTF_KEYUP


def list_windows() -> list[dict]:
    """النوافذ العلوية المرئية ذات العناوين: [{id, title}].

    ويندوز: EnumWindows + GetWindowText عبر ctypes (id = مقبض النافذة
    كعدد). غيره: قائمة فارغة.
    """
    if not IS_WINDOWS:
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[dict] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if buffer.value:
                    found.append({"id": int(hwnd), "title": buffer.value})
        return True

    user32.EnumWindows(_enum, 0)
    return found


WINDOW_ACTIONS = ("focus", "minimize", "maximize", "close")


def default_window_executor(window_id: int, action: str) -> None:
    """يتحكّم بنافذة عبر مقبضها (ويندوز فقط): إظهار/تصغير/تكبير/إغلاق."""
    if not IS_WINDOWS:
        raise RuntimeError("التحكّم بالنوافذ متاح على ويندوز فقط")
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = int(window_id)
    if action == "focus":
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
    elif action == "minimize":
        user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    elif action == "maximize":
        user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
    elif action == "close":
        user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    else:
        raise RuntimeError(f"فعل نافذة غير معروف: {action}")


def list_processes(runner=None, limit: int = 50) -> list[dict]:
    """أثقل العمليات ذاكرةً (حتى limit): [{pid, name, mem_mb}].

    runner: دالة (argv) -> (returncode, stdout) قابلة للحقن.
    ويندوز: tasklist بصيغة CSV (بلا ترويسة)، تُفرز بالذاكرة هنا.
    غيره: ps مرتبة بالذاكرة.
    """
    run = runner or _run_capture
    processes: list[dict] = []
    try:
        if IS_WINDOWS:
            rc, out = run(["tasklist", "/FO", "CSV", "/NH"])
            if rc == 0:
                for row in csv.reader(io.StringIO(out)):
                    # "Image Name","PID","Session Name","Session#","Mem Usage"
                    if len(row) < 5:
                        continue
                    name = row[0].strip()
                    mem_raw = row[4].strip()
                    if mem_raw.endswith(" K"):
                        mem_raw = mem_raw[:-2]
                    try:
                        pid = int(row[1])
                        mem_kb = int(mem_raw.replace(",", "").strip())
                    except ValueError:
                        continue
                    if not name:
                        continue
                    processes.append(
                        {
                            "pid": pid,
                            "name": name,
                            "mem_mb": round(mem_kb / 1024, 1),
                        }
                    )
                processes.sort(key=lambda p: p["mem_mb"], reverse=True)
                processes = processes[:limit]
        else:
            rc, out = run(["ps", "-eo", "pid=,comm=,rss=", "--sort=-rss"])
            if rc == 0:
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    try:
                        pid = int(parts[0])
                        rss_kb = int(parts[-1])
                    except ValueError:
                        continue
                    processes.append(
                        {
                            "pid": pid,
                            "name": " ".join(parts[1:-1]),
                            "mem_mb": round(rss_kb / 1024, 1),
                        }
                    )
                    if len(processes) >= limit:
                        break
    except Exception:
        return []
    return processes


def default_process_killer(pid: int, runner=None) -> None:
    """ينهي عملية برقمها. يرفع استثناء عند الفشل.

    runner: دالة (argv) -> (returncode, stdout) قابلة للحقن.
    ويندوز: taskkill /PID. غيره: kill.
    """
    run = runner or _run_capture
    argv = ["taskkill", "/PID", str(int(pid))] if IS_WINDOWS else ["kill", str(int(pid))]
    rc, _ = run(argv)
    if rc != 0:
        raise RuntimeError(f"فشل إنهاء العملية {pid} (رمز {rc})")


def open_target(target: str) -> None:
    """يفتح ملفاً/مجلداً/رابطاً بالتطبيق الافتراضي للنظام."""
    if IS_WINDOWS:
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(
            ["open", target],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
    else:
        subprocess.Popen(
            ["xdg-open", target],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )


# ======================================================================
# الطابعات والطباعة
# ======================================================================
def _run_capture(argv: list[str], timeout: float = 15.0) -> tuple[int, str]:
    proc = subprocess.run(
        argv, capture_output=True, text=True, timeout=timeout,
        creationflags=_NO_WINDOW,
    )
    return proc.returncode, proc.stdout or ""


# أعلام تعداد الطابعات في winspool: المحلية + اتصالات الشبكة المحفوظة.
_PRINTER_ENUM_LOCAL = 0x00000002
_PRINTER_ENUM_CONNECTIONS = 0x00000004


class _SystemTime(ctypes.Structure):
    """SYSTEMTIME في winspool (8 قيم WORD) — جزء من PRINTER_INFO_2."""

    _fields_ = [
        (name, ctypes.c_ushort)
        for name in (
            "wYear", "wMonth", "wDayOfWeek", "wDay",
            "wHour", "wMinute", "wSecond", "wMilliseconds",
        )
    ]


class _PrinterInfo2(ctypes.Structure):
    """PRINTER_INFO_2 كما يعيدها EnumPrintersW عند المستوى 2."""

    _fields_ = [
        ("pServerName", ctypes.c_wchar_p),
        ("pPrinterName", ctypes.c_wchar_p),
        ("pShareName", ctypes.c_wchar_p),
        ("pPortName", ctypes.c_wchar_p),
        ("pDriverName", ctypes.c_wchar_p),
        ("pComment", ctypes.c_wchar_p),
        ("pLocation", ctypes.c_wchar_p),
        ("pDevMode", ctypes.c_void_p),
        ("pSepFile", ctypes.c_wchar_p),
        ("pPrintProcessor", ctypes.c_wchar_p),
        ("pDatatype", ctypes.c_wchar_p),
        ("pParameters", ctypes.c_wchar_p),
        ("pSecurityDescriptor", ctypes.c_void_p),
        ("Attributes", ctypes.c_uint32),
        ("Priority", ctypes.c_uint32),
        ("DefaultPriority", ctypes.c_uint32),
        ("StartTime", _SystemTime),
        ("UntilTime", _SystemTime),
        ("Status", ctypes.c_uint32),
        ("cJobs", ctypes.c_uint32),
        ("AveragePPM", ctypes.c_uint32),
    ]


def _parse_printer_records(buffer, count: int, default_name: str = "") -> list[dict]:
    """يفكّ سجلّات PRINTER_INFO_2 من مخزن ctypes إلى [{name, is_default}].

    buffer: أي كائن ctypes يبدأ عنده صفّ السجلّات (مخزن EnumPrintersW
    في الإنتاج، أو صفّ مُصنّع في الاختبارات). السجلّات بلا اسم تُتخطّى.
    """
    printers: list[dict] = []
    if count <= 0:
        return printers
    entries = (_PrinterInfo2 * int(count)).from_address(ctypes.addressof(buffer))
    for entry in entries:
        name = entry.pPrinterName
        if name:
            printers.append(
                {"name": name, "is_default": bool(default_name) and name == default_name}
            )
    return printers


def _default_printer_name(winspool) -> str:
    """اسم الطابعة الافتراضية عبر GetDefaultPrinterW، أو "" إن تعذّر."""
    from ctypes import wintypes

    size = wintypes.DWORD(0)
    winspool.GetDefaultPrinterW(None, ctypes.byref(size))
    if size.value == 0:
        return ""
    buffer = ctypes.create_unicode_buffer(size.value)
    if winspool.GetDefaultPrinterW(buffer, ctypes.byref(size)):
        return buffer.value
    return ""


def _list_printers_windows() -> list[dict]:
    """طابعات ويندوز عبر winspool.drv: EnumPrintersW بمستوى 2.

    نداءان: الأول بمخزن صفري لمعرفة الحجم المطلوب (pcbNeeded)، ثم
    تخصيص المخزن والنداء الثاني الفعلي. أي فشل = قائمة فارغة.
    """
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv")
    flags = _PRINTER_ENUM_LOCAL | _PRINTER_ENUM_CONNECTIONS
    needed = wintypes.DWORD(0)
    returned = wintypes.DWORD(0)
    winspool.EnumPrintersW(
        flags, None, 2, None, 0, ctypes.byref(needed), ctypes.byref(returned)
    )
    if needed.value == 0:
        return []
    buffer = ctypes.create_string_buffer(needed.value)
    ok = winspool.EnumPrintersW(
        flags, None, 2, buffer, needed.value,
        ctypes.byref(needed), ctypes.byref(returned),
    )
    if not ok:
        return []
    return _parse_printer_records(
        buffer, returned.value, _default_printer_name(winspool)
    )


def list_printers(runner=None) -> list[dict]:
    """الطابعات المعروفة للنظام: [{name, is_default}] — قد تكون فارغة.

    ويندوز: winspool.drv عبر ctypes (EnumPrintersW). غيره: lpstat.
    runner: دالة (argv) -> (returncode, stdout) قابلة للحقن في
    الاختبارات لمسار lpstat؛ الافتراضي يشغّل أوامر النظام فعلياً.
    """
    printers: list[dict] = []
    try:
        if IS_WINDOWS:
            return _list_printers_windows()
        run = runner or _run_capture
        if shutil.which("lpstat"):
            rc, out = run(["lpstat", "-a"])
            names = []
            if rc == 0:
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[0]:
                        names.append(parts[0])
            default_name = ""
            rc, out = run(["lpstat", "-d"])
            if rc == 0 and ":" in out:
                default_name = out.split(":", 1)[1].strip()
            printers = [
                {"name": name, "is_default": name == default_name}
                for name in names
            ]
    except Exception:
        return []
    return printers


def default_print_executor(path: str, printer: str | None = None) -> None:
    """يطبع ملفاً فعلياً. يرفع استثناء عند الفشل (يُبلَّغ ولا يمرّ صامتاً).

    ويندوز: فعل «print» للطابعة الافتراضية، أو PowerShell Out-Printer
    لطابعة مسمّاة (بأفضل جهد). لينكس: lp إن وُجد.
    """
    if IS_WINDOWS:
        if printer:
            script = (
                f"Get-Content -LiteralPath '{path}' -Raw | "
                f"Out-Printer -Name '{printer}'"
            )
            rc, _ = _run_capture(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                timeout=30,
            )
            if rc != 0:
                raise RuntimeError("فشلت الطباعة عبر PowerShell")
        else:
            os.startfile(path, "print")  # type: ignore[attr-defined]
        return
    if not shutil.which("lp"):
        raise RuntimeError("أداة الطباعة lp غير موجودة على هذا النظام")
    argv = ["lp"]
    if printer:
        argv += ["-d", printer]
    argv.append(path)
    rc, _ = _run_capture(argv, timeout=30)
    if rc != 0:
        raise RuntimeError("فشلت الطباعة عبر lp")


# ======================================================================
# الحافظة (نصّ فقط)
# ======================================================================
def get_clipboard(runner=None) -> str:
    """نصّ الحافظة الحالي؛ سلسلة فارغة إن تعذّر أو لم يكن نصاً.

    runner: دالة (argv) -> (returncode, stdout) قابلة للحقن.
    ويندوز: Get-Clipboard. لينكس: xclip/xsel إن وُجدا. غيره: فارغ.
    """
    run = runner or _run_capture
    try:
        if IS_WINDOWS:
            rc, out = run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "Get-Clipboard"]
            )
            return out.rstrip("\r\n") if rc == 0 else ""
        if shutil.which("xclip"):
            rc, out = run(["xclip", "-selection", "clipboard", "-o"])
            return out if rc == 0 else ""
        if shutil.which("xsel"):
            rc, out = run(["xsel", "--clipboard", "--output"])
            return out if rc == 0 else ""
    except Exception:
        return ""
    return ""


def set_clipboard(text: str, runner=None) -> None:
    """يضع نصاً في حافظة النظام. يرفع استثناء عند التعذّر.

    runner: دالة (argv, input_text) -> (returncode, stdout) قابلة
    للحقن؛ الافتراضي يشغّل أمر النظام ويمرّر النصّ في دخله القياسي
    (لا في سطر الأوامر — فلا حدود طول ولا مشاكل اقتباس).
    """
    if runner is not None:
        rc, _ = runner(_clipboard_set_argv(), text)
        if rc != 0:
            raise RuntimeError("تعذّر ضبط الحافظة")
        return
    argv = _clipboard_set_argv()
    if argv is None:
        raise RuntimeError("ضبط الحافظة غير متاح على هذه المنصّة")
    proc = subprocess.run(
        argv, input=text, capture_output=True, text=True, timeout=15,
        creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise RuntimeError("تعذّر ضبط الحافظة")


def _clipboard_set_argv() -> list[str] | None:
    if IS_WINDOWS:
        return [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "$input | Set-Clipboard",
        ]
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard"]
    if shutil.which("xsel"):
        return ["xsel", "--clipboard", "--input"]
    return None
