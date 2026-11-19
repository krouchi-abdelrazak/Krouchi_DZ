#!/bin/bash
# Build the Windows package for Krouchi_DZ (cross-compile from Linux)
# Usage: bash build_exe_windows.sh
#
# Same pattern as the WinBiblio / WinEcole / RGF Windows packages:
#   1. Cross-compiles windows_launcher.c with zig into a GUI-subsystem
#      .exe (PE32+ x86-64) that starts the bundled portable Python.
#   2. Assembles ./Krouchi_DZ_Windows/ :
#        Krouchi_DZ.exe, run_gui.py, krouchi_dz/ (the package),
#        providers.json (seed), python/ (portable Windows Python 3.12
#        + tkinter), README_WINDOWS.txt, run_windows.bat
#   3. Zips it as ./Krouchi_DZ_Windows.zip
#
# Requirements: zig and a copy of the portable Windows Python.
# Override with WIN_PYTHON_DIR=/path/to/python (a folder containing
# pythonw.exe with tkinter). Default: reuse the one shipped with the
# WinBiblio_DZ Windows package.
#
# NOTE: this Windows package was NOT tested on a real Windows machine
# (only that the launcher is a valid PE64 file). See README.md.
set -e
cd "$(dirname "$0")"

ZIG="${ZIG:-zig}"
if ! command -v "$ZIG" >/dev/null 2>&1; then
  if [ -x /home/hatch/tmp/zig-linux-x86_64-0.13.0/zig ]; then
    ZIG=/home/hatch/tmp/zig-linux-x86_64-0.13.0/zig
  else
    echo "zig is not installed. Get it from https://ziglang.org/download/" >&2
    exit 1
  fi
fi

if [ -z "${WIN_PYTHON_DIR:-}" ]; then
  for cand in \
    "$HOME/workspace/goals/winbiblio-dz/files/WinBiblio_DZ_Windows/python" \
    "../RGF_Builder_Windows/python"; do
    if [ -x "$cand/pythonw.exe" ]; then WIN_PYTHON_DIR="$cand"; break; fi
  done
fi
if [ -z "${WIN_PYTHON_DIR:-}" ] || [ ! -x "$WIN_PYTHON_DIR/pythonw.exe" ]; then
  echo "Portable Windows Python not found." >&2
  echo "Set WIN_PYTHON_DIR to a folder containing pythonw.exe (with tkinter)." >&2
  exit 1
fi
echo "Using portable Python: $WIN_PYTHON_DIR"

OUT="$(pwd)/Krouchi_DZ_Windows"
rm -rf "$OUT"
mkdir -p "$OUT"

echo "Compiling Windows launcher with zig..."
"$ZIG" cc -target x86_64-windows-gnu -Wl,--subsystem,windows \
  windows_launcher.c -o "$OUT/Krouchi_DZ.exe"
rm -f "$OUT"/*.pdb

cp -f run_gui.py providers.json "$OUT/"
mkdir -p "$OUT/krouchi_dz"
cp -f krouchi_dz/*.py "$OUT/krouchi_dz/"
cp -f krouchi_dz/icon.png "$OUT/krouchi_dz/" 2>/dev/null || true
cp -r "$WIN_PYTHON_DIR" "$OUT/python"

cat > "$OUT/README_WINDOWS.txt" <<'EOF'
Krouchi_DZ — وكيلك الشخصي المحلي — نسخة Windows المحمولة
============================================================
(لا تحتاج تثبيت Python)

كيف تشغّل البرنامج:
  1. فك ضغط هذا المجلد في أي مكان (سطح المكتب مثلاً).
  2. نقر مزدوج على Krouchi_DZ.exe.
  3. لا تحذف مجلد python ولا مجلد krouchi_dz ولا ملف run_gui.py،
     فالبرنامج يحتاجها كلها في نفس المجلد.

أول استعمال — أضف الـAPI أولاً:
  1. اضغط «إدخال API» وألصق عنوان الأساس (Base URL) ومفتاح الـAPI
     لأي مزوّد (OpenRouter أو Groq أو Z AI أو NVIDIA أو Gemini
     أو أي عنوان آخر متوافق)، ثم اضغط «اجلب النماذج»:
     البرنامج يجلب قائمة نماذج المزوّد بنفسه ويعرضها لك.
  2. أنشئ بوتاً جديداً: اختر المزوّد والنموذج واسم البوت.
  3. اختر البوت من القائمة وتحدّث معه.

الموافقات (مهم):
  - نمط الموافقة الافتراضي هو «اسأل»: قبل أن يكتب البوت أي ملف
    أو يشغّل أي أمر تظهر لك بطاقة موافقة فيها الإجراء وهدفه حرفياً.
  - إغلاق البطاقة أو انتهاء مهلتها يعني الرفض، ولا يُنفَّذ شيء.
  - لا تُبدّل النمط إلى «كامل» إلا لبوت تثق به تماماً.

ربط الهاتف (الإصدار الثاني):
  - اضغط «ربط الهاتف» في النافذة الرئيسية ثم «تشغيل الخادم».
  - في تطبيق Krouchi_DZ على هاتفك (على نفس شبكة Wi-Fi) أدخل أحد
    العناوين المعروضة (مثل http://192.168.1.10:8765) ورمز الربط
    كما يظهران في النافذة.
  - بعدها يحادث الهاتف بوتات هذا الحاسوب نفسها، وطلبات الموافقة
    تظهر على الحاسوب وعلى الهاتف معاً — الحسم من أيٍّ منهما يكفي.
  - رمز الربط سرّ: لا تشاركه إلا مع هاتفك، وبدّله من نفس النافذة
    متى شئت (القديم يتوقف فوراً).

لغة الواجهة (الإصدار الثالث):
  - الواجهة عربية أو إنجليزية: بدّل من منتقي اللغة أسفل القائمة
    الجانبية في النافذة الرئيسية — يتغيّر اتجاه التخطيط مع اللغة
    (القائمة يميناً في العربية، يساراً في الإنجليزية) ويُحفَظ
    اختيارك للمرة التالية.

بياناتك:
  - كل شيء محلي على جهازك في مجلد .krouchi_dz داخل مجلد المستخدم:
    قاعدة SQLite للمحادثات والبوتات وسجل التدقيق.
  - مفاتيح الـAPI تُحفظ في ملف أسرار منفصل، ولا تدخل قاعدة البيانات.

ما في المجلد:
  - Krouchi_DZ.exe : ملف التشغيل (انقر عليه نقراً مزدوجاً).
  - run_gui.py     : مشغّل الواجهة الرسومية.
  - krouchi_dz\    : حزمة البرنامج (المحرك، الاكتشاف، وسيط الموافقات).
  - providers.json : بذرة تعريفات المزوّدين.
  - python\        : نسخة Python 3.12 مدمجة (فيها tkinter).

ملاحظات:
  - نسخة Windows هذه 64-bit وتعمل على Windows 10 و Windows 11.
  - هذه الحزمة لم تُختبَر على Windows حقيقي (بُنيت بنفس نمط حزم
    WinBiblio وWinEcole وRGF)؛ إن واجهت مشكلة في التشغيل، شغّل
    run_windows.bat وأرسل رسالة الخطأ.
EOF

cp -f run_windows.bat "$OUT/" 2>/dev/null || true

cd "$(dirname "$OUT")"
rm -f Krouchi_DZ_Windows.zip
zip -qr Krouchi_DZ_Windows.zip Krouchi_DZ_Windows \
  -x "*/__pycache__/*"
echo "Done."
echo "  Folder: $OUT"
echo "  Zip:    $(pwd)/Krouchi_DZ_Windows.zip"
