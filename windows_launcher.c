/* Krouchi_DZ — Windows launcher (x86_64-windows-gnu, GUI subsystem)
 *
 * Runs the bundled portable Python (python\pythonw.exe) with run_gui.py
 * from the same folder as this .exe, without opening a console window.
 * No Python installation is needed on the target PC.
 *
 * Build (Linux cross-compile):
 *   zig cc -target x86_64-windows-gnu -Wl,--subsystem,windows \
 *     windows_launcher.c -o Krouchi_DZ.exe
 *
 * Same pattern as the WinBiblio / WinEcole / RGF Windows packages.
 */
#include <stdio.h>
#include <wchar.h>
#include <windows.h>

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nCmdShow) {
    (void)hInstance; (void)hPrevInstance; (void)lpCmdLine; (void)nCmdShow;

    wchar_t dir[MAX_PATH];
    if (GetModuleFileNameW(NULL, dir, MAX_PATH) == 0) {
        MessageBoxW(NULL, L"Cannot locate the program folder.",
                    L"Krouchi_DZ", MB_ICONERROR);
        return 1;
    }
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash) *slash = L'\0';

    wchar_t cmd[MAX_PATH * 3];
    /* pythonw.exe (no console) + the GUI entry script next to the exe. */
    if (swprintf(cmd, MAX_PATH * 3,
                 L"\"%s\\python\\pythonw.exe\" \"%s\\run_gui.py\"",
                 dir, dir) < 0) {
        MessageBoxW(NULL, L"Path too long.", L"Krouchi_DZ", MB_ICONERROR);
        return 1;
    }

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        MessageBoxW(NULL,
                    L"Could not start the bundled Python (python\\pythonw.exe).\n"
                    L"Make sure the whole folder was extracted, including the "
                    L"'python' subfolder.\n\n"
                    L"تعذّر تشغيل بايثون المدمج (python\\pythonw.exe).\n"
                    L"تأكد من فك ضغط المجلد كاملاً مع مجلد 'python'.",
                    L"Krouchi_DZ", MB_ICONERROR);
        return 1;
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return (int)code;
}
