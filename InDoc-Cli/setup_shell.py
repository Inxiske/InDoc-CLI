r"""
Register Windows shell context menu entries for InDoc.

Adds:
- HKEY_CLASSES_ROOT\*\shell\Open with InDoc\command
- HKEY_CLASSES_ROOT\Directory\shell\Open with InDoc\command
"""

import sys
from pathlib import Path
import winreg


def _set_default_value(root: int, key_path: str, value: str) -> None:
    with winreg.CreateKey(root, key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)


def register_shell() -> None:
    launcher_bat = (Path(__file__).resolve().parent / "inx_launcher.bat").resolve()

    # Use launcher BAT as a stable shell bridge for both files and directories.
    # Quoting ensures paths with spaces are passed correctly.
    file_cmd = f"cmd /k \"\\\"{launcher_bat}\\\" \\\"%1\\\"\""
    dir_cmd = f"cmd /k \"\\\"{launcher_bat}\\\" \\\"%1\\\"\""

    file_shell_key = r"*\shell\Open with InDoc"
    file_cmd_key = r"*\shell\Open with InDoc\command"
    dir_shell_key = r"Directory\shell\Open with InDoc"
    dir_cmd_key = r"Directory\shell\Open with InDoc\command"

    _set_default_value(winreg.HKEY_CLASSES_ROOT, file_shell_key, "Open with InDoc")
    _set_default_value(winreg.HKEY_CLASSES_ROOT, file_cmd_key, file_cmd)
    _set_default_value(winreg.HKEY_CLASSES_ROOT, dir_shell_key, "Open with InDoc")
    _set_default_value(winreg.HKEY_CLASSES_ROOT, dir_cmd_key, dir_cmd)

    print("[OK] InDoc shell integration installed.")
    print(f"     File command: {file_cmd}")
    print(f"     Dir command:  {dir_cmd}")


if __name__ == "__main__":
    try:
        register_shell()
    except PermissionError:
        print("[!] Permission denied while writing HKEY_CLASSES_ROOT.")
        print("    Run this script as Administrator.")
        raise
