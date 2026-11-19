"""إعدادات المزوّدين في Krouchi_DZ.

تعريفات المزوّدين تعيش في ملف JSON (providers.json داخل مجلد البيانات)،
لا في قاعدة البيانات ولا مضمّنة في الشيفرة. الملف يحمل لكل مزوّد:
الاسم، النوع (openai = متوافق مع OpenAI، gemini = Google Gemini)،
عنوان الأساس (base_url)، واسم مرجع السرّ (secret_ref) — المفتاح نفسه
لا يُكتب هنا إطلاقاً؛ يُحفظ في ملف الأسرار المنفصل (secrets.py).
المزوّدون المُدخَلون من المستخدم (أي مفتاح + أي عنوان) يحملون أيضاً
حالة التحقق (verified) وقائمة النماذج المكتشفة مع وقت اكتشافها —
تُكتب هنا عند نجاح الاكتشاف (discovery.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# البذرة الافتراضية: تُكتب في providers.json عند أول تشغيل إن لم يوجد.
# النماذج الافتراضية قابلة للتعديل من الملف نفسه دون لمس الشيفرة.
DEFAULT_PROVIDERS = [
    {
        "name": "openrouter",
        "kind": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "secret_ref": "openrouter",
        "default_model": "meta-llama/llama-3.3-70b-instruct",
    },
    {
        "name": "groq",
        "kind": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "secret_ref": "groq",
        "default_model": "llama-3.3-70b-versatile",
    },
    {
        "name": "zai",
        "kind": "openai",
        "base_url": "https://api.z.ai/api/paas/v4",
        "secret_ref": "zai",
        "default_model": "glm-4.5",
    },
    {
        "name": "nvidia",
        "kind": "openai",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "secret_ref": "nvidia",
        "default_model": "meta/llama-3.3-70b-instruct",
    },
    {
        "name": "gemini",
        "kind": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "secret_ref": "gemini",
        "default_model": "gemini-2.0-flash",
    },
]


@dataclass
class ProviderConfig:
    """تعريف مزوّد واحد كما في ملف الإعدادات (بلا مفتاح)."""

    name: str
    kind: str  # "openai" | "gemini" | "mock"
    base_url: str
    secret_ref: str
    default_model: str = ""
    # حالة الاكتشاف (للمزوّدين المُدخَلين من المستخدم خاصة):
    verified: bool = True        # هل نجح جلب النماذج بهذا المفتاح؟
    models: list[str] = field(default_factory=list)  # النماذج المكتشفة (كاش)
    models_fetched_at: str = ""  # وقت الاكتشاف ISO — لحساب صلاحية الكاش

    @classmethod
    def from_dict(cls, d: dict) -> "ProviderConfig":
        return cls(
            name=d["name"],
            kind=d.get("kind", "openai"),
            base_url=d.get("base_url", ""),
            secret_ref=d.get("secret_ref", d["name"]),
            default_model=d.get("default_model", ""),
            verified=bool(d.get("verified", True)),
            models=[str(m) for m in d.get("models", []) or []],
            models_fetched_at=str(d.get("models_fetched_at", "") or ""),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "base_url": self.base_url,
            "secret_ref": self.secret_ref,
            "default_model": self.default_model,
            "verified": self.verified,
            "models": list(self.models),
            "models_fetched_at": self.models_fetched_at,
        }


def ensure_providers_file(path: Path) -> Path:
    """يكتب ملف البذرة إن لم يوجد، ويعيد المسار."""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"providers": DEFAULT_PROVIDERS}
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return path


def load_providers(path: Path) -> dict[str, ProviderConfig]:
    """يقرأ تعريفات المزوّدين من ملف JSON ويعيدها قاموساً بالاسم."""
    path = ensure_providers_file(Path(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    providers: dict[str, ProviderConfig] = {}
    for entry in raw.get("providers", []):
        cfg = ProviderConfig.from_dict(entry)
        providers[cfg.name] = cfg
    return providers


def save_providers(path: Path, providers: dict[str, "ProviderConfig"]) -> None:
    """يعيد كتابة ملف المزوّدين من القاموس (بلا أي مفتاح — المراجع فقط)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"providers": [cfg.to_dict() for cfg in providers.values()]}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
