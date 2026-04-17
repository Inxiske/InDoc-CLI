"""
Discord Rich Presence manager for InDoc CLI.
Runs as a lightweight daemon thread and never blocks core execution.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional, Dict
from session_state import session_state

CLIENT_ID = "1494503060465127546"
DEFAULT_LARGE_IMAGE = os.environ.get("INDOC_RPC_LARGE_IMAGE", "indoc")
DEFAULT_SMALL_IMAGE = os.environ.get("INDOC_RPC_SMALL_IMAGE", "indoc_small")
DEFAULT_LARGE_TEXT = os.environ.get("INDOC_RPC_LARGE_TEXT", "InDoc CLI")

try:
    from pypresence import Presence
except Exception:  # pragma: no cover
    Presence = None


class RPCManager:
    def __init__(self) -> None:
        self._enabled = Presence is not None
        self._rpc = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._payload: Optional[Dict[str, str]] = None
        self._last_payload: Optional[Dict[str, str]] = None
        self._last_sent_ts: float = 0.0
        self._connected = False
        self._next_connect_ts: float = 0.0
        self._backoff_s: float = 15.0

    def _ensure_thread(self) -> None:
        if not self._enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _connect(self) -> None:
        if not self._enabled or self._connected:
            return
        now = time.time()
        if now < self._next_connect_ts:
            return
        try:
            self._rpc = Presence(CLIENT_ID)
            self._rpc.connect()
            self._connected = True
            self._backoff_s = 15.0
            self._next_connect_ts = 0.0
            if os.environ.get("INDOC_RPC_DEBUG") == "1":
                print("[InDoc] Discord RPC connected.")
        except Exception:
            self._connected = False
            self._rpc = None
            self._next_connect_ts = now + self._backoff_s
            self._backoff_s = min(self._backoff_s * 2.0, 300.0)
            if os.environ.get("INDOC_RPC_DEBUG") == "1":
                print("[InDoc] Discord RPC connection failed (Discord may be closed).")

    def _worker(self) -> None:
        while not self._stop.is_set():
            self._connect()
            payload = None
            with self._lock:
                payload = self._payload
                self._payload = None
            if payload:
                self._last_payload = payload
            should_refresh = self._last_payload is not None and (time.time() - self._last_sent_ts) >= 15
            if (payload or should_refresh) and self._connected and self._rpc is not None and self._last_payload is not None:
                try:
                    self._rpc.update(**self._last_payload)
                    self._last_sent_ts = time.time()
                except Exception:
                    self._connected = False
                    self._rpc = None
                    self._last_sent_ts = 0.0
                    if os.environ.get("INDOC_RPC_DEBUG") == "1":
                        print("[InDoc] Discord RPC update failed (will retry with backoff).")
            time.sleep(0.8 if self._connected else 1.5)

    def update_presence(self, details: str, state: str, mode: str) -> None:
        if not self._enabled:
            return
        self._ensure_thread()
        payload = {
            "details": details,
            "state": state,
            "large_image": DEFAULT_LARGE_IMAGE,
            "large_text": f"{DEFAULT_LARGE_TEXT} | {mode}",
            "small_image": DEFAULT_SMALL_IMAGE,
            "small_text": f"Mode: {mode}",
        }
        with self._lock:
            self._payload = payload

    def set_idle(self, mode: str) -> None:
        self.update_presence("InDoc-CLI Idle", "Waiting for command...", mode)


_rpc_manager = RPCManager()


def refresh_presence() -> None:
    s = session_state.snapshot()
    details = s.target or "InDoc-CLI Idle"
    state = f"Model: {s.model}" if s.model else "Model: (unknown)"
    _rpc_manager.update_presence(details=details, state=state, mode=s.mode)


def set_idle(mode: str) -> None:
    session_state.set_mode(mode)
    session_state.set_target("InDoc-CLI Idle")
    refresh_presence()


def set_activity_target(target: str) -> None:
    session_state.set_target(target)
    refresh_presence()


def set_active_model(model: str) -> None:
    session_state.set_model(model)
    refresh_presence()
