"""
InDoc CLI wrapper entrypoint for shell integration.
"""

import os
import sys
import traceback
from typing import List, Tuple, Optional

from main import main


def _normalize_path(raw: str) -> str:
    cleaned = (raw or "").strip().strip('"').strip("'")
    return os.path.abspath(os.path.expanduser(cleaned))


def _prepare_args(argv: List[str]) -> List[str]:
    if not argv:
        return []

    cmd = argv[0].strip().lower()

    if cmd in ("gen", "scan"):
        # Robust path parsing: handles quoted and non-quoted inputs.
        raw_path = " ".join(argv[1:]).strip() if len(argv) > 1 else ""
        normalized = _normalize_path(raw_path)
        if raw_path:
            return ["--force", "--auto-gen" if cmd == "gen" else "--auto-scan", normalized]

    if cmd in ("--auto-gen", "--auto-scan"):
        if len(argv) > 1:
            normalized = _normalize_path(" ".join(argv[1:]))
            return ["--force", cmd, normalized]
        return argv

    if cmd == "--force":
        # Keep as-is if already forced.
        return argv

    # Catch-all: do not fail immediately, print raw command for diagnostics.
    print(f"[!] Command received: {sys.argv}. Parsing...")
    candidate = _normalize_path(" ".join(argv))
    if os.path.exists(candidate):
        inferred = "--auto-scan" if os.path.isdir(candidate) else "--auto-gen"
        return ["--force", inferred, candidate]
    return argv


def _is_known_cli_token(token: str) -> bool:
    t = (token or "").strip().lower()
    return t in {
        "gen", "scan",
        "--auto-gen", "--auto-scan",
        "--open-with", "--force",
        "status", "help", "about", "identity",
        "model", "install", "uninstall", "init", "stats", "clear", "dev",
    }


def _extract_external_target(argv: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect external shell invocation and return (mode, path).
    mode is "gen" or "scan".
    """
    if not argv:
        return None, None

    # Highest priority: explicit shell bridge flag.
    if "--open-with" in argv:
        idx = argv.index("--open-with")
        if idx + 1 >= len(argv):
            raise ValueError("Missing path after --open-with")
        raw = argv[idx + 1]
        path = _normalize_path(raw)
        mode = "scan" if os.path.isdir(path) else "gen"
        return mode, path

    # Secondary priority: direct path argument from Windows shell.
    first = (argv[0] or "").strip().strip('"').strip("'")
    if first and not _is_known_cli_token(first):
        path = _normalize_path(first)
        mode = "scan" if os.path.isdir(path) else "gen"
        return mode, path

    return None, None


def execute_gen(path: str) -> None:
    normalized = _normalize_path(path)
    sys.argv = [sys.argv[0], "--force", "--auto-gen", normalized]
    main()


def execute_scan(path: str) -> None:
    normalized = _normalize_path(path)
    sys.argv = [sys.argv[0], "--force", "--auto-scan", normalized]
    main()


if __name__ == "__main__":
    try:
        raw_args = sys.argv[1:]
        mode, path = _extract_external_target(raw_args)
        if mode and path:
            if not os.path.exists(path):
                print(f"[!] Command received: {sys.argv}. Parsing...")
                raise FileNotFoundError(f"Target path not found: {path}")
            command = f"{mode} {path}"
            print(f"[SYSTEM] Auto-executing: {command}")
            if mode == "scan":
                execute_scan(path)
            else:
                execute_gen(path)
        else:
            args = _prepare_args(raw_args)
            sys.argv = [sys.argv[0], *args]
            main()
    except Exception as e:
        print(f"[!] InDoc runtime error: {type(e).__name__}: {e}")
        traceback.print_exc()
        try:
            input("\n[!] Press ENTER to exit...")
        except Exception:
            pass
