import json
from pathlib import Path
from typing import Dict, Any


def stats_path() -> Path:
    return Path.home() / ".indoc" / "stats.json"


def load_stats() -> Dict[str, Any]:
    path = stats_path()
    try:
        if not path.exists():
            return {"files_processed": 0, "docs_generated": 0, "seconds_spent": 0.0}
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"files_processed": 0, "docs_generated": 0, "seconds_spent": 0.0}
        return raw
    except Exception:
        return {"files_processed": 0, "docs_generated": 0, "seconds_spent": 0.0}


def save_stats(data: Dict[str, Any]) -> None:
    path = stats_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_stats(files_processed: int, docs_generated: int, seconds_spent: float) -> None:
    try:
        s = load_stats()
        s["files_processed"] = int(s.get("files_processed", 0)) + int(files_processed)
        s["docs_generated"] = int(s.get("docs_generated", 0)) + int(docs_generated)
        s["seconds_spent"] = float(s.get("seconds_spent", 0.0)) + float(seconds_spent)
        save_stats(s)
    except Exception:
        return
