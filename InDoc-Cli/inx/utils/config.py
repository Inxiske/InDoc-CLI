import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from inx.core.errors import IndocError


@dataclass(frozen=True)
class IndocConfig:
    model: str
    doc_style: str
    ignore_paths: List[str]
    baseline_seconds_per_file: int

    @staticmethod
    def defaults() -> "IndocConfig":
        return IndocConfig(
            model="llama3.1",
            doc_style="detailed",
            ignore_paths=["venv", ".git", "__pycache__", "node_modules"],
            baseline_seconds_per_file=30,
        )

    @staticmethod
    def from_dict(data: Dict[str, Any], base: Optional["IndocConfig"] = None) -> "IndocConfig":
        b = base or IndocConfig.defaults()
        model = str(data.get("model", b.model) or b.model).strip() or b.model
        doc_style = str(data.get("doc_style", b.doc_style) or b.doc_style).strip() or b.doc_style
        ignore_paths_raw = data.get("ignore_paths", b.ignore_paths)
        ignore_paths: List[str] = []
        if isinstance(ignore_paths_raw, list):
            for p in ignore_paths_raw:
                if isinstance(p, str) and p.strip():
                    ignore_paths.append(p.strip())
        else:
            ignore_paths = list(b.ignore_paths)
        baseline = b.baseline_seconds_per_file
        try:
            baseline = int(data.get("baseline_seconds_per_file", baseline))
        except Exception:
            baseline = b.baseline_seconds_per_file
        return IndocConfig(
            model=model,
            doc_style=doc_style,
            ignore_paths=ignore_paths,
            baseline_seconds_per_file=baseline,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "doc_style": self.doc_style,
            "ignore_paths": list(self.ignore_paths),
            "baseline_seconds_per_file": int(self.baseline_seconds_per_file),
        }


_GLOBAL_CACHE: Optional[Tuple[IndocConfig, Optional[Path]]] = None


def global_config_path() -> Path:
    return Path.home() / ".indoc" / "config.json"


def ensure_global_config() -> Path:
    cfg_path = global_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    if not cfg_path.exists():
        cfg_path.write_text(json.dumps(IndocConfig.defaults().to_dict(), indent=2), encoding="utf-8")
    return cfg_path


def load_global_config() -> Tuple[IndocConfig, Optional[Path]]:
    global _GLOBAL_CACHE
    if _GLOBAL_CACHE is not None:
        return _GLOBAL_CACHE

    base = IndocConfig.defaults()
    cfg_path = ensure_global_config()
    if not cfg_path.exists():
        _GLOBAL_CACHE = (base, None)
        return _GLOBAL_CACHE

    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise IndocError("Invalid global config.json format.")
        cfg = IndocConfig.from_dict(raw, base=base)
        _GLOBAL_CACHE = (cfg, cfg_path)
        return _GLOBAL_CACHE
    except Exception:
        _GLOBAL_CACHE = (base, cfg_path)
        return _GLOBAL_CACHE


def find_project_root(start: Path) -> Path:
    p = start if start.is_dir() else start.parent
    for parent in [p, *p.parents]:
        if (parent / ".indoc" / "config.json").exists():
            return parent
    return p


def load_project_config(start: Path) -> Tuple[IndocConfig, Optional[Path]]:
    global_cfg, _ = load_global_config()
    project_root = find_project_root(start)
    cfg_path = project_root / ".indoc" / "config.json"
    if not cfg_path.exists():
        return global_cfg, None
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise IndocError("Invalid project config.json format.")
        merged = IndocConfig.from_dict(raw, base=global_cfg)
        return merged, cfg_path
    except Exception:
        return global_cfg, cfg_path
