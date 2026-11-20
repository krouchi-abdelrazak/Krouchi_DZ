"""طبقة المزوّدين في Krouchi_DZ: عملاء محادثة بواجهة موحّدة.

- OpenAICompatibleProvider: يغطي OpenRouter وGroq وZ AI وNVIDIA NIM
  (وأي خدمة متوافقة مع OpenAI) بمجرّد تغيير base_url والمفتاح والنموذج.
- GeminiProvider: عميل Google Gemini عبر generativelanguage API.
- MockProvider: مزوّد مكتوب الردود للاختبارات — بلا أي شبكة.

النقل HTTP عبر urllib من المكتبة القياسية، وقابل للحقن (transport)
حتى تُختبَر أشكال الطلبات دون شبكة حقيقية.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .config import ProviderConfig


class ProviderError(Exception):
    """خطأ من طبقة المزوّد (شبكة أو ردّ غير صالح)."""


@dataclass
class ToolCall:
    """طلب أداة واحد من النموذج."""

    id: str
    name: str
    arguments: dict = field(default_factory=dict)

    def to_api_dict(self) -> dict:
        """شكل OpenAI القياسي لطلب الأداة (يُحفظ في قاعدة البيانات كما هو)."""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }


@dataclass
class ChatResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


# تعريفات الأدوات التي يستطيع البوت طلبها (تمرّ كلها عبر وسيط الموافقات).
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "قراءة محتوى ملف نصي من جهاز المستخدم",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "مسار الملف"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": (
                "قراءة نصّ وثيقة من جهاز المستخدم مع استخراج النصّ "
                "القابل للقراءة منها: ملفات Word ‏(.docx) وExcel "
                "‏(.xlsx) تُستخرَج فقراتها وجداولها وصفوفها نصاً "
                "حقيقياً، وPDF ‏(.pdf) يُقرأ بأفضل جهد من نصّه "
                "المخزَّن (الممسوح ضوئياً لا نصّ فيه فيتعذّر)، "
                "والملفات النصّية "
                "(.txt و.md و.csv و.json و.xml و.html و.log) تُقرأ "
                "بترميزها الصحيح (بما فيه ملفات ويندوز العربية). "
                "استعمل هذه الأداة — لا read_file — كلما طلب المستخدم "
                "قراءة وثيقة أو رسالة رسمية أو محضر، لتلخّصها له أو "
                "تردّ عليها؛ أما read_file فهي لقراءة ملف نصّي خام "
                "كما هو حرفياً."
            ),
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "مسار الوثيقة"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_clipboard",
            "description": (
                "قراءة نصّ الحافظة الحالي على جهاز المستخدم (ما نسخه "
                "للتوّ). استعملها عندما يطلب المستخدم العمل على نصّ "
                "نسخه، أو يسأل عمّا في الحافظة. تعيد النصّ كما هو، "
                "أو تنبيهاً إن كانت الحافظة فارغة أو لا تحوي نصاً."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "see_screen",
            "description": (
                "رؤية شاشة حاسوب المستخدم كما هي الآن بعينيك: تلتقط "
                "صورة الشاشة الحالية وتُريك إياها صورةً حقيقية في "
                "رسالتك التالية، فتصف ما تراه وتتصرّف بناءً عليه. "
                "انظر أولاً ثم افهم ثم تصرّف: استعملها كلما لم تكن "
                "متأكداً مما هو مفتوح أو معروض قبل أن تتصرّف بيديك — "
                "type_text للكتابة داخل البرامج، وpress_keys للمفاتيح، "
                "وwindow_action لإدارة النوافذ. المعامل question "
                "اختياري: سؤال محدّد تريد الإجابة عنه مما في الشاشة. "
                "تتطلّب نموذجاً بصرياً يرى الصور؛ فإن كان نموذج "
                "Krouchi AI الحالي نصّياً فقط أعادت الأداة تنبيهاً "
                "بذلك بدل الصورة."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "سؤال اختياري عمّا تريد معرفته من الشاشة"
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "كتابة نص في ملف على جهاز المستخدم (ينشئ المجلدات اللازمة)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "مسار الملف"},
                    "content": {"type": "string", "description": "النص المراد كتابته"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "تشغيل أمر على جهاز المستخدم وإعادة خرجه النصّي. للأوامر "
                "التي تنتهي وتطبع نتيجة فقط (مثل dir أو ipconfig أو قراءة "
                "حالة النظام). لا تستعملها لفتح برامج ذات نوافذ (كمفكّرة "
                "أو متصفّح): البرنامج ذو النافذة لا ينتهي، فتعلّق الأداة "
                "حتى انقضاء المهلة ثم يُقتل البرنامج؛ فتحُ برنامج أو ملف "
                "في نافذة ظاهرة له أداته الخاصة في هذه القائمة: open_target."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "الأمر المراد تشغيله (ينتهي ويعيد خرجاً نصّياً)",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_target",
            "description": (
                "فتح برنامج أو ملف أو مجلد أو موقع ليظهر مرئياً على شاشة "
                "جهاز المستخدم. استعمل هذه الأداة — لا run_command أبداً — "
                "كلما طلب المستخدم فتح شيء يراه أمامه (مثل «افتح المفكّرة» "
                "أو «افتح موجّه الأوامر» أو «افتح هذا الملف» أو «افتح موقع "
                "كذا»). أما run_command فهي للأوامر التي تنتهي وتعيد "
                "خرجاً نصّياً فقط، ولا تفتح نوافذ ظاهرة."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": (
                            "ما يُفتح: اسم برنامج (مثل cmd أو notepad) "
                            "أو مسار ملف/مجلد أو رابط URL"
                        ),
                    }
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": (
                "سرد النوافذ المفتوحة الآن على جهاز المستخدم (معرّف كل "
                "نافذة وعنوانها). أداة قراءة فقط: لا تغيّر شيئاً ولا "
                "تحتاج موافقة. استعملها أولاً كلما احتجت معرّف نافذة "
                "لإدارتها بأداة window_action."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "window_action",
            "description": (
                "تنفيذ إجراء على نافذة مفتوحة على جهاز المستخدم: focus "
                "(تفعيل النافذة وإظهارها في المقدمة) أو minimize (تصغيرها) "
                "أو maximize (تكبيرها) أو close (إغلاقها). استعمل هذه "
                "الأداة — لا run_command ولا taskkill أبداً — كلما طلب "
                "المستخدم إغلاق برنامج أو إدارة نافذته. وإن لم تعرف "
                "معرّف النافذة فاسرد النوافذ أولاً بأداة list_windows."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "معرّف النافذة (من list_windows)",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["focus", "minimize", "maximize", "close"],
                        "description": (
                            "الإجراء: focus تفعيل وإظهار في المقدمة، "
                            "minimize تصغير، maximize تكبير، close إغلاق"
                        ),
                    },
                },
                "required": ["id", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": (
                "كتابة نص داخل البرنامج المفتوح حالياً على جهاز المستخدم: "
                "يُضخّ النص بحقن يونيكود في النافذة المركّزة الآن، كما لو "
                "كتبه المستخدم بلوحة مفاتيحه — فيعمل في أي برنامج "
                "(Word أو المفكّرة أو نموذج في متصفّح أو غيرها). "
                "سير العمل للكتابة في برنامج: افتح البرنامج أو الملف "
                "أولاً بـ open_target، وركّز نافذته بـ window_action "
                "(focus) بعد سرد النوافذ بـ list_windows إن لزم، ثم "
                "اكتب المحتوى بهذه الأداة، واحفظ في النهاية بـ "
                "press_keys بقيمة ctrl+s. النص يُكتب عند موضع المؤشر "
                "الحالي، فتأكّد من التركيز وموضع المؤشر قبل الكتابة."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "النص المراد كتابته في النافذة المركّزة",
                    }
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_keys",
            "description": (
                "ضغط مفتاح أو تركيبة مفاتيح على جهاز المستخدم داخل "
                "النافذة المركّزة: enter للإدخال/الإرسال، tab للانتقال "
                "بين حقول نموذج (و shift+tab للرجوع)، ctrl+s للحفظ، "
                "ctrl+a لتحديد الكل، ctrl+c و ctrl+v للنسخ واللصق، "
                "alt+f4 لإغلاق النافذة. القيمة سلسلة واحدة مثل «ctrl+s» "
                "أو «enter» أو «tab»: مفاتيح التعديل (ctrl/alt/shift/win) "
                "تُفصَل بعلامة + عن المفتاح الأخير، والمفتاح الأخير حرف "
                "أو رقم أو اسم مفتاح (enter, esc, tab, space, "
                "backspace, delete, insert, home, end, pageup, "
                "pagedown, up, down, left, right, f1 حتى f12, "
                "printscreen, win)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "string",
                        "description": (
                            "المفتاح أو التركيبة، مثل ctrl+s أو enter "
                            "أو shift+tab"
                        ),
                    }
                },
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_conversation",
            "description": (
                "امسح كامل محادثة هذا البوت مع المستخدم نهائياً (كل الرسائل "
                "السابقة تُحذف ولا يمكن استرجاعها). استعملها فقط عندما يطلب "
                "المستخدم صراحة حذف/مسح المحادثات السابقة أو البدء من جديد. "
                "المسح نهائي، ويتطلب موافقة المستخدم دائماً مهما كان وضع البوت."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "use_skill",
            "description": (
                "اقرأ التعليمات الكاملة لمهارة محفوظة باسمها. فهرس "
                "مهاراتك (الاسم والوصف) يظهر في بداية محادثتك؛ فقبل "
                "أي مهمة مألوفة — كتابة محضر، الردّ على رسالة رسمية، "
                "تنسيق جدول — اقرأ مهارة الموضوع بهذه الأداة واتّبع "
                "تعليماتها حرفياً، فهي ما علّمه المدير أو ما تعلّمته "
                "من قبل. الاسم يجب أن يطابق اسماً من الفهرس."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "اسم المهارة كما في الفهرس",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_skill",
            "description": (
                "احفظ مهارة جديدة (أو حدّث قائمة بنفس الاسم) في "
                "ذاكرتك الدائمة: إجراء متكرّر باسمه ووصفه وتعليماته "
                "الكاملة خطوة بخطوة. استعملها عندما يعلّمك المدير "
                "إجراءً أو صيغة عمل («من الآن فصاعداً اكتب المحضر "
                "هكذا…»)، أو عندما تنجز مهمة بطريقة تستحق أن تتكرّر "
                "بنفس الجودة. المهارة المحفوظة تبقى بعد إغلاق "
                "البرنامج وتظهر في فهرسك أنت وكل البوتات."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "اسم قصير مميّز للمهارة",
                    },
                    "description": {
                        "type": "string",
                        "description": "وصف بسطر واحد: متى تُستعمل",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "التعليمات الكاملة خطوة بخطوة",
                    },
                },
                "required": ["name", "instructions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": (
                "احفظ حقيقة دائمة عن عمل المدير في ذاكرتك (تفضيل، "
                "اسم، موعد ثابت، قاعدة عمل…) لتتذكّرها في كل محادثة "
                "قادمة — ذاكرتك تظهر في بداية محادثتك. استعملها "
                "عندما يخبرك المدير بشيء يجب ألا تنساه، أو عندما "
                "تستنتج من العمل قاعدة ثابتة عنده. لا تحفظ أسراراً "
                "ولا كلمات مرور أبداً."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "الحقيقة الدائمة بجملة واحدة واضحة",
                    }
                },
                "required": ["fact"],
            },
        },
    },
]

TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


def _urllib_transport(url: str, headers: dict, payload: dict, timeout: float = 120.0) -> dict:
    """النقل الافتراضي: POST JSON عبر urllib وإعادة الردّ مُحلَّلاً."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        raise ProviderError(f"HTTP {exc.code} من المزوّد: {body}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"تعذّر الاتصال بالمزوّد: {exc.reason}") from exc


class OpenAICompatibleProvider:
    """عميل محادثة متوافق مع OpenAI (chat/completions)."""

    # يقبل أجزاء الصور في الرسائل (image_url) — القبول الفعلي رهين
    # بالنموذج المختار: النموذج النصّي يرفض الطلب بخطأ 400 فيتدهور
    # المحرّك بأمان إلى نصّ إرشادي (انظر engine._is_vision_rejection).
    supports_vision = True

    def __init__(self, config: ProviderConfig, api_key: str, transport=None):
        self.config = config
        self.api_key = api_key
        self.transport = transport or _urllib_transport

    def chat(self, messages: list[dict], model: str, tools: list | None = None) -> ChatResult:
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload: dict = {"model": model, "messages": messages}
        if tools:
            payload["tools"] = tools
        data = self.transport(url, headers, payload)
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"ردّ غير متوقع من المزوّد: {str(data)[:300]}") from exc
        result = ChatResult(text=message.get("content") or "")
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args else {}
                except ValueError:
                    args = {}
            result.tool_calls.append(
                ToolCall(id=raw.get("id", ""), name=fn.get("name", ""), arguments=args)
            )
        return result


class GeminiProvider:
    """عميل Google Gemini (generateContent). المحادثة النصية في الخطوة 1؛
    طلبات الأدوات لا تُمرَّر له (تبقى عبر المزوّدات المتوافقة مع OpenAI)."""

    # نماذج Gemini ترى الصور: أجزاء image_url في الرسائل تُترجَم
    # إلى inline_data في _convert.
    supports_vision = True

    def __init__(self, config: ProviderConfig, api_key: str, transport=None):
        self.config = config
        self.api_key = api_key
        self.transport = transport or _urllib_transport

    @staticmethod
    def _parts_from_content(content) -> list[dict]:
        """أجزاء Gemini من محتوى رسالة: نصّ عادي كما هو، وقائمة
        أجزاء (شكل OpenAI) تُترجَم: text ← text، وimage_url ذات
        عنوان data: ← inline_data (نوع MIME + بيانات base64)."""
        if isinstance(content, str):
            return [{"text": content}] if content else []
        parts: list[dict] = []
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type")
                if ptype == "text":
                    if part.get("text"):
                        parts.append({"text": part["text"]})
                elif ptype == "image_url":
                    url = (part.get("image_url") or {}).get("url", "")
                    if url.startswith("data:") and "," in url:
                        header, data = url.split(",", 1)
                        mime = header[5:].split(";")[0] or "image/jpeg"
                        parts.append(
                            {"inline_data": {"mime_type": mime, "data": data}}
                        )
        return parts

    def _convert(self, messages: list[dict]) -> tuple[str, list[dict]]:
        system_parts: list[str] = []
        contents: list[dict] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content")
            if role == "system":
                text = content if isinstance(content, str) else ""
                if text:
                    system_parts.append(text)
            elif role == "assistant":
                parts = self._parts_from_content(content)
                if parts:
                    contents.append({"role": "model", "parts": parts})
            elif role in ("user", "tool"):
                parts = self._parts_from_content(content)
                if parts:
                    contents.append({"role": "user", "parts": parts})
        return "\n".join(system_parts), contents

    def chat(self, messages: list[dict], model: str, tools: list | None = None) -> ChatResult:
        system_text, contents = self._convert(messages)
        url = (
            self.config.base_url.rstrip("/")
            + f"/models/{model}:generateContent"
        )
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        payload: dict = {"contents": contents}
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        data = self.transport(url, headers, payload)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"ردّ غير متوقع من Gemini: {str(data)[:300]}") from exc
        return ChatResult(text=text)


class MockProvider:
    """مزوّد للاختبارات: يردّ من قائمة مكتوبة ويسجّل ما وصله. بلا شبكة."""

    def __init__(self, scripted: list[ChatResult] | None = None):
        self.scripted: list[ChatResult] = list(scripted or [])
        self.calls: list[dict] = []

    def chat(self, messages: list[dict], model: str, tools: list | None = None) -> ChatResult:
        self.calls.append(
            {"messages": list(messages), "model": model, "tools": tools}
        )
        if self.scripted:
            return self.scripted.pop(0)
        return ChatResult(text="ردّ تجريبي")


def build_provider(config: ProviderConfig, api_key: str, transport=None):
    """مصنع المزوّدين بحسب نوع الإعداد."""
    if config.kind == "gemini":
        return GeminiProvider(config, api_key, transport=transport)
    if config.kind == "mock":
        return MockProvider()
    return OpenAICompatibleProvider(config, api_key, transport=transport)
