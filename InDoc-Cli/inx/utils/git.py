import shutil
import subprocess
from pathlib import Path


def is_git_dirty(project_root: Path) -> bool:
    if not (project_root / ".git").exists():
        return False
    if shutil.which("git") is None:
        return False
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        out = (r.stdout or "").strip()
        return bool(out)
    except Exception:
        return False
