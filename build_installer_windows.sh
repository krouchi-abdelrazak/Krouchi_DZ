#!/usr/bin/env bash
# Krouchi_DZ — build the Windows NSIS installer (Krouchi_DZ_Setup_vX.Y.Z.exe).
#
# Steps:
#   1. Assemble the portable bundle via build_exe_windows.sh
#      (launcher exe + portable Python + Pillow) into Krouchi_DZ_Windows/.
#   2. Add the shared assets beside run_gui.py: the bot avatar gallery
#      (assets/avatars/bot_*.png — never the raw/ sources) and the app icon.
#   3. Compile installer.nsi with makensis (per-user install, no UAC).
#
# The user's data directory (~/.krouchi_dz) is not part of the bundle and
# is never touched by the installer or the uninstaller.
set -euo pipefail
cd "$(dirname "$0")"

VERSION="${VERSION:-3.4.0}"

bash build_exe_windows.sh

mkdir -p Krouchi_DZ_Windows/assets/avatars
cp assets/avatars/bot_*.png Krouchi_DZ_Windows/assets/avatars/
cp assets/icon.ico Krouchi_DZ_Windows/assets/icon.ico

makensis -DVERSION="$VERSION" installer.nsi

echo "DONE: $(pwd)/Krouchi_DZ_Setup_v${VERSION}.exe"
