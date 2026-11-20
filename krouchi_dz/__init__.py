"""Krouchi_DZ — وكيل شخصي محلي أولاً (المحرّك + الواجهة الرسومية).

برنامج أصلي مكتوب من الصفر، بأمان صارم افتراضياً: وسيط موافقات
يفشل مُغلقاً، ومفاتيح خارج القاعدة.
الخطوة 1: المحرّك (engine.py) — الخطوة 2: الواجهة (gui.py، Tkinter) —
الإصدار الثاني: خادم مرافقة الهاتف (server.py) يربط تطبيق الهاتف
ببوتات الحاسوب عبر سجلّ الموافقات المشترك نفسه —
الإصدار الثالث: واجهة بلغتين (i18n.py) — العربية والإنجليزية،
بتبديل فوري من النافذة نفسها واتجاه تخطيط معكوس بينهما.
الإصدار 3.2: تحكّم الهاتف الكلي بالحاسوب (control.py: ملفات، أوامر،
طاقة، طباعة، حافظة، رفع) ومهام بوتات خلفية طويلة (tasks.py)
بمحرّكات مخصّصة وسجلّ الموافقات المشترك نفسه.
"""

from .broker import (
    ApprovalBroker,
    ApprovalRequest,
    BrokerDecision,
    PendingApproval,
    PendingApprovals,
    request_summary,
)
from .config import ProviderConfig, load_providers
from .db import Database
from .discovery import (
    DiscoveryError,
    DiscoveryResult,
    classify_kind,
    discover_models,
    normalize_base_url,
)
from .engine import ChatCancelled, ChatEngine, default_data_dir
from .i18n import get_lang, is_rtl, set_lang, t
from .providers import (
    ChatResult,
    GeminiProvider,
    MockProvider,
    OpenAICompatibleProvider,
    ProviderError,
    ToolCall,
    build_provider,
)
from .secrets import SecretsStore
from .tasks import TaskManager, TaskStore

__version__ = "3.3.1"

__all__ = [
    "ApprovalBroker",
    "ApprovalRequest",
    "BrokerDecision",
    "ChatCancelled",
    "ChatEngine",
    "ChatResult",
    "Database",
    "DiscoveryError",
    "DiscoveryResult",
    "GeminiProvider",
    "MockProvider",
    "OpenAICompatibleProvider",
    "PendingApproval",
    "PendingApprovals",
    "ProviderConfig",
    "ProviderError",
    "SecretsStore",
    "TaskManager",
    "TaskStore",
    "ToolCall",
    "build_provider",
    "classify_kind",
    "default_data_dir",
    "discover_models",
    "get_lang",
    "is_rtl",
    "load_providers",
    "normalize_base_url",
    "request_summary",
    "set_lang",
    "t",
]
