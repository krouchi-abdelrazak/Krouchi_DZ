; Krouchi_DZ — Windows installer (NSIS)
; By Krouchi Abderrazak
;
; Per-user install (no admin / no UAC) into %LOCALAPPDATA%\Krouchi_DZ.
; The user's data directory (%USERPROFILE%\.krouchi_dz — bots, keys,
; conversations) is NEVER touched by install, upgrade, or uninstall.

Unicode True

!ifndef VERSION
  !define VERSION "3.4.0"
!endif
!ifndef BUNDLE
  !define BUNDLE "Krouchi_DZ_Windows"
!endif

!include "MUI2.nsh"

Name "Krouchi_DZ"
Caption "Krouchi_DZ ${VERSION} Setup"
OutFile "Krouchi_DZ_Setup_v${VERSION}.exe"
InstallDir "$LOCALAPPDATA\Krouchi_DZ"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Icon "assets\icon.ico"
UninstallIcon "assets\icon.ico"

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Krouchi_DZ"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "Krouchi_DZ Setup"
VIAddVersionKey "CompanyName" "Krouchi Abderrazak"
VIAddVersionKey "LegalCopyright" "Krouchi Abderrazak"

; ---------------------------------------------------------------------------
; Wizard pages (English chrome; the app itself is bilingual ar/en)
; ---------------------------------------------------------------------------
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\Krouchi_DZ.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Run Krouchi_DZ"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ---------------------------------------------------------------------------
; Install
; ---------------------------------------------------------------------------
Section "Krouchi_DZ (required)" SecProgram
  SectionIn RO
  SetOutPath "$INSTDIR"

  ; Clear the previous program files (data lives in ~/.krouchi_dz, not here).
  RMDir /r "$INSTDIR\krouchi_dz"
  RMDir /r "$INSTDIR\pwa"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\assets"
  Delete "$INSTDIR\Krouchi_DZ.exe"
  Delete "$INSTDIR\run_gui.py"
  Delete "$INSTDIR\run_windows.bat"
  Delete "$INSTDIR\providers.json"
  Delete "$INSTDIR\README_WINDOWS.txt"

  ; Copy the full portable bundle.
  File /r "${BUNDLE}\*"

  ; Shortcuts: Desktop + Start Menu.
  CreateShortcut "$DESKTOP\Krouchi_DZ.lnk" "$INSTDIR\Krouchi_DZ.exe" "" \
    "$INSTDIR\assets\icon.ico" 0 SW_SHOWNORMAL "" "Krouchi_DZ"
  CreateDirectory "$SMPROGRAMS\Krouchi_DZ"
  CreateShortcut "$SMPROGRAMS\Krouchi_DZ\Krouchi_DZ.lnk" \
    "$INSTDIR\Krouchi_DZ.exe" "" "$INSTDIR\assets\icon.ico" 0 \
    SW_SHOWNORMAL "" "Krouchi_DZ"
  CreateShortcut "$SMPROGRAMS\Krouchi_DZ\Uninstall.lnk" \
    "$INSTDIR\uninstall.exe" "" "$INSTDIR\assets\icon.ico" 0 \
    SW_SHOWNORMAL "" "Uninstall Krouchi_DZ"

  ; Uninstaller + Add/Remove Programs entry (per-user, HKCU).
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krouchi_DZ" \
    "DisplayName" "Krouchi_DZ"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krouchi_DZ" \
    "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krouchi_DZ" \
    "Publisher" "Krouchi Abderrazak"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krouchi_DZ" \
    "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krouchi_DZ" \
    "DisplayIcon" "$INSTDIR\assets\icon.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krouchi_DZ" \
    "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krouchi_DZ" \
    "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krouchi_DZ" \
    "NoRepair" 1
SectionEnd

Section "Start with Windows" SecStartup
  ; Same Startup-folder shortcut the app's own toggle manages.
  CreateShortcut "$APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Krouchi_DZ.lnk" \
    "$INSTDIR\Krouchi_DZ.exe" "" "$INSTDIR\assets\icon.ico" 0 \
    SW_SHOWNORMAL "" "Krouchi_DZ"
SectionEnd

LangString DESC_SecProgram ${LANG_ENGLISH} \
  "The Krouchi_DZ program files, shortcuts, and uninstaller."
LangString DESC_SecStartup ${LANG_ENGLISH} \
  "Start Krouchi_DZ automatically when you sign in to Windows."
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecProgram} $(DESC_SecProgram)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartup} $(DESC_SecStartup)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ---------------------------------------------------------------------------
; Uninstall — program files only; ~/.krouchi_dz data is preserved on purpose.
; ---------------------------------------------------------------------------
Section "Uninstall"
  Delete "$DESKTOP\Krouchi_DZ.lnk"
  Delete "$APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Krouchi_DZ.lnk"
  Delete "$SMPROGRAMS\Krouchi_DZ\Krouchi_DZ.lnk"
  Delete "$SMPROGRAMS\Krouchi_DZ\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Krouchi_DZ"

  RMDir /r "$INSTDIR\krouchi_dz"
  RMDir /r "$INSTDIR\pwa"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\assets"
  Delete "$INSTDIR\Krouchi_DZ.exe"
  Delete "$INSTDIR\run_gui.py"
  Delete "$INSTDIR\run_windows.bat"
  Delete "$INSTDIR\providers.json"
  Delete "$INSTDIR\README_WINDOWS.txt"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krouchi_DZ"
SectionEnd
