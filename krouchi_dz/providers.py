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
            "description": "تشغيل أمر على جهاز المستخدم وإعادة خرجه",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "الأمر المراد تشغيله",
                    }
                },
                "required": ["command"],
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

    def __init__(self, config: ProviderConfig, api_key: str, transport=None):
        self.config = config
        self.api_key = api_key
        self.transport = transport or _urllib_transport

    def _convert(self, messages: list[dict]) -> tuple[str, list[dict]]:
        system_parts: list[str] = []
        contents: list[dict] = []
        for m in messages:
            role = m.get("role")
            text = m.get("content") or ""
            if role == "system":
                if text:
                    system_parts.append(text)
            elif role == "assistant":
                if text:
                    contents.append({"role": "model", "parts": [{"text": text}]})
            elif role in ("user", "tool"):
                if text:
                    contents.append({"role": "user", "parts": [{"text": text}]})
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
