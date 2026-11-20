#!/usr/bin/env bash
# بناء Krouchi_DZ Android يدوياً (نفس خط Raqmana_Fetch_DZ_Android):
# javac ← d8 ← aapt2 ← zip (resources.arsc مُخزَّنة) ← zipalign ← apksigner
set -euo pipefail

PROJ="$(cd "$(dirname "$0")" && pwd)"
SDK="$HOME/workspace/tools/android-sdk"
BT="$SDK/build-tools/34.0.0"
AJAR="$SDK/platforms/android-34/android.jar"
export JAVA_HOME="$HOME/workspace/tools/jdk"
export PATH="$JAVA_HOME/bin:$PATH"
VERSION="3.4.0"
OUT="$PROJ/Krouchi_DZ_v${VERSION}.apk"
BUILD="$PROJ/build"

rm -rf "$BUILD"
mkdir -p "$BUILD/classes" "$BUILD/dex" "$BUILD/stage"

echo "== javac =="
javac --release 8 -encoding UTF-8 -cp "$AJAR" -d "$BUILD/classes" \
  "$PROJ/src/dz/krouchi/app/MainActivity.java"

echo "== d8 =="
(cd "$BUILD/classes" && jar cf "$BUILD/classes.jar" .)
"$BT/d8" --lib "$AJAR" --output "$BUILD/dex" "$BUILD/classes.jar"

echo "== aapt2 compile (res: أيقونة المشغّل) =="
"$BT/aapt2" compile --dir "$PROJ/res" -o "$BUILD/res.zip"

echo "== aapt2 link (base.apk) =="
"$BT/aapt2" link -o "$BUILD/base.apk" -I "$AJAR" \
  --manifest "$PROJ/AndroidManifest.xml" \
  --min-sdk-version 24 --target-sdk-version 34 \
  "$BUILD/res.zip"

echo "== stage + zip (resources.arsc STORED — درس OPPO) =="
(cd "$BUILD/stage" && unzip -o -q "$BUILD/base.apk")
cp "$BUILD/dex/classes.dex" "$BUILD/stage/classes.dex"
cp -r "$PROJ/assets" "$BUILD/stage/assets"
python3 - "$BUILD/stage" "$BUILD/unsigned.apk" <<'PYEOF'
import os, sys, zipfile
stage, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w") as z:
    for root, _dirs, files in os.walk(stage):
        for name in sorted(files):
            full = os.path.join(root, name)
            arc = os.path.relpath(full, stage)
            # resources.arsc يجب أن تبقى مُخزَّنة غير مضغوطة وإلا رفض
            # بعض الأجهزة (OPPO) تثبيت الحزمة — كما حدث في Raqmana v1.0.7
            method = zipfile.ZIP_STORED if arc == "resources.arsc" else zipfile.ZIP_DEFLATED
            z.write(full, arc, compress_type=method)
print("unsigned.apk written")
PYEOF

echo "== zipalign =="
"$BT/zipalign" -f -v 4 "$BUILD/unsigned.apk" "$BUILD/aligned.apk" >/dev/null

echo "== keystore =="
if [ ! -f "$PROJ/debug.keystore" ]; then
  keytool -genkeypair -keystore "$PROJ/debug.keystore" \
    -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass android -keypass android \
    -dname "CN=Android Debug,O=Android,C=US" >/dev/null 2>&1
fi

echo "== apksigner =="
"$BT/apksigner" sign --ks "$PROJ/debug.keystore" \
  --ks-pass pass:android --key-pass pass:android \
  --out "$OUT" "$BUILD/aligned.apk"

echo "== verify =="
"$BT/apksigner" verify --verbose --print-certs "$OUT"
python3 - "$OUT" <<'PYEOF'
import sys, zipfile
apk = sys.argv[1]
with zipfile.ZipFile(apk) as z:
    info = z.getinfo("resources.arsc")
    assert info.compress_type == zipfile.ZIP_STORED, "resources.arsc مضغوطة!"
    # إزاحة بيانات resources.arsc يجب أن تكون محاذاة لـ 4 بايتات
    with open(apk, "rb") as f:
        f.seek(info.header_offset)
        hdr = f.read(30)
        nlen = int.from_bytes(hdr[26:28], "little")
        elen = int.from_bytes(hdr[28:30], "little")
        data_off = info.header_offset + 30 + nlen + elen
    assert data_off % 4 == 0, f"resources.arsc غير محاذاة: {data_off}"
    print(f"resources.arsc: STORED, data offset {data_off} (aligned ✓)")
print("entries:", [i.filename for i in zipfile.ZipFile(apk).infolist()])
PYEOF
ls -la "$OUT"
sha256sum "$OUT"
echo "DONE: $OUT"
