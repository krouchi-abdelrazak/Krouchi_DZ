"""مخزن الأسرار في Krouchi_DZ.

مفاتيح API تُحفظ في ملف JSON منفصل (secrets.json داخل مجلد البيانات)
بصلاحيات مقيّدة 0600 — لا تدخل قاعدة البيانات ولا ملف الإعدادات أبداً.
القاعدة والإعدادات لا تحملان سوى اسم المرجع (secret_ref) مثل "openrouter".
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class SecretsStore:
    """قراءة/كتابة مفاتيح API في ملف محلي محمي بصلاحيات الملف."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    # -- داخلي ---------------------------------------------------------
    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, self.path)
        self._restrict_permissions()

    def _restrict_permissions(self) -> None:
        # على Windows صلاحيات chmod محدودة؛ نحاول على أية حال دون أن نفشل.
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    # -- واجهة عامة ----------------------------------------------------
    def get(self, ref: str) -> str:
        """يعيد المفتاح المرتبط بالمرجع، أو سلسلة فارغة إن لم يوجد."""
        return str(self._read().get(ref, "") or "")

    def has(self, ref: str) -> bool:
        return bool(self.get(ref))

    def set(self, ref: str, value: str) -> None:
        data = self._read()
        data[ref] = value
        self._write(data)

    def delete(self, ref: str) -> None:
        data = self._read()
        data.pop(ref, None)
        self._write(data)

    def refs(self) -> list[str]:
        """أسماء المراجع التي لها مفتاح محفوظ (دون القيم)."""
        return sorted(k for k, v in self._read().items() if v)
