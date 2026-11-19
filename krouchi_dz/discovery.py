"""اكتشاف المزوّدين في Krouchi_DZ — «أي مفتاح وأي عنوان».

قلب هذه الوحدة هو ما يفعله DeepSeek Harness وأمثاله: يعطي المستخدم
عنوان أساس (base_url) ومفتاح API فقط، فيُطبَّع العنوان، ويُخمَّن نوع
نقطة الاتصال من اسم الخادم، ثم تُجلَب قائمة النماذج المتاحة للمفتاح
من GET {base}/models — فيعرف البرنامج المزوّد بنفسه دون إعداد مسبق.

الأخطاء هنا صادقة ومميّزة: لكل فشل (عنوان غير صالح، خادم لا يُبلَغ،
مفتاح مرفوض، ردّ ليس JSON، قائمة فارغة...) رسالة عربية واضحة خاصة به،
تُعاد في DiscoveryResult ولا تنهار العملية أبداً.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlparse

# -- رسائل الخطأ العربية (واحدة لكل نوع فشل، تُعرض على المستخدم) ---------
ERR_BAD_URL = "العنوان غير صالح — تأكد أنه يبدأ بـ http:// أو https:// ويحمل اسم خادم"
ERR_UNREACHABLE = "تعذّر الوصول إلى الخادم — تحقق من العنوان ومن اتصال الإنترنت"
ERR_AUTH = "رفض المزوّد المفتاح (خطأ مصادقة 401/403) — تحقق من صحة مفتاح API"
ERR_NOT_JSON = "ردّ الخادم ليس JSON — غالباً العنوان ليس عنوان API صحيحاً"
ERR_BAD_SHAPE = "وصل ردّ من الخادم، لكنه لا يحمل قائمة نماذج بالشكل المتوقع"
ERR_EMPTY = "اتصلنا بالمزوّد بنجاح، لكنه لم يُعد أي نموذج متاحاً لهذا المفتاح"
ERR_NO_KEY = "لا يوجد مفتاح محفوظ لهذا المزوّد — أضف مفتاح API أولاً"

DISCOVERY_TIMEOUT = 30.0        # مهلة طلب اكتشاف النماذج (ثوانٍ)
MODELS_CACHE_TTL = 3600.0       # مدة صلاحية كاش النماذج المكتشفة (ثوانٍ)

_VERSION_SEGMENT = re.compile(r"v\d+(\.\d+)?(beta|alpha)?")
_GEMINI_HOST = "generativelanguage.googleapis.com"


class DiscoveryError(Exception):
    """فشل اكتشاف مصنّف: kind برمجياً، وmessage عربية جاهزة للعرض."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass
class DiscoveryResult:
    """نتيجة إدخال API أو جلب نماذج: نجاح بالنماذج، أو فشل برسالة واضحة."""

    ok: bool
    provider: str | None = None
    models: list[str] = field(default_factory=list)
    error: str = ""
    error_kind: str = ""
    verified: bool = False
    from_cache: bool = False
    base_url: str = ""


# -- تطبيع العنوان وتصنيف النوع واشتقاق الاسم -----------------------------

def classify_kind(base_url: str, override: str | None = None) -> str:
    """يخمّن نوع نقطة الاتصال من اسم الخادم؛ التجاوز اليدوي ينتصر دائماً."""
    if override:
        kind = str(override).strip().lower()
        if kind in ("openai", "gemini"):
            return kind
        raise ValueError(f"نوع مزوّد غير معروف: {override}")
    candidate = base_url if "://" in base_url else "https://" + base_url
    host = (urlparse(candidate).hostname or "").lower()
    if host == _GEMINI_HOST:
        return "gemini"
    return "openai"


def normalize_base_url(raw_url: str, kind: str = "openai") -> str:
    """يُعيد العنوان إلى صورة قانونية واحدة.

    يقبل: بلا مخطط (يُضاف https)، بشرطة مائلة أخيرة أو دونها، بلاحقة
    /chat/completions أو /models إن لصقها المستخدم كاملة، وبنسخة /v1
    أو دونها — فتؤول كل الصور لنفس العنوان المحفوظ. يرفع ValueError
    برسالة عربية إن كان العنوان غير صالح أصلاً.
    """
    text = (raw_url or "").strip()
    if not text:
        raise ValueError(ERR_BAD_URL)
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(ERR_BAD_URL)
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if path.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break
    base = f"{parsed.scheme}://{parsed.netloc}{path}"
    last_segment = path.rsplit("/", 1)[-1] if path else ""
    if not _VERSION_SEGMENT.fullmatch(last_segment):
        # لا نسخة في آخر المسار: نضيف الافتراضية بحسب النوع
        # (v1 للمتوافق مع OpenAI، v1beta لـ Gemini).
        base += "/v1beta" if kind == "gemini" else "/v1"
    return base


def derive_name(base_url: str) -> str:
    """يشتق اسماً مقروءاً للمزوّد من اسم الخادم (openrouter.ai ← openrouter)."""
    host = (urlparse(base_url).hostname or "custom").lower()
    parts = host.split(".")
    while len(parts) > 2 and parts[0] in ("api", "www", "integrate"):
        parts.pop(0)
    if len(parts) >= 2:
        label = parts[-2]
        if len(label) < 3:  # نطاق قصير جداً مثل z.ai: خذ الخادم كاملاً
            label = "-".join(parts)
    else:
        label = parts[0]
    label = re.sub(r"[^a-z0-9_-]+", "-", label).strip("-")
    return label or "custom"


def sanitize_name(name: str) -> str:
    """ينظّف اسماً أعطاه المستخدم ليصلح اسمَ مزوّد ومرجعَ سرّ."""
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", str(name).strip().lower()).strip("-")
    return cleaned or "custom"


# -- النقل الافتراضي (GET) --------------------------------------------------

def _urllib_get_transport(url: str, headers: dict, timeout: float = DISCOVERY_TIMEOUT) -> dict:
    """GET عبر urllib وإعادة الردّ مُحلَّلاً؛ الفشل DiscoveryError مصنّف."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise DiscoveryError("auth", ERR_AUTH) from exc
        raise DiscoveryError(
            "http", f"أعاد الخادم خطأ HTTP {exc.code} — راجع العنوان أو حالة الخدمة"
        ) from exc
    except urllib.error.URLError as exc:
        raise DiscoveryError(
            "unreachable", f"{ERR_UNREACHABLE} ({exc.reason})"
        ) from exc
    except OSError as exc:  # مهلة/انقطاع على مستوى المقبس
        raise DiscoveryError("unreachable", f"{ERR_UNREACHABLE} ({exc})") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise DiscoveryError("not_json", ERR_NOT_JSON) from exc
    if not isinstance(data, dict):
        raise DiscoveryError("bad_shape", ERR_BAD_SHAPE)
    return data


# -- جلب النماذج --------------------------------------------------------------

def discover_models(base_url: str, api_key: str, kind: str, get_transport=None) -> list[str]:
    """يطلب قائمة النماذج من نقطة الاتصال ويعيد معرّفاتها مرتبة كما وردت.

    يرفع DiscoveryError مصنّفاً عند أي فشل — لا يعيد قائمة جزئية أبداً.
    """
    transport = get_transport or _urllib_get_transport
    base = base_url.rstrip("/")
    if kind == "gemini":
        url = base + "/models"
        headers = {"x-goog-api-key": api_key}
        data = transport(url, headers)
        items = data.get("models") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise DiscoveryError("bad_shape", ERR_BAD_SHAPE)
        models: list[str] = []
        for item in items:
            if isinstance(item, dict) and item.get("name"):
                name = str(item["name"])
                if name.startswith("models/"):
                    name = name[len("models/"):]
                if name and name not in models:
                    models.append(name)
    else:  # openai — الشكل القياسي {"data": [{"id": ...}]}
        url = base + "/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        data = transport(url, headers)
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise DiscoveryError("bad_shape", ERR_BAD_SHAPE)
        models = []
        for item in items:
            if isinstance(item, dict) and item.get("id"):
                model_id = str(item["id"])
                if model_id not in models:
                    models.append(model_id)
    if not models:
        raise DiscoveryError("empty", ERR_EMPTY)
    return models
