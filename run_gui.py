#!/usr/bin/env python3
"""مشغّل Krouchi_DZ الرسومي (الخطوة 2).

التشغيل:  python3 run_gui.py
يفتح التطبيق على مجلد البيانات الافتراضي ~/.krouchi_dz
(مرّر مساراً آخر كوسيط أول إن أردت مجلد بيانات مختلفاً).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from krouchi_dz.gui import main

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
