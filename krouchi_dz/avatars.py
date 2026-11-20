"""صور البوتات الجاهزة (معرض الأفاتار) في Krouchi_DZ.

دلالات القيمة المخزَّنة في bots.avatar بعد هذا الإصدار:
- اسم ملف من المعرض حرفياً (مثل "bot_3.png") ⇒ تُعرَض تلك الصورة.
- أي قيمة أخرى — بما فيها "" والقيم القديمة (إيموجي مثل "🤖" من
  قواعد أُنشئت قبل المعرض) ⇒ تراجع أحادي الحرف (monogram): أول حرف
  من اسم البوت، يُحسَب وقت العرض ولا يُخزَّن أبداً.

المعرض نفسه ملفات PNG مربّعة في assets/avatars بجانب جذر المشروع
(bot_1.png … bot_6.png). غياب المجلد أو أي ملف منه ليس خطأً أبداً:
كل الدوال هنا تتراجع بصمت (None / False) فيعرض المستدعي الأحادي.
"""

from __future__ import annotations

import os
from pathlib import Path

# ملفات المعرض الوحيدة المعترف بها — أي اسم خارجها ليس صورة معرض.
GALLERY_FILES = [
    "bot_1.png",
    "bot_2.png",
    "bot_3.png",
    "bot_4.png",
    "bot_5.png",
    "bot_6.png",
]

# متغيّر بيئة يتقدّم كل بحث تلقائي عن مجلد المعرض (كما في server).
ENV_AVATARS_DIR = "KROUCHI_AVATARS_DIR"


def is_gallery_avatar(value) -> bool:
    """هل القيمة اسم ملف معرض حرفياً؟ (إيموجي قديم أو "" ⇒ False)."""
    return isinstance(value, str) and value in GALLERY_FILES


def find_avatars_dir() -> Path | None:
    """يحدّد مجلد صور المعرض (assets/avatars) إن وُجد، وإلا None.

    ترتيب البحث — مرآة server.find_pwa_dir: متغيّر البيئة
    KROUCHI_AVATARS_DIR أولاً، ثم «assets/avatars» بجانب حزمة
    krouchi_dz (جذر المشروع — ينطبق على شجرة المصدر وعلى الحزم إن
    ضمّن المُحزّم المجلد بجانب run_gui.py)، ثم «assets/avatars»
    داخل مجلد العمل الحالي. لا يُقبل المرشّح إلا إن كان مجلداً.
    """
    candidates: list[Path] = []
    env_dir = os.environ.get(ENV_AVATARS_DIR)
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(
        Path(__file__).resolve().parent.parent / "assets" / "avatars"
    )
    candidates.append(Path.cwd() / "assets" / "avatars")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def avatar_image_path(value) -> Path | None:
    """مسار ملف صورة القيمة إن كانت من المعرض والملف موجود فعلاً.

    None في كل الحالات الأخرى: قيمة غير معرضية (إيموجي/فارغة/غريبة)،
    أو مجلد المعرض غائب، أو الملف نفسه غائب — فلا ينهار أي عرض.
    """
    if not is_gallery_avatar(value):
        return None
    avatars_dir = find_avatars_dir()
    if avatars_dir is None:
        return None
    path = avatars_dir / value
    return path if path.is_file() else None


def monogram_for_name(name) -> str:
    """حرف الأحادي لاسم بوت: أول حرف من الاسم المشذّب، أو "؟" إن خلا.

    هذا هو التراجع البصري لكل قيمة أفاتار غير معرضية — يُحسَب من
    الاسم وقت العرض فلا يحتاج أي تخزين ولا يتعارض مع إعادة التسمية.
    """
    text = str(name or "").strip()
    return text[0] if text else "؟"


def display_avatar_text(bot: dict) -> str:
    """النصّ الذي يمثّل أفاتار بوت في سياقات نصّية (قوائم/عناوين).

    الصور لا تسكن القوائم النصّية، فالتمثيل النصّي واحد للجميع:
    حرف الأحادي من اسم البوت — لقيم المعرض وغير المعرض على حدّ
    سواء. القيمة المخزَّنة الخام (إيموجي قديم مثلاً) لا تُعرَض أبداً.
    """
    return monogram_for_name((bot or {}).get("name", ""))
