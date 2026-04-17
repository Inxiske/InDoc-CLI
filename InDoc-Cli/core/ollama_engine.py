"""
InDoc-CLI: Ollama Engine Module.

Handles all communication with the Ollama API.
State-aware: tracks connection status internally.
Smart Boot Protocol: detects and auto-starts Ollama service.
"""

import shutil
import subprocess
import traceback
import json
import time
from datetime import datetime
from pathlib import Path
import httpx
from typing import Tuple, Optional, List, Callable, Dict, Any

from inx.core.errors import IndocError


class OllamaEngine:
    """
    Manages Ollama API connections and state.

    Attributes:
        base_url: The base URL for the Ollama API.
        is_online: Current connection state.
        active_model: Currently active model name.
    """

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        """
        Initialize the Ollama engine.

        Args:
            base_url: The base URL for the Ollama API.
        """
        self.base_url = base_url
        self.request_timeout: float = 300.0
        self.client = httpx.Client(timeout=self.request_timeout)
        self.is_online: bool = False
        self.active_model: Optional[str] = None
        self.is_installed: bool = False
        self.doc_style: str = "deep-dive"
        self.prompt_mode: str = "senior"
        self.prompt_descriptions: Dict[str, str] = {}
        self.prompt_profiles: Dict[str, str] = self._load_prompt_profiles()
        self.last_first_token_delay: Optional[float] = None
        self.system_prompt = self.prompt_profiles.get("senior", "")

    def _default_prompt_profiles(self) -> Dict[str, Dict[str, str]]:
        return {
            "junior": {
                "description": "Guided explanation for new developers.",
                "prompt": (
                "You are a senior engineer mentoring a junior developer. "
                "Explain code clearly and progressively with practical examples. "
                "Output in English Markdown. Include sections: Purpose, Flow, Key Functions, Potential Risks, Refactor Suggestions."
                ),
            },
            "senior": {
                "description": "Deep architectural and forensic technical analysis.",
                "prompt": (
                "You are a Senior Software Engineer and Reverse Engineering Specialist. "
                "Produce a dense technical report with sections: System Architecture & Intent, Component Analysis, "
                "Forensic Engineering, Senior Engineering Recommendations. "
                "Include Security Audit findings and Refactor Suggestion opportunities."
                ),
            },
            "security": {
                "description": "Security-first audit with findings and mitigations.",
                "prompt": (
                "You are a Software Security Auditor. "
                "Prioritize vulnerability discovery (injection, insecure deserialization, secrets, unsafe I/O, race conditions, auth flaws). "
                "Output in English Markdown with sections: Threat Surface, Findings, Severity, Exploitability, Mitigations."
                ),
            },
            "onboarding": {
                "description": "Entrypoint and hierarchy mapping for onboarding.",
                "prompt": (
                "You are an onboarding architect. "
                "Map project entrypoints, startup flow, module hierarchy, ownership boundaries, and dependency paths for new developers. "
                "Output in English Markdown with sections: Entry Points, Execution Flow, Module Hierarchy, Developer Onboarding Notes."
                ),
            },
        }

    def _load_prompt_profiles(self) -> Dict[str, str]:
        defaults = self._default_prompt_profiles()
        profiles: Dict[str, str] = {k: v["prompt"] for k, v in defaults.items()}
        self.prompt_descriptions = {k: v["description"] for k, v in defaults.items()}
        prompt_path = Path(__file__).resolve().parent.parent / "prompts.json"
        if not prompt_path.exists():
            return profiles
        try:
            raw = json.loads(prompt_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if not isinstance(key, str):
                        continue
                    k = key.strip().lower()
                    if isinstance(value, str) and value.strip():
                        profiles[k] = value.strip()
                        self.prompt_descriptions[k] = self.prompt_descriptions.get(k, f"{k} mode")
                        continue
                    if isinstance(value, dict):
                        p = value.get("prompt")
                        d = value.get("description")
                        if isinstance(p, str) and p.strip():
                            profiles[k] = p.strip()
                            if isinstance(d, str) and d.strip():
                                self.prompt_descriptions[k] = d.strip()
                            else:
                                self.prompt_descriptions[k] = self.prompt_descriptions.get(k, f"{k} mode")
        except Exception:
            pass
        return profiles

    def _system_prompt_for_style(self, style: Optional[str]) -> str:
        return self.prompt_profiles.get(self.prompt_mode, self.system_prompt)

    def set_doc_style(self, style: Optional[str]) -> None:
        if style:
            self.doc_style = style

    def set_prompt_mode(self, mode: Optional[str]) -> None:
        if not mode:
            return
        m = mode.strip().lower()
        if m in self.prompt_profiles:
            self.prompt_mode = m
            return
        raise IndocError(f"Unknown mode '{mode}'. Available modes: {', '.join(sorted(self.prompt_profiles.keys()))}")

    def get_prompt_modes(self) -> List[str]:
        return sorted(self.prompt_profiles.keys())

    def get_prompt_catalog(self) -> Dict[str, str]:
        return {k: self.prompt_descriptions.get(k, f"{k} mode") for k in sorted(self.prompt_profiles.keys())}

    def log_error(self, message: str, exc: Optional[BaseException] = None) -> None:
        try:
            log_dir = Path.home() / ".indoc" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "error.log"
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            lines = [f"[{ts}] {message}"]
            if exc is not None:
                lines.append(f"Exception: {type(exc).__name__}: {exc}")
                lines.append(traceback.format_exc())
            with log_path.open("a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            return

    def is_ollama_installed(self) -> bool:
        """
        Check if Ollama binary is available in PATH.

        Returns:
            True if 'ollama' command is found, False otherwise.
        """
        self.is_installed = shutil.which("ollama") is not None
        return self.is_installed

    def try_start_service(self) -> Tuple[bool, str]:
        """
        Attempt to start Ollama service in background.

        Returns:
            Tuple of (success, message).
        """
        if not self.is_installed:
            return False, "Ollama not installed"

        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                encoding='utf-8',
                errors='ignore'
            )
            return True, "Ollama service starting..."
        except Exception as e:
            return False, f"Failed to start: {str(e)}"

    def check_connection(self) -> Tuple[bool, str, Optional[str]]:
        """
        Check if Ollama service is reachable and update internal state.

        Returns:
            Tuple of (is_online, message, active_model).
        """
        self.is_ollama_installed()

        if not self.is_installed:
            self.is_online = False
            self.active_model = None
            return False, "Ollama binary not found in PATH", None

        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            models = response.json().get('models', [])
            if models:
                self.active_model = models[0]['name']
                self.is_online = True
                return True, "Ollama Service is ONLINE", self.active_model
            self.is_online = True
            self.active_model = None
            return True, "Ollama Service is ONLINE", None
        except httpx.ConnectError:
            self.is_online = False
            self.active_model = None
            return False, "Ollama Service is OFFLINE - Connection refused", None
        except Exception as e:
            self.is_online = False
            self.active_model = None
            return False, f"Ollama Service Error: {str(e)}", None

    def get_available_models(self) -> List[str]:
        """
        Fetch list of available models from Ollama.

        Returns:
            List of model names.
        """
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
        except Exception:
            return []

    @staticmethod
    def _split_model_name(name: str) -> Tuple[str, Optional[str]]:
        n = (name or "").strip().lower()
        if ":" in n:
            base, tag = n.split(":", 1)
            base = base.strip()
            tag = tag.strip() or None
            return base, tag
        return n, None

    @classmethod
    def _model_matches(cls, requested: str, candidate: str) -> bool:
        r_base, r_tag = cls._split_model_name(requested)
        c_base, c_tag = cls._split_model_name(candidate)
        if not r_base or not c_base:
            return False
        if r_base != c_base:
            return False
        if r_tag is None:
            return True
        if c_tag is None:
            return r_tag == "latest"
        return r_tag == c_tag

    def get_installed_models_cli(self) -> List[str]:
        """
        Fetch installed models via 'ollama list' (CLI), as a source of truth.

        Returns:
            List of installed model names.
        """
        try:
            r = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            out = (r.stdout or "").splitlines()
            if not out:
                return []
            models: List[str] = []
            for line in out[1:]:
                line = line.strip()
                if not line:
                    continue
                name = line.split()[0].strip()
                if name:
                    models.append(name)
            return models
        except Exception:
            return []

    def get_installed_models(self) -> List[str]:
        """
        Return installed models, preferring CLI list (ollama list) before API tags.
        """
        models_cli = self.get_installed_models_cli()
        if models_cli:
            return models_cli
        return self.get_available_models()

    def resolve_installed_model(self, requested: str) -> Tuple[Optional[str], List[str]]:
        """
        Resolve a requested model name to an installed model name.
        Matches are case-insensitive and flexible with ':latest' suffix.

        Returns:
            Tuple of (resolved_name or None, installed_models_list).
        """
        installed = self.get_installed_models()
        for m in installed:
            if self._model_matches(requested, m):
                return m, installed
        return None, installed

    def generate(
        self,
        code_snippet: str,
        model: Optional[str] = None,
        stream: bool = True,
        on_first_token: Optional[Callable[[], None]] = None,
        on_token: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Generate documentation for code snippet.

        Args:
            code_snippet: The source code to analyze.
            model: Model to use (defaults to active model).

        Returns:
            Generated documentation or error message.
        """
        if not self.is_online:
            raise IndocError("Ollama service is not running.")

        target_model = model or self.active_model
        if not target_model:
            raise IndocError("No model available. Please pull a model first.")

        try:
            payload = {
                "model": target_model,
                "system": self._system_prompt_for_style(self.doc_style),
                "prompt": f"Code to analyze:\n{code_snippet}",
                "stream": bool(stream)
            }
            if stream:
                start_ts = time.monotonic()
                self.last_first_token_delay = None
                chunks: List[str] = []
                with self.client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.request_timeout
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue
                        if isinstance(line, bytes):
                            line = line.decode("utf-8", errors="ignore")
                        try:
                            data = json.loads(line)
                        except Exception:
                            continue
                        token = data.get("response", "")
                        if token:
                            if self.last_first_token_delay is None:
                                self.last_first_token_delay = time.monotonic() - start_ts
                                if on_first_token is not None:
                                    try:
                                        on_first_token()
                                    except Exception:
                                        pass
                            if on_token is not None:
                                try:
                                    on_token(token)
                                except Exception:
                                    pass
                            chunks.append(token)
                        if data.get("done", False):
                            break
                final_text = "".join(chunks).strip()
                return final_text if final_text else "No response from model."
            else:
                response = self.client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.request_timeout
                )
                response.raise_for_status()
                result = response.json()
                return result.get('response', 'No response from model.')
        except httpx.ConnectError as e:
            self.is_online = False
            self.active_model = None
            raise IndocError(f"Ollama connection error (ConnectError): {e}") from e
        except httpx.TimeoutException as e:
            raise IndocError(f"Ollama timeout error (TimeoutException): {e}") from e
        except httpx.HTTPError as e:
            status = getattr(getattr(e, "response", None), "status_code", "unknown")
            body = getattr(getattr(e, "response", None), "text", "")
            detail = f"status={status}"
            if body:
                detail += f", body={body}"
            raise IndocError(f"Ollama request failed ({type(e).__name__}): {detail}") from e
        except Exception as e:
            raise IndocError(f"Unexpected engine error ({type(e).__name__}): {e}") from e

    def __del__(self) -> None:
        """Cleanup client connection on deletion."""
        self.client.close()
