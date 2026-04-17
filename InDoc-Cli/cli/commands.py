"""
InDoc-CLI: Commands Module.

Contains all command implementations with strict argument handling.
Each command accepts args as list and returns a tuple (success, message).
"""

import os
import getpass
import ctypes
import webbrowser
import subprocess
import json
import time
import shutil
import concurrent.futures
import queue
from pathlib import Path
from typing import Tuple, List, Optional, Dict, Callable

from rich.console import Console
from rich.console import Group
from rich.live import Live
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn, TaskProgressColumn
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich import box

from core.ollama_engine import OllamaEngine, IndocError
from core.scanner import ProjectScanner
from rpc_manager import set_idle, set_activity_target, set_active_model
from session_state import session_state


APP_NAME = "InDoc-CLI"
VERSION = "1.4.0"
BUILD_STATUS = "Stable"
DEVELOPER = "Inxiske"

OLLAMA_MODELS = [
    "llama3.1",
    "llama3.2",
    "mistral",
    "gemma2",
    "gemma2:2b",
    "phi3",
    "phi3.5",
    "codellama",
    "qwen2.5",
    "deepseek-coder",
    "codegemma",
    "starcoder2",
    "wizardcoder",
    "llava",
    "mixtral",
    "command-r",
]

console = Console()


class CommandRouter:
    """
    Strict command router using Command Pattern.
    Maps command names to handler functions.
    """

    def __init__(self) -> None:
        """Initialize router with empty registry."""
        self.commands: Dict[str, Callable] = {}
        self.engine = OllamaEngine()
        try:
            from inx.utils.config import ensure_global_config
            ensure_global_config()
        except Exception:
            pass
        self.is_online: bool = False
        self.active_model: Optional[str] = None
        self.username: str = self._get_username()
        self.is_admin: bool = self._check_admin()
        self.last_output: str = ""
        self.active_jobs: int = 0

    @staticmethod
    def _get_username() -> str:
        """Get current username."""
        try:
            return getpass.getuser()
        except Exception:
            return "user"

    @staticmethod
    def _check_admin() -> bool:
        """Check if running with admin privileges."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except AttributeError:
            return getattr(os, 'getuid', lambda: -1)() == 0 if hasattr(os, 'getuid') else False

    def register(self, name: str, handler: Callable) -> None:
        """
        Register a command handler.

        Args:
            name: Command name.
            handler: Function to handle the command.
        """
        self.commands[name] = handler

    def dispatch(self, cmd: str, args: List[str]) -> Tuple[bool, str]:
        """
        Dispatch command to handler with strict argument handling.

        Args:
            cmd: Command name.
            args: Arguments list.

        Returns:
            Tuple of (success, message).
        """
        if cmd not in self.commands:
            return False, f"[!] Unknown command. Type 'inx help' for a list of valid actions."

        try:
            return self.commands[cmd](args)
        except IndocError as e:
            self.engine.log_error("Command failed", e)
            return False, f"[!] {str(e)}"
        except TypeError:
            return False, "[!] Error: Command failed. Type 'inx help' for usage."
        except Exception as e:
            self.engine.log_error("Unhandled exception", e)
            return False, "[!] Unexpected error. See ~/.indoc/logs/error.log"

    def check_status(self) -> Tuple[bool, str, Optional[str]]:
        """
        Check Ollama connection and update state.

        Returns:
            Tuple of (is_online, message, active_model).
        """
        is_online, msg, model = self.engine.check_connection()
        self.is_online = is_online
        self.active_model = model
        return is_online, msg, model

    def refresh_models(self) -> None:
        """Refresh available models and update active model."""
        models = self.engine.get_available_models()
        if models and not self.active_model:
            self.active_model = models[0]
        elif models and self.active_model not in models:
            self.active_model = models[0]
        elif not models:
            self.active_model = None

    def clear_screen(self) -> None:
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def begin_job(self) -> None:
        """Track long-running processing jobs."""
        self.active_jobs += 1

    def end_job(self) -> None:
        """Release long-running processing jobs."""
        if self.active_jobs > 0:
            self.active_jobs -= 1


router = CommandRouter()

def _default_config() -> Dict[str, object]:
    return {
        "model": "llama3",
        "doc_style": "detailed",
        "ignore_paths": ["venv", ".git", "__pycache__", "node_modules"],
        "baseline_seconds_per_file": 30
    }


def _global_config_path() -> Path:
    return Path.home() / ".indoc" / "config.json"


_GLOBAL_CONFIG_CACHE: Optional[Tuple[Dict[str, object], Optional[Path]]] = None


def _ensure_global_config() -> Path:
    cfg_path = _global_config_path()
    try:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        if not cfg_path.exists():
            cfg_path.write_text(json.dumps(_default_config(), indent=2), encoding="utf-8")
    except Exception as e:
        router.engine.log_error("Failed to ensure global config", e)
    return cfg_path


def _load_global_config() -> Tuple[Dict[str, object], Optional[Path]]:
    global _GLOBAL_CONFIG_CACHE
    if _GLOBAL_CONFIG_CACHE is not None:
        return _GLOBAL_CONFIG_CACHE
    defaults = _default_config()
    cfg_path = _ensure_global_config()
    if not cfg_path.exists():
        _GLOBAL_CONFIG_CACHE = (defaults, None)
        return _GLOBAL_CONFIG_CACHE
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise IndocError("Invalid global config.json format.")
        merged = defaults.copy()
        merged.update(raw)
        if not isinstance(merged.get("ignore_paths", []), list):
            merged["ignore_paths"] = defaults["ignore_paths"]
        _GLOBAL_CONFIG_CACHE = (merged, cfg_path)
        return _GLOBAL_CONFIG_CACHE
    except Exception as e:
        router.engine.log_error("Failed to read ~/.indoc/config.json", e)
        _GLOBAL_CONFIG_CACHE = (defaults, cfg_path)
        return _GLOBAL_CONFIG_CACHE


def _set_global_default_model(model_name: str) -> None:
    global _GLOBAL_CONFIG_CACHE
    cfg_path = _ensure_global_config()
    data: Dict[str, object] = {}
    try:
        if cfg_path.exists():
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
    except Exception:
        data = {}
    data["model"] = model_name
    cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _GLOBAL_CONFIG_CACHE = None


def _get_rpc_pref() -> Optional[bool]:
    cfg_path = _ensure_global_config()
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "discord_rpc" in raw:
            v = raw.get("discord_rpc")
            if isinstance(v, bool):
                return v
    except Exception:
        return None
    return None


def _set_rpc_pref(enabled: bool) -> bool:
    cfg_path = _ensure_global_config()
    data: Dict[str, object] = {}
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data = raw
    except Exception:
        data = {}
    prev = data.get("discord_rpc")
    data["discord_rpc"] = bool(enabled)
    try:
        cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        router.engine.log_error("Failed to write ~/.indoc/config.json for discord_rpc", e)
        raise IndocError("Could not persist RPC preference (permission/disk issue).")
    return prev is not bool(enabled)


def _parse_rpc_flags(args: List[str]) -> Tuple[List[str], Optional[bool]]:
    remaining: List[str] = []
    rpc_override: Optional[bool] = None
    i = 0
    while i < len(args):
        a = args[i].strip()
        al = a.lower()
        if al == "--rpc-off":
            rpc_override = False
            i += 1
            continue
        remaining.append(args[i])
        i += 1
    return remaining, rpc_override


def _find_project_root(start: Path) -> Path:
    p = start if start.is_dir() else start.parent
    for parent in [p, *p.parents]:
        if (parent / ".indoc" / "config.json").exists():
            return parent
    return p


def _load_project_config(start: Path) -> Tuple[Dict[str, object], Optional[Path]]:
    defaults, _ = _load_global_config()
    project_root = _find_project_root(start)
    cfg_path = project_root / ".indoc" / "config.json"
    if not cfg_path.exists():
        return defaults, None
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise IndocError("Invalid config.json format.")
        merged = defaults.copy()
        merged.update(raw)
        if not isinstance(merged.get("ignore_paths", []), list):
            merged["ignore_paths"] = defaults["ignore_paths"]
        return merged, cfg_path
    except Exception as e:
        router.engine.log_error("Failed to read .indoc/config.json", e)
        return defaults, cfg_path


def _parse_flags(args: List[str]) -> Tuple[List[str], bool, bool]:
    verbose = False
    dry_run = False
    remaining: List[str] = []
    for a in args:
        al = a.strip().lower()
        if al in ("-v", "--verbose"):
            verbose = True
            continue
        if al == "--dry-run":
            dry_run = True
            continue
        remaining.append(a)
    return remaining, verbose, dry_run


def _parse_mode(args: List[str]) -> Tuple[List[str], Optional[str]]:
    mode: Optional[str] = None
    remaining: List[str] = []
    i = 0
    while i < len(args):
        a = args[i].strip()
        al = a.lower()
        if al == "--mode":
            if i + 1 >= len(args):
                raise IndocError("Missing value for --mode. Usage: inx gen <path> --mode <junior|senior|security|onboarding>")
            mode = args[i + 1].strip().lower()
            i += 2
            continue
        remaining.append(args[i])
        i += 1
    return remaining, mode


def _parse_model(args: List[str]) -> Tuple[List[str], Optional[str]]:
    model: Optional[str] = None
    remaining: List[str] = []
    i = 0
    while i < len(args):
        a = args[i].strip()
        al = a.lower()
        if al == "--model":
            if i + 1 >= len(args):
                raise IndocError("Missing value for --model. Usage: --model <model_name>")
            model = args[i + 1].strip()
            i += 2
            continue
        remaining.append(args[i])
        i += 1
    return remaining, model


def _write_manifest(manifest_path: Path, payload: Dict[str, object]) -> None:
    try:
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        router.engine.log_error(f"Could not write manifest: {manifest_path}", e)
        raise IndocError("Could not write manifest.json (permission/disk issue).")


def _is_git_dirty(project_root: Path) -> bool:
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


def _stats_path() -> Path:
    return Path.home() / ".indoc" / "stats.json"


def _load_stats() -> Dict[str, object]:
    path = _stats_path()
    try:
        if not path.exists():
            return {"files_processed": 0, "docs_generated": 0, "seconds_spent": 0.0}
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"files_processed": 0, "docs_generated": 0, "seconds_spent": 0.0}
        return raw
    except Exception:
        return {"files_processed": 0, "docs_generated": 0, "seconds_spent": 0.0}


def _save_stats(data: Dict[str, object]) -> None:
    path = _stats_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        return


def _record_stats(files_processed: int, docs_generated: int, seconds_spent: float) -> None:
    s = _load_stats()
    try:
        s["files_processed"] = int(s.get("files_processed", 0)) + int(files_processed)
        s["docs_generated"] = int(s.get("docs_generated", 0)) + int(docs_generated)
        s["seconds_spent"] = float(s.get("seconds_spent", 0.0)) + float(seconds_spent)
        _save_stats(s)
    except Exception:
        return


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def _log_line(scope: str, event: str, target: str) -> str:
    return f"LOG | {_ts()} | {scope.upper():<5} | {event.upper():<10} | {target}"


def _generate_with_ai_status(content: str, model: str, target_label: str) -> str:
    q: "queue.SimpleQueue[tuple]" = queue.SimpleQueue()
    component = {"text": target_label}
    stage_index = {"value": 0}
    first_token_seen = {"value": False}
    tip_shown = {"value": False}
    line_buf: List[str] = []

    def advance_stage(target_idx: int) -> None:
        if target_idx > stage_index["value"]:
            stage_index["value"] = target_idx

    def set_stage_from_text(s: str) -> None:
        s_low = s.lower()
        if "## component analysis" in s_low:
            advance_stage(1)
        elif "## forensic engineering" in s_low:
            advance_stage(2)
        elif "## senior engineering recommendations" in s_low:
            advance_stage(3)

    def try_update_component_from_line(line: str) -> None:
        l = line.strip()
        if l.startswith("### "):
            component["text"] = l[4:].strip()
        if l.startswith("#### "):
            component["text"] = l[5:].strip()

    def _on_first_token() -> None:
        q.put(("first_token", None))

    def _on_token(tok: str) -> None:
        q.put(("token", tok))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(router.engine.generate, content, model, True, _on_first_token, _on_token)

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task(_log_line("AUDIT", "STAGE", "Ingesting Source Code"), total=100)

            renderable = {"value": Group(progress)}
            with Live(renderable["value"], console=console, refresh_per_second=8, transient=True) as live:
                percent = 0
                start_ts = time.monotonic()

                while not future.done():
                    while True:
                        try:
                            kind, payload = q.get_nowait()
                        except Exception:
                            break
                        if kind == "first_token":
                            advance_stage(1)
                            first_token_seen["value"] = True
                        elif kind == "token":
                            tok = str(payload)
                            for ch in tok:
                                line_buf.append(ch)
                                if ch == "\n":
                                    line = "".join(line_buf)
                                    line_buf.clear()
                                    set_stage_from_text(line)
                                    try_update_component_from_line(line)

                    if not first_token_seen["value"] and not tip_shown["value"]:
                        if (time.monotonic() - start_ts) >= 15:
                            tip_shown["value"] = True
                            tip = (
                                "[!] High latency detected. The current model appears to be under heavy load.\n"
                                "[TIP] Use 'inx model --list' to see installed models or 'inx model --set <name>' to switch.\n\n"
                                "For faster audits, consider 'phi3' or 'llama3.2'. "
                                "For maximum depth, keep 'llama3.1'. The choice is yours."
                            )
                            tip_panel = Panel(tip, border_style="yellow", padding=(0, 0), box=box.SIMPLE)
                            renderable["value"] = Group(progress, tip_panel)
                            live.update(renderable["value"])

                    if stage_index["value"] == 0:
                        percent = max(percent, 10)
                        description = _log_line("AUDIT", "STAGE", "Ingesting Source Code")
                    elif stage_index["value"] == 1:
                        percent = max(percent, 30)
                        description = _log_line("AUDIT", "STAGE", f"Analyzing Context ({component['text']})")
                    elif stage_index["value"] == 2:
                        percent = max(percent, 70)
                        description = _log_line("AUDIT", "STAGE", "Identifying Architectural Risks")
                    else:
                        percent = max(percent, 90)
                        description = _log_line("AUDIT", "STAGE", "Drafting Senior Recommendations")

                    progress.update(task, completed=percent, description=description)
                    live.update(renderable["value"])
                    time.sleep(0.1)

                result = future.result()
                progress.update(task, completed=100, description=_log_line("AUDIT", "STAGE", "Completed"))
                live.update(renderable["value"])
                return result


def _extract_ai_insight(markdown_text: str) -> str:
    if not markdown_text:
        return ""
    lines = (markdown_text or "").splitlines()
    in_overview = False
    overview_lines: List[str] = []
    for line in lines:
        l = line.strip()
        if l.startswith("## "):
            if l.startswith("## 🧠"):
                in_overview = True
                continue
            if in_overview:
                break
        if in_overview and l:
            overview_lines.append(l)
            if len(overview_lines) >= 3:
                break
    text = " ".join(overview_lines).strip()
    for prefix in ("- ", "* ", "> "):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    text = text.replace("**", "").replace("__", "").replace("`", "")
    words = [w for w in text.split() if w]
    return " ".join(words[:5]).strip()


def _extract_ai_key_points(markdown_text: str, max_points: int = 3) -> List[str]:
    if not markdown_text:
        return []
    lines = (markdown_text or "").splitlines()

    def collect_from_section(section_prefix: str) -> List[str]:
        in_section = False
        points: List[str] = []
        for line in lines:
            l = line.strip()
            if l.startswith("## "):
                if l.startswith(section_prefix):
                    in_section = True
                    continue
                if in_section:
                    break
            if in_section:
                if l.startswith(("- ", "* ")):
                    item = l[2:].strip()
                    if item:
                        points.append(item)
                elif l and len(points) < max_points and not points:
                    points.append(l)
            if len(points) >= max_points:
                break
        return points

    points = collect_from_section("## 🔑")
    if points:
        return points[:max_points]
    points = collect_from_section("## 🚀")
    return points[:max_points]


def cmd_init(args: List[str]) -> Tuple[bool, str]:
    project_root = Path.cwd()
    indoc_dir = project_root / ".indoc"
    cfg_path = indoc_dir / "config.json"
    try:
        _ensure_global_config()
        indoc_dir.mkdir(parents=True, exist_ok=True)
        if cfg_path.exists():
            console.print(f"[yellow][!] Config already exists:[/yellow] {cfg_path}")
            return True, "Config exists"
        cfg_path.write_text(json.dumps(_default_config(), indent=2), encoding="utf-8")
        console.print(f"[green][OK] Initialized project config:[/green] {cfg_path}")
        return True, "Initialized"
    except Exception as e:
        router.engine.log_error("inx init failed", e)
        return False, "[!] Could not initialize project. See ~/.indoc/logs/error.log"


def cmd_status(args: List[str]) -> Tuple[bool, str]:
    """
    Check Ollama connection status.

    Args:
        args: Command arguments (ignored).

    Returns:
        Tuple of (success, message).
    """
    is_online, msg, model = router.check_status()
    router.refresh_models()

    if is_online:
        console.print(f"[green][OK] {msg}[/green]")
        if model:
            console.print(f"[dim]Active Model:[/dim] [cyan]{model}[/cyan]")
        else:
            console.print("[yellow][!] Ollama is online, but no models found.[/yellow]")
            console.print("[dim]Run 'inx model pull <name>' to download a model.[/dim]")
    else:
        console.print(f"[red][!] {msg}[/red]")
        console.print("[yellow]Run 'inx install ollama' to setup your environment.[/yellow]")

    return True, msg


def cmd_install(args: List[str]) -> Tuple[bool, str]:
    """
    Handle Ollama installation.

    Args:
        args: Command arguments. If 'ollama', proceed with setup.

    Returns:
        Tuple of (success, message).
    """
    if not args or args[0].lower() != 'ollama':
        return False, "[!] Usage: inx install ollama"

    router.check_status()
    if router.is_online:
        return False, "[!] Ollama is already installed and running. No setup required."

    console.print("\nOllama setup")
    console.print("-" * 11)
    console.print("[1] Open download page (manual install)")
    console.print("[2] Automated install (requires admin)")
    console.print("[3] Cancel")

    choice = Prompt.ask("\nSelect option", choices=["1", "2", "3"], default="3")

    if choice == "1":
        webbrowser.open("https://ollama.com/download")
        console.print("\n[OK] Download page opened in your browser.")
        console.print("[1] Complete the installation.")
        console.print("[2] Run: ollama run llama3")
        console.print(f"[3] Restart {APP_NAME}.")
    elif choice == "2":
        console.print("\n[INFO] Attempting automated installation (may require admin)...")
        try:
            subprocess.run(
                ["powershell", "-Command", "irm https://ollama.com/install.ps1 | iex"],
                check=True,
                encoding='utf-8',
                errors='ignore'
            )
            console.print("\n[OK] Ollama installation completed.")
            console.print("Next: ollama run llama3")
        except subprocess.CalledProcessError:
            console.print("\n[ERR] Installation failed or was cancelled.")
            console.print("Try manual installation: inx install ollama (option 1)")
    else:
        console.print("Setup cancelled.")

    return True, "Setup options displayed"


def cmd_uninstall(args: List[str]) -> Tuple[bool, str]:
    """
    Handle Ollama integration uninstall.

    Args:
        args: Command arguments. If 'ollama', proceed with uninstall.

    Returns:
        Tuple of (success, message).
    """
    if not args or args[0].lower() != 'ollama':
        return False, "[!] Usage: inx uninstall ollama"

    if router.active_jobs > 0:
        console.print("[ERR] Cannot uninstall while processing tasks are running.")
        console.print("Wait for 'inx gen' or 'inx scan' to finish, then try again.")
        return False, "Processing job running"

    confirm = Prompt.ask(
        "[bold yellow][?] Are you sure you want to stop and remove Ollama?[/bold yellow] (y/N)",
        default="N"
    ).strip().lower()

    if confirm not in ("y", "yes"):
        console.print("Uninstall cancelled.")
        return True, "Uninstall cancelled"

    console.print(_log_line("SYSTEM", "STOP", "Stopping Ollama service"))
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "ollama.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            encoding='utf-8',
            errors='ignore'
        )
    except Exception:
        pass

    console.print(_log_line("SYSTEM", "CLEAN", "Cleaning local engine files"))
    cleaned_any = False
    cleanup_targets = [
        Path.home() / ".ollama",
        Path.home() / "AppData" / "Local" / "Ollama",
        Path.home() / "AppData" / "Roaming" / "Ollama",
    ]

    for target in cleanup_targets:
        try:
            if target.exists():
                if target.is_dir():
                    import shutil
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
                cleaned_any = True
        except Exception:
            continue

    router.is_online = False
    router.active_model = None
    console.print(_log_line("SYSTEM", "UNINSTALL", "Ollama integration disabled by user request"))
    if cleaned_any:
        console.print("[OK] Local engine files cleaned.")
    else:
        console.print("[INFO] No local engine files found to clean.")
    console.print("[INFO] Note: the Ollama binary may still be installed on this system.")
    return True, "Ollama integration uninstalled"


def cmd_model(args: List[str]) -> Tuple[bool, str]:
    """
    Handle model management commands.

    Args:
        args: Command arguments (action, name).

    Returns:
        Tuple of (success, message).
    """
    if not args:
        return False, "[!] Usage: inx model <action>\n    Actions: --list | --set <name> | pull <name> | gallery"

    if args[0].lower() in ("--list", "--ls"):
        return cmd_model_list([])

    if args[0].lower() == "--set":
        if len(args) < 2:
            return False, "[!] Usage: inx model --set <name>"
        requested = args[1].strip()
        resolved, installed = router.engine.resolve_installed_model(requested)
        if not resolved:
            if installed:
                console.print("[WARN] Model not found.")
                console.print(f"Installed models: {', '.join(installed[:12])}")
                return False, "Model not found"
            return False, f"[!] Model '{requested}' is not installed. Run 'inx model pull {requested}'."
        _set_global_default_model(resolved)
        router.active_model = resolved
        router.engine.active_model = resolved
        console.print(f"[OK] Default model set to: {resolved}")
        console.print("This will be used on the next execution.")
        if _get_rpc_pref() is True:
            set_active_model(resolved)
        return True, "Model set"

    action = args[0].lower()

    if action == "list":
        return cmd_model_list(args[1:])

    if action == "search":
        return cmd_model_list(args[1:])

    if action == "gallery":
        return cmd_model_gallery(args[1:])

    if action != "pull":
        return False, f"[!] Unknown action '{action}'. Usage: inx model pull <name>"

    if len(args) < 2:
        return False, "[!] Usage: inx model pull <name>"

    model_name = args[1].lower()

    router.check_status()
    if not router.is_online:
        console.print("[ERR] Ollama service is not running.")
        console.print("Run: inx install ollama")
        return False, "Ollama offline"

    console.print(_log_line("MODEL", "PULL", f"Downloading {model_name}"))

    try:
        process = subprocess.Popen(
            ["ollama", "pull", model_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding='utf-8',
            errors='ignore'
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task(f"Downloading {model_name}...", total=None)
            for _ in process.stdout:
                pass
            process.wait()

        if process.returncode == 0:
            console.print(f"[OK] Model '{model_name}' pulled successfully.")
            router.refresh_models()
            if router.active_model:
                console.print(f"Active model set to: {router.active_model}")
            return True, f"Model {model_name} pulled"
        else:
            console.print(f"[ERR] Failed to pull model '{model_name}'.")
            suggestions = get_similar_models(model_name)
            if suggestions:
                console.print(f"Did you mean: {', '.join(suggestions)}")
            return False, f"Failed to pull model {model_name}"

    except FileNotFoundError:
        console.print("[ERR] 'ollama' command not found. Is Ollama installed?")
        return False, "Ollama CLI not found"
    except Exception as e:
        console.print(f"[ERR] Error pulling model: {str(e)}")
        return False, f"Error: {str(e)}"


def cmd_model_list(args: List[str]) -> Tuple[bool, str]:
    """
    Display available models from Ollama library.

    Args:
        args: Command arguments (ignored).

    Returns:
        Tuple of (success, message).
    """
    router.check_status()

    installed = router.engine.get_installed_models()
    console.print("\nInstalled models (Ollama):")
    console.print("Use: inx model --set <name>")

    if not installed:
        console.print("[WARN] No installed models found.")
        console.print("Run: inx model pull <name>")
        return True, "No models"

    table = Table(show_header=True, box=box.MINIMAL, pad_edge=False)
    table.add_column("Model", width=40)
    for m in installed:
        table.add_row(m)
    console.print(table)
    return True, "Model list displayed"


def cmd_model_gallery(args: List[str]) -> Tuple[bool, str]:
    """
    Display a beautiful gallery of recommended models.

    Args:
        args: Command arguments (ignored).

    Returns:
        Tuple of (success, message).
    """
    console.print("\nModel gallery (recommended):")

    recommended = [
        ("llama3.1", "Meta's flagship instruction-following model", "General purpose"),
        ("mistral", "Efficient 7B model, excellent for code", "Balanced"),
        ("gemma2", "Google's open model, 9B parameters", "Research"),
        ("phi3", "Microsoft's compact 3B model", "Lightweight"),
        ("codellama", "Meta's code-specialized variant", "Code generation"),
    ]

    table = Table(show_header=True, box=box.MINIMAL, pad_edge=False)
    table.add_column("Model", width=18)
    table.add_column("Description", width=45)
    table.add_column("Use case", width=18)

    for model, desc, use in recommended:
        table.add_row(model, desc, use)

    console.print(table)
    console.print("Download: inx model pull <name>")

    return True, "Gallery displayed"


def get_similar_models(model_name: str) -> List[str]:
    """
    Find similar model names for suggestions.

    Args:
        model_name: The model name to match.

    Returns:
        List of similar model names.
    """
    model_lower = model_name.lower()
    matches = []

    for model in OLLAMA_MODELS:
        if model_lower in model or model in model_lower:
            matches.append(model)
        if len(matches) >= 3:
            break

    if not matches:
        matches = OLLAMA_MODELS[:4]

    return matches


def cmd_gen(args: List[str]) -> Tuple[bool, str]:
    """
    Generate documentation for a single file.

    Args:
        args: First element is the file path.

    Returns:
        Tuple of (success, message).
    """
    remaining, rpc_override = _parse_rpc_flags(args)
    if rpc_override is False:
        changed = _set_rpc_pref(False)
        if changed:
            console.print("[InDoc] Discord RPC disabled.")
    remaining, mode = _parse_mode(remaining)
    remaining, model_override = _parse_model(remaining)
    remaining, verbose, dry_run = _parse_flags(remaining)
    if not remaining:
        return False, "[!] Usage: inx gen <file_path> [--mode <profile>] [--model <model_name>] [-v|--verbose] [--dry-run]"

    input_path = remaining[0]
    normalized_path = os.path.abspath(os.path.expanduser(input_path))
    path = normalized_path

    router.check_status()
    router.refresh_models()

    if not router.is_online:
        console.print(f"[red][!] Ollama service is not running.[/red]")
        console.print("[yellow]Run 'inx install ollama' to setup, then try again.[/yellow]")
        return False, "Ollama offline"

    if not router.active_model:
        console.print("[red][!] No model available.[/red]")
        console.print("[yellow]Run 'inx model pull <name>' to download a model first.[/yellow]")
        return False, "No model available"

    if not os.path.exists(path):
        console.print(f"[red][!] Could not find file at: {path}[/red]")
        return False, f"[!] Could not find file at: {path}"

    source_path = Path(path).resolve()
    cfg, cfg_path = _load_project_config(source_path)
    cfg_model = str(cfg.get("model") or "").strip()
    cfg_style = str(cfg.get("doc_style") or "").strip()
    if cfg_style:
        router.engine.set_doc_style(cfg_style)
    if mode:
        router.engine.set_prompt_mode(mode)
    selected_model = (model_override or cfg_model or "llama3").strip()
    if selected_model:
        resolved, installed = router.engine.resolve_installed_model(selected_model)
        if not resolved:
            if installed:
                suggestions = ", ".join(installed[:12])
                return False, f"[!] Model not found. Did you mean one of these? {suggestions}"
            return False, f"[!] Model '{selected_model}' is not installed. Run 'inx model pull {selected_model}'."
        router.active_model = resolved
    current_mode = router.engine.prompt_mode
    rpc_enabled = _get_rpc_pref() is True
    console.print(f"[InDoc] Mode: {current_mode} | Model: {router.active_model} | RPC: {'Active' if rpc_enabled else 'Inactive'} | Status: Initializing...")
    if rpc_enabled:
        session_state.set_mode(current_mode)
        session_state.set_model(str(router.active_model))
        set_activity_target(source_path.name)
    project_root = _find_project_root(source_path)
    if _is_git_dirty(project_root):
        console.print("[WARN] Git working tree is dirty. Consider committing before generating docs.")
    output_path = source_path.with_suffix(source_path.suffix + ".indoc.md")
    manifest_path = project_root / "manifest.json"
    content = ""
    result = ""

    start_ts = time.perf_counter()
    router.begin_job()
    try:
        if dry_run:
            console.print("[WARN] DRY-RUN enabled. No files will be written.")

        console.print(_log_line("GEN", "READING", str(source_path)))
        console.print(f"Model: {router.active_model}")

        if verbose:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TextColumn("[dim]{task.fields[current_item]}[/dim]"),
                console=console
            ) as progress:
                task = progress.add_task(
                    "gen pipeline",
                    total=3,
                    current_item=source_path.name
                )

                console.print("Step 1/3: READING file contents...")
                try:
                    with source_path.open('r', encoding='utf-8') as f:
                        content = f.read()
                except Exception as e:
                    router.engine.log_error(f"Could not read file: {source_path}", e)
                    console.print(f"[red][ERROR] Could not read {source_path.name}. Skipping...[/red]")
                    return False, f"Error reading file: {str(e)}"
                progress.update(task, advance=1, current_item="read completed")

                console.print(f"Step 2/3: AUDITING with Ollama model: {router.active_model} ...")
                if dry_run:
                    result = f"# DRY-RUN\n\nWould generate documentation for: {source_path.name}\n"
                else:
                    try:
                        result = _generate_with_ai_status(content, str(router.active_model), source_path.name)
                    except IndocError as e:
                        router.engine.log_error("inx gen failed", e)
                        console.print("[red][!] Operation failed.[/red]")
                        console.print("[dim]See ~/.indoc/logs/error.log[/dim]")
                        return False, f"[!] {str(e)}"
                router.last_output = result
                progress.update(task, advance=1, current_item="analysis completed")

                console.print(_log_line("GEN", "WRITING", str(output_path)))
                if not dry_run:
                    try:
                        output_path.write_text(result, encoding='utf-8')
                    except Exception as e:
                        router.engine.log_error(f"Could not write output file: {output_path}", e)
                        return False, f"[!] Could not write documentation file (permission/disk issue). See ~/.indoc/logs/error.log"
                    _write_manifest(manifest_path, {
                        "tool": "InDoc",
                        "command": "gen",
                        "mode": router.engine.prompt_mode,
                        "source_path": str(source_path),
                        "output_path": str(output_path),
                        "model": str(router.active_model),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "files_processed": 1,
                        "code_health": "analyzed",
                        "security_status": "security-audit" if router.engine.prompt_mode == "security" else "not-focused"
                    })
                progress.update(task, advance=1, current_item=output_path.name)
        else:
            try:
                with source_path.open('r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                router.engine.log_error(f"Could not read file: {source_path}", e)
                return False, "[!] Could not read input file. See ~/.indoc/logs/error.log"

            if not dry_run:
                try:
                    result = _generate_with_ai_status(content, str(router.active_model), source_path.name)
                except IndocError as e:
                    router.engine.log_error("inx gen failed", e)
                    return False, f"[!] {str(e)}"
                try:
                    output_path.write_text(result, encoding='utf-8')
                except Exception as e:
                    router.engine.log_error(f"Could not write output file: {output_path}", e)
                    return False, "[!] Could not write documentation file (permission/disk issue). See ~/.indoc/logs/error.log"
                _write_manifest(manifest_path, {
                    "tool": "InDoc",
                    "command": "gen",
                    "mode": router.engine.prompt_mode,
                    "source_path": str(source_path),
                    "output_path": str(output_path),
                    "model": str(router.active_model),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "files_processed": 1,
                    "code_health": "analyzed",
                    "security_status": "security-audit" if router.engine.prompt_mode == "security" else "not-focused"
                })
            else:
                result = f"# DRY-RUN\n\nWould generate documentation for: {source_path.name}\n"
                router.last_output = result

        elapsed = time.perf_counter() - start_ts
        _record_stats(files_processed=1, docs_generated=(0 if dry_run else 1), seconds_spent=elapsed)

        if verbose and not dry_run:
            console.print("\n" + "-" * 80)
            console.print("## System Architecture & Intent")
            console.print("-" * 80)
            console.print(Markdown(result))
            console.print("-" * 80 + "\n")

        key_points = _extract_ai_key_points(result, max_points=3)
        summary_table = Table(show_header=False, box=box.MINIMAL, pad_edge=False)
        summary_table.add_column("Metric")
        summary_table.add_column("Value")
        summary_table.add_row("Files processed", "1")
        summary_table.add_row("Total time", f"{elapsed:.2f}s")
        summary_table.add_row("Model", str(router.active_model))
        if key_points:
            summary_table.add_row("AI insights", "\n".join([f"- {p}" for p in key_points]))
        if dry_run:
            summary_table.add_row("Output", f"(dry-run) {output_path}")
        else:
            summary_table.add_row("Output", str(output_path))
            summary_table.add_row("Manifest", str(manifest_path))
        console.print("\nSummary:")
        console.print(summary_table)
        if not dry_run:
            console.print(f"[OK] [SAVE] Documentation generated at: {str(output_path.resolve())}")

        return True, "Documentation generated"
    finally:
        router.end_job()


def cmd_scan(args: List[str]) -> Tuple[bool, str]:
    """
    Scan a project directory recursively.

    Args:
        args: First element is the directory path.

    Returns:
        Tuple of (success, message).
    """
    remaining, rpc_override = _parse_rpc_flags(args)
    if rpc_override is False:
        changed = _set_rpc_pref(False)
        if changed:
            console.print("[InDoc] Discord RPC disabled.")
    remaining, mode = _parse_mode(remaining)
    remaining, model_override = _parse_model(remaining)
    remaining, verbose, dry_run = _parse_flags(remaining)
    if not remaining:
        return False, "[!] Usage: inx scan <directory_path> [-v|--verbose] [--dry-run]"

    input_target_path = remaining[0]
    target_path = os.path.abspath(os.path.expanduser(input_target_path))

    router.check_status()
    router.refresh_models()

    if not router.is_online:
        console.print(f"[red][!] Ollama service is not running.[/red]")
        console.print("[yellow]Run 'inx install ollama' to setup, then try again.[/yellow]")
        return False, "Ollama offline"

    if not router.active_model:
        console.print("[red][!] No model available.[/red]")
        console.print("[yellow]Run 'inx model pull <name>' to download a model first.[/yellow]")
        return False, "No model available"

    if not os.path.exists(target_path):
        console.print(f"[red][!] Path not found: {target_path}[/red]")
        return False, f"Path not found: {target_path}"

    if not os.path.isdir(target_path):
        console.print(f"[red][!] Not a directory: {target_path}[/red]")
        console.print(f"[dim]Validated path (repr): {target_path!r}[/dim]")
        return False, f"Not a directory: {target_path}"

    start_ts = time.perf_counter()
    router.begin_job()
    try:
        scanner = ProjectScanner(Path(target_path).resolve())
        manifest_path = scanner.root_path / "manifest.json"
        if scanner.ignore_source:
            if scanner.ignore_source == ".gitignore":
                console.print("[LOG] Skipping ignored paths based on .gitignore...")
            else:
                console.print(f"[LOG] Skipping ignored paths based on {scanner.ignore_source}...")
        cfg, cfg_path = _load_project_config(scanner.root_path)
        cfg_style = str(cfg.get("doc_style") or "").strip()
        cfg_model = str(cfg.get("model") or "").strip()
        if cfg_style:
            router.engine.set_doc_style(cfg_style)
        if mode:
            router.engine.set_prompt_mode(mode)
        selected_model = (model_override or cfg_model or "llama3").strip()
        if selected_model:
            resolved, installed = router.engine.resolve_installed_model(selected_model)
            if not resolved:
                if installed:
                    suggestions = ", ".join(installed[:12])
                    return False, f"[!] Model not found. Did you mean one of these? {suggestions}"
                return False, f"[!] Model '{selected_model}' is not installed. Run 'inx model pull {selected_model}'."
            router.active_model = resolved
        current_mode = router.engine.prompt_mode
        rpc_enabled = _get_rpc_pref() is True
        console.print(f"[InDoc] Mode: {current_mode} | Model: {router.active_model} | RPC: {'Active' if rpc_enabled else 'Inactive'} | Status: Initializing...")
        if rpc_enabled:
            session_state.set_mode(current_mode)
            session_state.set_model(str(router.active_model))
            set_activity_target(scanner.root_path.name)
        ignore_paths = cfg.get("ignore_paths", [])
        if isinstance(ignore_paths, list):
            for p in ignore_paths:
                if isinstance(p, str) and p.strip():
                    scanner.ignored_patterns.add(p.strip())
        file_tree: Dict[str, List[Dict]] = {}
        total_size = 0
        found_files = 0
        ready_files = 0

        console.print(f"\nScanning project: {target_path}")
        if dry_run:
            console.print("[WARN] DRY-RUN enabled. No analysis will be generated.")
        if _is_git_dirty(_find_project_root(scanner.root_path)):
            console.print("[WARN] Git working tree is dirty. Consider committing before generating docs.")

        # Always count files first for a real progress bar.
        files_to_visit: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(scanner.root_path):
            dirpath_obj = Path(dirpath)
            rel_dir = dirpath_obj.relative_to(scanner.root_path) if dirpath_obj != scanner.root_path else Path(".")
            if scanner._should_ignore(rel_dir):
                continue
            filtered_dirs: List[str] = []
            for d in dirnames:
                cand = rel_dir / d if rel_dir != Path(".") else Path(d)
                if not scanner._should_ignore(cand):
                    filtered_dirs.append(d)
            dirnames[:] = filtered_dirs
            for filename in filenames:
                fp = dirpath_obj / filename
                rel_path = fp.relative_to(scanner.root_path)
                if scanner._should_ignore(rel_path):
                    continue
                if fp.suffix.lower() not in scanner.EXTENSIONS_MAP:
                    continue
                files_to_visit.append(fp)

        total_files = max(1, len(files_to_visit))

        live_lines: List[str] = []

        def push_live(line: str) -> None:
            live_lines.append(line)
            if len(live_lines) > 18:
                del live_lines[0]

        with Progress(
            TextColumn("{task.completed}/{task.total}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[current_file]}"),
            console=console
        ) as progress:
            task = progress.add_task(
                "scan",
                total=total_files,
                current_file="starting..."
            )

            with Live(console=console, refresh_per_second=8, transient=True) as live:
                for idx, filepath in enumerate(files_to_visit, start=1):
                    rel_path = filepath.relative_to(scanner.root_path)
                    progress.update(task, advance=1, current_file=str(rel_path))
                    found_files += 1

                    push_live(_log_line("SCAN", "SCANNING", str(rel_path)))
                    try:
                        size = filepath.stat().st_size
                        total_size += size
                        ready_files += 1
                        lang = scanner.EXTENSIONS_MAP.get(filepath.suffix.lower(), 'Other')
                        if lang not in file_tree:
                            file_tree[lang] = []
                        file_tree[lang].append({
                            'name': filepath.name,
                            'path': str(rel_path),
                            'size': size,
                            'size_formatted': scanner._format_size(size)
                        })
                    except OSError:
                        push_live(_log_line("SCAN", "ERROR", f"Could not read {rel_path}. Skipping"))

                    live.update(Group(progress, Text("\n".join(live_lines), style="dim")))

        scanner.file_tree = file_tree
        scanner.total_size = total_size

        if not file_tree:
            console.print("[WARN] No code files found.")
            return False, "No code files found"

        stats = scanner.get_stats()
        table = Table(show_header=True, box=box.MINIMAL, pad_edge=False)
        table.add_column("Language", width=20)
        table.add_column("Files", justify="right", width=10)
        table.add_column("Size", justify="right", width=15)

        for lang in sorted(file_tree.keys()):
            files = file_tree[lang]
            lang_size = sum(item['size'] for item in files)
            table.add_row(lang, str(len(files)), scanner._format_size(lang_size))

        console.print("\nProject map:")
        console.print(table)
        console.print(f"Total files: {stats['total_files']} | Total size: {stats['total_size_formatted']}")
        console.print(f"[OK] {found_files} files found, {ready_files} files ready for documentation.")

        if not dry_run:
            console.print(f"Model: {router.active_model}")
            console.print("Generating architecture analysis via Ollama...")
            try:
                result = _generate_with_ai_status(
                    scanner.get_summary(),
                    str(router.active_model),
                    "project summary"
                )
            except IndocError as e:
                router.engine.log_error("inx scan analysis failed", e)
                console.print("[red][!] Operation failed.[/red]")
                console.print("[dim]See ~/.indoc/logs/error.log[/dim]")
                return False, f"[!] {str(e)}"
            router.last_output = result

            console.print("\n" + "-" * 80)
            console.print("## System Architecture & Intent")
            console.print("-" * 80)
            console.print(Markdown(result))
            console.print("-" * 80 + "\n")
            _write_manifest(manifest_path, {
                "tool": "InDoc",
                "command": "scan",
                "mode": router.engine.prompt_mode,
                "root_path": str(scanner.root_path),
                "model": str(router.active_model),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "files_processed": ready_files,
                "languages": stats.get("total_languages", 0),
                "total_size": stats.get("total_size", 0),
                "code_health": "mapped",
                "security_status": "security-audit" if router.engine.prompt_mode == "security" else "not-focused"
            })

        elapsed = time.perf_counter() - start_ts
        _record_stats(files_processed=ready_files, docs_generated=0, seconds_spent=elapsed)

        summary = Table(show_header=False, box=box.MINIMAL, pad_edge=False)
        summary.add_column("Metric")
        summary.add_column("Value")
        summary.add_row("Files processed", str(ready_files))
        summary.add_row("Total time", f"{elapsed:.2f}s")
        summary.add_row("Model", str(router.active_model))
        if not dry_run:
            summary.add_row("Manifest", str(manifest_path))
        console.print("\nSummary:")
        console.print(summary)
        return True, "Project scan completed"

    except Exception as e:
        console.print(f"[red][!] Error scanning project: {str(e)}[/red]")
        return False, f"Error scanning project: {str(e)}"
    finally:
        router.end_job()


def cmd_about(args: List[str]) -> Tuple[bool, str]:
    """
    Display about information.

    Args:
        args: Command arguments (ignored).

    Returns:
        Tuple of (success, message).
    """
    content = (
        f"{APP_NAME} v{VERSION}\n"
        f"A practical tool for code analysis and documentation.\n"
        f"Engine: Ollama\n"
        f"Developer: {DEVELOPER}\n"
    )
    console.print(content)
    return True, "About displayed"


def cmd_identity(args: List[str]) -> Tuple[bool, str]:
    """
    Display identity and build information.

    Args:
        args: Command arguments (ignored).

    Returns:
        Tuple of (success, message).
    """
    content = (
        f"{APP_NAME} v{VERSION}\n"
        f"Build: {BUILD_STATUS}\n"
        f"Developer: {DEVELOPER}\n"
        f"Engine: Ollama\n"
    )
    console.print(content)
    return True, "Identity displayed"


def cmd_stats(args: List[str]) -> Tuple[bool, str]:
    cfg, _ = _load_global_config()
    baseline = 30
    try:
        baseline = int(cfg.get("baseline_seconds_per_file", 30))
    except Exception:
        baseline = 30

    s = _load_stats()
    files_processed = int(s.get("files_processed", 0) or 0)
    docs_generated = int(s.get("docs_generated", 0) or 0)
    seconds_spent = float(s.get("seconds_spent", 0.0) or 0.0)
    estimated_saved = max(0.0, (docs_generated * float(baseline)) - seconds_spent)

    def fmt(sec: float) -> str:
        sec_i = int(max(0.0, sec))
        h = sec_i // 3600
        m = (sec_i % 3600) // 60
        s2 = sec_i % 60
        if h:
            return f"{h}h {m}m {s2}s"
        if m:
            return f"{m}m {s2}s"
        return f"{s2}s"

    table = Table(show_header=True, box=box.MINIMAL, pad_edge=False)
    table.add_column("Metric", width=28)
    table.add_column("Value", width=24)
    table.add_row("Files processed", str(files_processed))
    table.add_row("Docs generated", str(docs_generated))
    table.add_row("Time spent", fmt(seconds_spent))
    table.add_row("Estimated time saved", fmt(estimated_saved))

    console.print("INX stats:")
    console.print(table)
    return True, "Stats displayed"


def cmd_list_modes(args: List[str]) -> Tuple[bool, str]:
    catalog = router.engine.get_prompt_catalog()
    table = Table(show_header=True, box=box.MINIMAL, pad_edge=False)
    table.add_column("Profile", width=14)
    table.add_column("Description", width=72)
    for profile, desc in catalog.items():
        table.add_row(profile, desc)
    console.print("Available analysis profiles:")
    console.print(table)
    return True, "Modes listed"


def cmd_help(args: List[str]) -> Tuple[bool, str]:
    """
    Display usage guide and command reference.

    Args:
        args: Command arguments (ignored).

    Returns:
        Tuple of (success, message).
    """
    content = (
        "InDoc-CLI command reference\n\n"
        "System:\n"
        "  inx init                 - Initialize .indoc/config.json\n"
        "  inx stats                - Show usage statistics\n"
        "  inx status               - Check Ollama connection\n"
        "  inx identity             - Show build information\n"
        "  inx about                - About the tool\n\n"
        "Processing:\n"
        "  inx gen <path> [--mode <profile>] [--model <name>] - Generate documentation for a file\n"
        "  inx scan <path> [--mode <profile>] [--model <name>] - Recursively scan a project\n"
        "  Use --list-modes to see available profiles.\n\n"
        "Models:\n"
        "  inx model gallery        - Browse recommended models\n"
        "  inx model --list         - List installed models\n"
        "  inx model --set <name>   - Set default model\n"
        "  inx model pull <name>    - Download a model\n\n"
        "Environment:\n"
        "  inx install ollama       - Setup Ollama engine\n"
        "  inx uninstall ollama     - Stop service and disable integration\n\n"
        "Other:\n"
        "  inx clear                - Clear terminal\n"
        "  inx dev                  - Developer greeting\n"
        "  exit                     - Terminate session\n"
    )
    console.print(content)
    return True, "Help displayed"


def cmd_clear(args: List[str]) -> Tuple[bool, str]:
    """
    Clear the terminal screen.

    Args:
        args: Command arguments (ignored).

    Returns:
        Tuple of (success, message).
    """
    router.clear_screen()
    return True, "Screen cleared"


def cmd_dev(args: List[str]) -> Tuple[bool, str]:
    """
    Display developer greeting.

    Args:
        args: Command arguments (ignored).

    Returns:
        Tuple of (success, message).
    """
    console.print(f"Greetings. System optimized by {DEVELOPER}.")
    return True, "Dev greeting displayed"


def setup_commands() -> None:
    """Register all available commands with the router."""
    router.register('init', cmd_init)
    router.register('stats', cmd_stats)
    router.register('list-modes', cmd_list_modes)
    router.register('status', cmd_status)
    router.register('install', cmd_install)
    router.register('uninstall', cmd_uninstall)
    router.register('model', cmd_model)
    router.register('gen', cmd_gen)
    router.register('scan', cmd_scan)
    router.register('about', cmd_about)
    router.register('identity', cmd_identity)
    router.register('help', cmd_help)
    router.register('clear', cmd_clear)
    router.register('dev', cmd_dev)


setup_commands()
