"""
InDoc-CLI: Project Scanner Module.

Handles recursive project scanning with ignore pattern support.
Uses pathlib for robust path manipulation.
"""

import os
import fnmatch
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class ProjectScanner:
    """
    Recursively scans directories and builds project maps.

    Attributes:
        root_path: Root directory being scanned.
        ignored_patterns: Custom patterns from .docgenignore.
        file_tree: Dictionary of language -> file list.
        total_size: Total size of all scanned files.
    """

    EXTENSIONS_MAP: Dict[str, str] = {
        '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
        '.cpp': 'C++', '.c': 'C', '.h': 'C Header', '.java': 'Java',
        '.cs': 'C#', '.go': 'Go', '.rs': 'Rust', '.rb': 'Ruby',
        '.php': 'PHP', '.swift': 'Swift', '.kt': 'Kotlin',
        '.html': 'HTML', '.css': 'CSS', '.vue': 'Vue',
        '.jsx': 'React JSX', '.tsx': 'React TSX',
        '.sh': 'Shell', '.bash': 'Bash', '.ps1': 'PowerShell',
        '.sql': 'SQL', '.md': 'Markdown', '.json': 'JSON',
        '.xml': 'XML', '.yaml': 'YAML', '.yml': 'YAML',
        '.toml': 'TOML', '.ini': 'INI', '.cfg': 'Config'
    }

    IGNORE_DIRS: set = {
        'node_modules', 'venv', '__pycache__', '.git', '.vscode',
        '.idea', 'dist', 'build', '.env', '.venv', 'env', '.docgen'
    }
    DEFAULT_INDOC_IGNORE: List[str] = [
        "# InDoc default ignore patterns",
        "# Dependencies / virtual env",
        "node_modules/",
        "venv/",
        ".venv/",
        "env/",
        ".git/",
        "__pycache__/",
        "dist/",
        "build/",
        "",
        "# Binary / archives",
        "*.exe",
        "*.dll",
        "*.so",
        "*.dylib",
        "*.bin",
        "*.o",
        "*.obj",
        "*.class",
        "*.jar",
        "*.zip",
        "*.tar",
        "*.gz",
        "*.7z",
        "*.rar",
        "",
        "# Logs / caches / databases",
        "*.log",
        "*.tmp",
        "*.cache",
        "*.db",
        "*.sqlite",
        "",
        "# Media / docs not relevant to code audit",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.gif",
        "*.ico",
        "*.pdf",
        "",
        "# OS metadata",
        ".DS_Store",
        "Thumbs.db",
    ]

    def __init__(self, root_path: Path) -> None:
        """
        Initialize scanner for a given root path.

        Args:
            root_path: Root directory to scan.
        """
        self.root_path = root_path
        self.ignore_source: Optional[str] = None
        self.ignored_patterns: set = self._load_ignore_patterns()
        self.file_tree: Dict[str, List[Dict]] = {}
        self.total_size: int = 0

    def _load_ignore_patterns(self) -> set:
        """
        Load ignore patterns with priority:
        1) .gitignore
        2) indoc.ignore
        3) create default indoc.ignore

        Returns:
            Set of patterns to ignore.
        """
        patterns: set = set()

        gitignore = self.root_path / ".gitignore"
        indoc_ignore = self.root_path / "indoc.ignore"

        source_file: Optional[Path] = None
        if gitignore.exists():
            source_file = gitignore
            self.ignore_source = ".gitignore"
        elif indoc_ignore.exists():
            source_file = indoc_ignore
            self.ignore_source = "indoc.ignore"
        else:
            self._create_default_indoc_ignore(indoc_ignore)
            source_file = indoc_ignore
            self.ignore_source = "indoc.ignore"

        if source_file and source_file.exists():
            try:
                with source_file.open('r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if line.startswith('!'):
                            # Keep scanner deterministic and simple: ignore negation rules for now.
                            continue
                        patterns.add(line.replace("\\", "/"))
            except Exception:
                pass
        return patterns

    def _create_default_indoc_ignore(self, path: Path) -> None:
        try:
            path.write_text("\n".join(self.DEFAULT_INDOC_IGNORE) + "\n", encoding="utf-8")
            if os.name == "nt":
                try:
                    subprocess.run(
                        ["attrib", "+h", "+s", str(path)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False
                    )
                except Exception:
                    pass
        except Exception:
            return

    def _matches_pattern(self, rel_path: Path, pattern: str, is_dir: bool) -> bool:
        p = (pattern or "").strip().replace("\\", "/")
        if not p:
            return False

        rel = rel_path.as_posix().lstrip("./")
        name = rel_path.name

        # Directory pattern (e.g. node_modules/)
        if p.endswith("/"):
            p_dir = p.rstrip("/")
            if rel == p_dir or rel.startswith(p_dir + "/"):
                return True
            return any(part == p_dir for part in rel_path.parts)

        # Recursive / anchored path pattern
        if "/" in p:
            if fnmatch.fnmatch(rel, p):
                return True
            if p.endswith("/*"):
                base = p[:-2]
                return rel == base or rel.startswith(base + "/")
            return False

        # Simple token or wildcard filename
        if fnmatch.fnmatch(name, p):
            return True
        if is_dir and p == name:
            return True
        # Treat plain token as path segment matcher.
        return any(part == p for part in rel_path.parts)

    def _should_ignore(self, path: Path) -> bool:
        """
        Check if path should be ignored based on patterns.

        Args:
            path: Path to check.

        Returns:
            True if path should be ignored.
        """
        rel_path = path
        try:
            if path.is_absolute():
                rel_path = path.relative_to(self.root_path)
        except Exception:
            rel_path = path

        for part in rel_path.parts:
            if part in self.IGNORE_DIRS:
                return True
        is_dir_hint = not bool(rel_path.suffix)
        for p in self.ignored_patterns:
            if self._matches_pattern(rel_path, p, is_dir_hint):
                return True
        return False

    def _format_size(self, size: int) -> str:
        """
        Format byte size to human-readable string.

        Args:
            size: Size in bytes.

        Returns:
            Formatted size string.
        """
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def scan(self) -> Tuple[Dict[str, List[Dict]], int]:
        """
        Perform recursive directory scan.

        Returns:
            Tuple of (file_tree dict, total_size).
        """
        self.file_tree = {}
        self.total_size = 0

        for dirpath, dirnames, filenames in os.walk(self.root_path):
            dirpath = Path(dirpath)
            rel_dir = dirpath.relative_to(self.root_path) if dirpath != self.root_path else Path(".")
            if self._should_ignore(rel_dir):
                continue

            filtered_dirs: List[str] = []
            for d in dirnames:
                cand = rel_dir / d if rel_dir != Path(".") else Path(d)
                if not self._should_ignore(cand):
                    filtered_dirs.append(d)
            dirnames[:] = filtered_dirs

            for filename in filenames:
                filepath = dirpath / filename
                rel_path = filepath.relative_to(self.root_path)
                ext = filepath.suffix.lower()

                if self._should_ignore(rel_path):
                    continue

                if ext not in self.EXTENSIONS_MAP:
                    continue

                try:
                    size = filepath.stat().st_size
                    self.total_size += size
                    lang = self.EXTENSIONS_MAP.get(ext, 'Other')
                    if lang not in self.file_tree:
                        self.file_tree[lang] = []
                    self.file_tree[lang].append({
                        'name': filename,
                        'path': str(rel_path),
                        'size': size,
                        'size_formatted': self._format_size(size)
                    })
                except OSError:
                    pass

        return self.file_tree, self.total_size

    def get_summary(self) -> str:
        """
        Generate text summary for Ollama.

        Returns:
            Summary string.
        """
        lines = [f"Project Analysis: {self.root_path.name}"]
        lines.append(f"Total Languages: {len(self.file_tree)}")
        for lang in sorted(self.file_tree.keys()):
            files = self.file_tree[lang]
            lines.append(f"- {lang}: {len(files)} file(s)")
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, any]:
        """
        Get scan statistics.

        Returns:
            Dictionary with file counts and total size.
        """
        total_files = sum(len(files) for files in self.file_tree.values())
        return {
            'total_files': total_files,
            'total_languages': len(self.file_tree),
            'total_size': self.total_size,
            'total_size_formatted': self._format_size(self.total_size)
        }
