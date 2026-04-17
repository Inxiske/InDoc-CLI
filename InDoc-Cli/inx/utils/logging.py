import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional


def error_log_path() -> Path:
    return Path.home() / ".indoc" / "logs" / "error.log"


def log_error(message: str, exc: Optional[BaseException] = None) -> None:
    try:
        log_path = error_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{ts}] {message}"]
        if exc is not None:
            lines.append(f"Exception: {type(exc).__name__}: {exc}")
            lines.append(traceback.format_exc())
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        return
