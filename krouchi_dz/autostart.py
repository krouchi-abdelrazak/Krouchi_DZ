"""تشغيل Krouchi_DZ مع بدء ويندوز — اختصار مجلد «بدء التشغيل».

آلية واحدة مشتركة مع مثبّت NSIS (installer.nsi): ملف اختصار باسم
Krouchi_DZ.lnk في مجلد بدء تشغيل ويندوز
(%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup)
يشير إلى Krouchi_DZ.exe للبرنامج. المثبّت ينشئ هذا الاختصار نفسه
عند اختيار مكوّن «Start with Windows»، ومفتاح التبديل في نافذة
«ربط الهاتف» (gui.PhoneLinkDialog) ينشئه ويحذفه — وحالة المفتاح
الابتدائية هي وجود الملف فعلاً على القرص لحظة فتح النافذة، لا أي
إعداد محفوظ في قاعدة البيانات.

إنشاء الاختصار يتم عبر PowerShell (WScript.Shell) — الأداة الوحيدة
المتاحة في ويندوز بلا مكتبات خارجية — وبعلم CREATE_NO_WINDOW حتى
لا تومض نافذة وحدة تحكّم (كما في control.py). المنفّذ (runner)
قابل للحقن فلا تلمس الاختبارات PowerShell الحقيقي أبداً.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = os.name == "nt"

# ويندوز فقط: منع وميض نافذة وحدة تحكّم عند تشغيل PowerShell المساعد.
# الثابت غير موجود على الأنظمة الأخرى فيعيد getattr صفراً — وهو
# القيمة الافتراضية أصلاً فلا أثر هناك (نمط control.py نفسه).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SHORTCUT_NAME = "Krouchi_DZ.lnk"
_STARTUP_PARTS = ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def _is_windows() -> bool:
    """هل المنصّة ويندوز؟ ثابت الوحدة أو os.name الحالي — أيّهما حُقن.

    الفحص عبر دالة (لا ثابت لحظي وحده) حتى تستطيع الاختبارات محاكاة
    ويندوز بحقن IS_WINDOWS أو os.name دون تشغيل فعلي على ويندوز.
    """
    return IS_WINDOWS or os.name == "nt"


def _as_path(value) -> Path:
    """يحوّل قيمة إلى Path دون إعادة لفّ كائن Path قائم أصلاً."""
    return value if isinstance(value, Path) else Path(value)


# ======================================================================
# مسار الاختصار وحالته
# ======================================================================
def startup_shortcut_path(appdata: str | Path | None = None) -> Path:
    """مسار اختصار بدء التشغيل: <APPDATA>/Microsoft/Windows/Start
    Menu/Programs/Startup/Krouchi_DZ.lnk.

    الأساس: الوسيط appdata إن أُعطي، وإلا متغيّر البيئة APPDATA،
    وإلا AppData/Roaming تحت مجلد المستخدم الرئيسي.
    """
    if appdata is not None:
        base = _as_path(appdata)
    else:
        env_appdata = os.environ.get("APPDATA")
        base = Path(env_appdata) if env_appdata else Path.home() / "AppData" / "Roaming"
    return base.joinpath(*_STARTUP_PARTS, SHORTCUT_NAME)


def is_startup_enabled(path=None, exists=os.path.exists) -> bool:
    """هل التشغيل مع ويندوز مفعَّل؟ أي هل ملف الاختصار موجود فعلاً.

    exists قابلة للحقن في الاختبارات (افتراضيها os.path.exists).
    """
    shortcut = path if path is not None else startup_shortcut_path()
    return bool(exists(shortcut))


# ======================================================================
# هدف الاختصار الافتراضي
# ======================================================================
def default_target() -> tuple[str, str]:
    """(الهدف، الوسائط) الافتراضيان لاختصار بدء التشغيل.

    في التخطيط المجمّع/المثبَّت يوجد Krouchi_DZ.exe بجانب run_gui.py
    (جذر الحزمة) فيُستهدَف مباشرة بلا وسائط. في شجرة المصدر لا يوجد
    exe: الهدف هو مفسّر بايثون الحالي ووسيطته مسار run_gui.py
    مقتبساً بعلامتي تنصيص مزدوجتين.
    """
    root = Path(__file__).resolve().parent.parent
    exe = root / "Krouchi_DZ.exe"
    if exe.is_file():
        return str(exe), ""
    run_gui = root / "run_gui.py"
    return sys.executable, f'"{run_gui}"'


# ======================================================================
# إنشاء الاختصار عبر PowerShell (المنفّذ قابل للحقن)
# ======================================================================
def _default_runner(argv: list[str]) -> tuple[int, str, str]:
    """المنفّذ الافتراضي: subprocess.run بعلم منع نافذة وحدة التحكّم."""
    proc = subprocess.run(
        argv, capture_output=True, text=True, creationflags=_NO_WINDOW
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _ps_single(value: str) -> str:
    """يقتبس قيمة داخل علامتي اقتباس مفردتين في PowerShell.

    علامة الاقتباس المفردة داخل النصّ تُضاعَف ('' بدل ') — قاعدة
    الهروب الوحيدة داخل سلاسل PowerShell المفردة الاقتباس.
    """
    return "'" + str(value).replace("'", "''") + "'"


def set_startup_enabled(
    enabled: bool,
    *,
    shortcut_path=None,
    target=None,
    args: str = "",
    icon=None,
    runner=None,
) -> bool:
    """يفعّل/يعطّل التشغيل مع ويندوز بإنشاء اختصار بدء التشغيل أو حذفه.

    التعطيل: حذف الاختصار إن وُجد (غيابه ليس خطأ) وإعادة False —
    يعمل على أي منصّة. التفعيل (ويندوز فقط، وإلا RuntimeError):
    إنشاء الاختصار عبر PowerShell/WScript.Shell وإعادة True؛ فشل
    PowerShell (رمز خروج غير صفري) يرفع RuntimeError برسالة عربية.

    target/args: هدف الاختصار ووسائطه؛ غياب الهدف يستعمل
    default_target() (ووسائطه الافتراضية إن لم تُعطَ وسائط).
    icon: أيقونة الاختصار؛ غيابها يعني <مجلد الهدف>/assets/icon.ico
    إن وُجد على القرص، وإلا بلا أيقونة صريحة.
    runner: منفّذ (argv) -> (returncode, stdout, stderr) قابل للحقن؛
    الافتراضي يشغّل PowerShell فعلياً عبر subprocess.
    """
    shortcut = (
        _as_path(shortcut_path)
        if shortcut_path is not None
        else startup_shortcut_path()
    )
    if not enabled:
        shortcut.unlink(missing_ok=True)
        return False
    if not _is_windows():
        raise RuntimeError("التشغيل مع بدء ويندوز متاح على ويندوز فقط")
    if target is None:
        target, default_args = default_target()
        if not args:
            args = default_args
    target_text = str(target)
    target_dir = os.path.dirname(target_text)
    if icon is None:
        candidate = os.path.join(target_dir, "assets", "icon.ico")
        icon_text = candidate if os.path.exists(candidate) else None
    else:
        icon_text = str(icon) if icon else None

    parts = [
        "$ws = New-Object -ComObject WScript.Shell",
        f"$s = $ws.CreateShortcut({_ps_single(str(shortcut))})",
        f"$s.TargetPath = {_ps_single(target_text)}",
    ]
    if args:
        parts.append(f"$s.Arguments = {_ps_single(str(args))}")
    parts.append(f"$s.WorkingDirectory = {_ps_single(target_dir)}")
    if icon_text:
        parts.append(f"$s.IconLocation = {_ps_single(icon_text)}")
    parts.append("$s.Save()")
    script = "; ".join(parts)
    argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]

    try:
        shortcut.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # مجلد بدء التشغيل موجود في ويندوز أصلاً؛ فشل PowerShell سيُبلَّغ تحت
    run = runner if runner is not None else _default_runner
    rc, _stdout, stderr = run(argv)
    if rc != 0:
        detail = f": {stderr.strip()}" if stderr and stderr.strip() else ""
        raise RuntimeError(
            f"فشل إنشاء اختصار بدء التشغيل عبر PowerShell (رمز {rc}){detail}"
        )
    return True
