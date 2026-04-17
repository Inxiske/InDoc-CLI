import os
import time
from pathlib import Path
from typing import Optional

from rich.console import Console


def check_system_lock(work_dir: Optional[Path] = None) -> bool:
    lock_path = (work_dir or Path.cwd()) / ".inx_lockcheck.tmp"
    f = None
    try:
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
        f = os.fdopen(fd, "r+")
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return False
    except (PermissionError, OSError):
        return True
    finally:
        try:
            if f is not None:
                f.close()
        except Exception:
            pass
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def wait_for_system_clear(console: Console, timeout_s: int = 30, poll_s: int = 2, work_dir: Optional[Path] = None) -> None:
    if not check_system_lock(work_dir=work_dir):
        return

    start = time.monotonic()
    with console.status(
        "[yellow][!] Security scanner detected. Waiting for system to clear...[/yellow]",
        spinner="dots"
    ):
        while time.monotonic() - start < timeout_s:
            time.sleep(poll_s)
            if not check_system_lock(work_dir=work_dir):
                break

    if not check_system_lock(work_dir=work_dir):
        console.print("[green][OK] System clear. Starting...[/green]")
    else:
        console.print("[yellow][!] Warning: System scan taking too long. Proceeding anyway...[/yellow]")
