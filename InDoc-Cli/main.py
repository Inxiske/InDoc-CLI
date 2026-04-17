"""
InDoc-CLI: Main Entry Point.

Pure entry point. Handles Smart Boot Protocol and command routing.
No business logic here - only orchestration.
Smart Boot Protocol:
  - Scenario A: Ollama not found -> Setup screen
  - Scenario B: Ollama installed but OFFLINE -> Auto-start attempt
  - Scenario C: Ollama ONLINE -> System Ready
"""

import sys
import time
import os
import json
from pathlib import Path
from typing import Optional, List

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from cli.commands import router, CommandRouter
from core.ollama_engine import OllamaEngine


APP_NAME = "InDoc-CLI"
VERSION = "1.4.0"

console = Console()

def _global_config_path() -> Path:
    return Path.home() / ".indoc" / "config.json"


def _ensure_global_config_file() -> Path:
    p = _global_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(json.dumps({}, indent=2), encoding="utf-8")
    return p


def _load_global_config_dict() -> dict:
    p = _ensure_global_config_file()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _write_global_config_dict(data: dict) -> None:
    p = _ensure_global_config_file()
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _handle_rpc_global_flags(args: List[str]) -> List[str]:
    if "--rpc-off" not in args:
        return args
    data = _load_global_config_dict()
    data["discord_rpc"] = False
    _write_global_config_dict(data)
    console.print("[InDoc] Discord RPC disabled.")
    return [a for a in args if a != "--rpc-off"]


def _maybe_prompt_rpc_opt_in(args: List[str]) -> None:
    if not sys.stdin.isatty():
        return
    if args and args[0] in ("--auto-gen", "--auto-scan"):
        return
    data = _load_global_config_dict()
    if "discord_rpc" in data:
        return
    try:
        resp = input("Enable Discord Rich Presence to showcase your engineering activity? [y/N] ").strip().lower()
    except Exception:
        resp = ""
    enabled = resp in ("y", "yes")
    data["discord_rpc"] = enabled
    _write_global_config_dict(data)


def _rpc_enabled() -> bool:
    data = _load_global_config_dict()
    return data.get("discord_rpc") is True


def check_system_lock() -> bool:
    temp_dir = os.environ.get("TEMP") or os.environ.get("TMP") or str(Path.cwd())
    lock_path = Path(temp_dir) / ".inx_lockcheck.tmp"
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


def wait_for_system_clear(timeout_s: int = 30, poll_s: int = 2) -> None:
    if not check_system_lock():
        return

    start = time.monotonic()
    with console.status(
        "[yellow][!] Security scanner detected. Waiting for system to clear...[/yellow]",
        spinner="dots"
    ):
        while time.monotonic() - start < timeout_s:
            time.sleep(poll_s)
            if not check_system_lock():
                break

    if not check_system_lock():
        console.print("[green][OK] System clear. Starting...[/green]")
    else:
        console.print("[yellow][!] Warning: System scan taking too long. Proceeding anyway...[/yellow]")


def smart_boot() -> str:
    """
    Execute Smart Boot Protocol.

    Returns:
        Scenario code: 'A' (not installed), 'B' (offline), 'C' (online)
    """
    engine = router.engine

    if not engine.is_ollama_installed():
        return 'A'

    is_online, _, _ = engine.check_connection()
    if not is_online:
        return 'B'

    return 'C'


def show_scenario_a() -> None:
    """
    Scenario A: Ollama not found in PATH.
    Show setup and installation screen.
    """
    console.print(Panel(
        Text.from_markup(f"[bold red]SETUP & INSTALLATION REQUIRED[/bold red]\n\n"
                        f"[yellow]Ollama binary was not found in your system PATH.[/yellow]\n"
                        f"[dim]Follow the instructions below to complete setup.[/dim]"),
        border_style="red",
        expand=False
    ))
    console.print()
    console.print("[bold cyan]Available Options:[/bold cyan]")
    console.print()
    console.print("  [yellow]1.[/yellow] [bold]inx install ollama[/bold]     - Install Ollama engine")
    console.print("     [dim]Opens download page or automated install[/dim]")
    console.print()
    console.print("  [yellow]2.[/yellow] [bold]inx help[/bold]              - View all commands")
    console.print("     [dim]Documentation and usage guide[/dim]")
    console.print()


def show_scenario_b() -> None:
    """
    Scenario B: Ollama installed but service not running.
    Attempt auto-start and show status.
    """
    console.print(Panel(
        Text.from_markup("[yellow][!] Ollama is installed but not running.[/yellow]\n"
                        "[dim]Attempting to start engine...[/dim]"),
        border_style="yellow",
        expand=False
    ))
    console.print()

    success, msg = router.engine.try_start_service()

    if success:
        console.print("[dim]Starting Ollama service in background...[/dim]")
        console.print("[dim]Verifying connection...[/dim]")

        for i in range(3):
            time.sleep(1)
            is_online, status_msg, model = router.check_status()
            if is_online:
                console.print(f"[green][OK] {status_msg}[/green]")
                if model:
                    console.print(f"[dim]Active Model:[/dim] [cyan]{model}[/cyan]")
                return

        console.print("[yellow]Service started but verification pending.[/yellow]")
        console.print("[dim]Run 'inx status' to check again.[/dim]")
    else:
        console.print(f"[red][!] {msg}[/red]")
        console.print("[dim]Try running 'ollama serve' manually in a terminal.[/dim]")
        console.print("[dim]Or use 'inx install ollama' to reinstall.[/dim]")


def show_scenario_c(is_online: bool, active_model: Optional[str]) -> None:
    """
    Scenario C: Ollama is online. Show System Ready dashboard.

    Args:
        is_online: Whether Ollama is connected.
        active_model: The active model name from API.
    """
    status_text = "[green]ONLINE[/green]"
    model_display = active_model if active_model else "None"

    info_table = Table.grid(padding=(0, 2))
    info_table.add_column(justify="left")
    info_table.add_column(justify="left")
    info_table.add_row("[dim]Status:[/dim]", status_text)
    info_table.add_row("[dim]Active Model:[/dim]", f"[cyan]{model_display}[/cyan]")
    info_table.add_row("[dim]User:[/dim]", f"[yellow]{router.username}[/yellow]")

    actions_table = Table.grid(padding=(0, 1))
    actions_table.add_column(justify="left")
    actions_table.add_column(justify="left")
    actions_table.add_row("[yellow]inx gen <path>[/yellow]", "[dim]Document a file[/dim]")
    actions_table.add_row("[yellow]inx scan <path>[/yellow]", "[dim]Scan a project[/dim]")
    actions_table.add_row("[yellow]inx model gallery[/yellow]", "[dim]Browse models[/dim]")
    actions_table.add_row("[yellow]inx status[/yellow]", "[dim]Check connection[/dim]")

    console.print(Panel(
        info_table,
        title=f"[bold cyan]{APP_NAME} v{VERSION}[/bold cyan] - System Ready",
        border_style="blue",
        expand=False
    ))
    console.print(Panel(
        actions_table,
        title="[bold]Quick Actions[/bold]",
        border_style="green",
        expand=False
    ))
    console.print()
    if _rpc_enabled():
        try:
            from rpc_manager import set_active_model, set_idle
            if active_model:
                set_active_model(active_model)
            set_idle(router.engine.prompt_mode)
        except Exception:
            pass


def run_interactive() -> None:
    """
    Run the interactive shell loop with Smart Boot Protocol.
    """
    router.clear_screen()

    console.print(Panel(
        Text.from_markup(f"[bold]{APP_NAME}[/bold] [dim]v{VERSION}[/dim] | [cyan]Engine: Ollama[/cyan] | [yellow]Command Prefix: 'inx'[/yellow]"),
        border_style="blue",
        expand=False
    ))
    console.print("-" * 60, style="dim")
    console.print()

    scenario = smart_boot()

    if scenario == 'A':
        show_scenario_a()
    elif scenario == 'B':
        show_scenario_b()
        router.check_status()
        if router.is_online:
            show_scenario_c(router.is_online, router.active_model)
    else:
        router.check_status()
        show_scenario_c(router.is_online, router.active_model)

    if _rpc_enabled():
        try:
            from rpc_manager import set_idle
            set_idle(router.engine.prompt_mode)
        except Exception:
            pass

    while True:
        try:
            prompt = f"(inx) [bold cyan]{router.username}[/bold cyan]@system > "
            user_input = console.input(prompt)

            if not user_input.strip():
                continue

            success, message = route_input(user_input)

            if not success:
                console.print(f"[red]{message}[/red]")
            if _rpc_enabled():
                try:
                    from rpc_manager import set_idle
                    set_idle(router.engine.prompt_mode)
                except Exception:
                    pass

        except KeyboardInterrupt:
            console.print("\n[dim]Use 'exit' to close properly.[/dim]")
        except EOFError:
            console.print("\n[dim]Session ended.[/dim]")
            break


def route_input(raw_input: str) -> tuple:
    """
    Route user input to appropriate command handler.
    Supports only 'inx' prefix.

    Args:
        raw_input: The raw user input string.

    Returns:
        Tuple of (success, message).
    """
    cmd_input = raw_input.strip()
    cmd_lower = cmd_input.lower()

    if cmd_lower == "exit":
        console.print("[dim]Shutting down...[/dim]")
        sys.exit(0)

    prefix = "inx "
    if cmd_lower.startswith(prefix):
        parts = cmd_input[len(prefix):].strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1].split() if len(parts) > 1 else []
        return router.dispatch(cmd, args)

    if cmd_lower == "inx":
        return router.dispatch("help", [])

    return False, "[!] Unknown command. Type 'inx help' for a list of valid actions."


def run_direct(args: List[str]) -> None:
    """
    Run a single command directly (non-interactive).

    Args:
        args: Command line arguments.
    """
    if not args:
        run_interactive()
        return

    cmd = args[0].lower()
    cmd_args = args[1:] if len(args) > 1 else []

    if cmd in ("install",) and cmd_args and cmd_args[0].lower() == "ollama":
        success, msg = router.dispatch("install", cmd_args[1:])
        if not success:
            console.print(f"[red]{msg}[/red]")
        return

    success, msg = router.dispatch(cmd, cmd_args)
    if not success:
        console.print(f"[red]{msg}[/red]")


def _hold_terminal_for_error() -> None:
    """Keep terminal open so user can read auto-pilot errors."""
    try:
        console.print("[dim]Press Enter to close...[/dim]")
        input()
    except Exception:
        time.sleep(15)


def run_autopilot(mode: str, raw_target: str) -> None:
    """
    Run auto-pilot flow for shell integration.

    Args:
        mode: "gen" or "scan".
        raw_target: File or directory path from shell.
    """
    target = os.path.abspath(os.path.expanduser(raw_target.strip().strip('"')))
    console.print(f"[bold cyan][SYSTEM][/bold cyan] InDoc Initialized for: {target}")

    # Use the same boot protocol as manual execution, but with preloaded target.
    scenario = smart_boot()
    if scenario == 'A':
        show_scenario_a()
        console.print("[bold red][!] Ollama engine not found. Please start the engine first.[/bold red]")
        _hold_terminal_for_error()
        return
    elif scenario == 'B':
        show_scenario_b()
        router.check_status()
        if not router.is_online:
            console.print("[bold red][!] Ollama engine not found. Please start the engine first.[/bold red]")
            _hold_terminal_for_error()
            return
    else:
        router.check_status()

    cmd = "gen" if mode == "gen" else "scan"
    success, msg = router.dispatch(cmd, [target])
    if success:
        console.print("[bold green][OK] Documentation generated successfully.[/bold green]")
        try:
            input("\nPress ENTER to close...")
        except Exception:
            time.sleep(15)
    else:
        console.print(f"[red]{msg}[/red]")
        _hold_terminal_for_error()


def main() -> None:
    """
    Application entry point.
    """
    args = sys.argv[1:]
    args = _handle_rpc_global_flags(args)
    _maybe_prompt_rpc_opt_in(args)
    force_mode = False
    if "--force" in args:
        force_mode = True
        args = [a for a in args if a != "--force"]
    if args and args[0] in ("--auto-gen", "--auto-scan"):
        if len(args) < 2:
            console.print("[red][!] Missing target path for auto mode.[/red]")
            _hold_terminal_for_error()
            return
        force_mode = True
        mode = "gen" if args[0] == "--auto-gen" else "scan"
        run_autopilot(mode, args[1])
        return

    if args and args[0] == "--list-modes":
        run_direct(["list-modes"])
        return

    if not force_mode:
        wait_for_system_clear()
    if args:
        run_direct(args)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
