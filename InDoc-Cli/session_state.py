import threading
from dataclasses import dataclass
from typing import Optional, Dict


@dataclass
class SessionSnapshot:
    mode: str
    model: str
    target: str


class SessionState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mode: str = "senior"
        self._model: str = ""
        self._target: str = ""

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._mode = str(mode or "").strip() or "senior"

    def set_model(self, model: str) -> None:
        with self._lock:
            self._model = str(model or "").strip()

    def set_target(self, target: str) -> None:
        with self._lock:
            self._target = str(target or "").strip()

    def snapshot(self) -> SessionSnapshot:
        with self._lock:
            return SessionSnapshot(
                mode=self._mode,
                model=self._model,
                target=self._target
            )

    def to_dict(self) -> Dict[str, str]:
        s = self.snapshot()
        return {"mode": s.mode, "model": s.model, "target": s.target}


session_state = SessionState()

