"""
General-purpose helper utilities for the Desktop Automation Agent.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# ─────────────────────────────────────────────
# Path Utilities
# ─────────────────────────────────────────────

def resolve_path(path: str) -> Path:
    """Expand environment variables and user home in a path."""
    expanded = os.path.expandvars(os.path.expanduser(path))
    return Path(expanded)


def ensure_dir(path: Union[str, Path]) -> Path:
    """Create directory (and parents) if it doesn't exist."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_filename(name: str) -> str:
    """Strip characters that are invalid in Windows filenames."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def timestamped_filename(base: str, ext: str) -> str:
    """Generate a filename like report_20250101_153000.docx"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_clean = safe_filename(base)
    ext = ext.lstrip(".")
    return f"{base_clean}_{ts}.{ext}"


def get_desktop_path() -> Path:
    """Return Windows Desktop path."""
    return Path.home() / "Desktop"


def get_downloads_path() -> Path:
    """Return Windows Downloads path."""
    return Path.home() / "Downloads"


def get_documents_path() -> Path:
    """Return Windows Documents path."""
    return Path.home() / "Documents"


# ─────────────────────────────────────────────
# File Discovery
# ─────────────────────────────────────────────

def find_files(
    directory: Union[str, Path],
    pattern: str = "*",
    recursive: bool = True,
    max_results: int = 50,
) -> List[Path]:
    """Find files matching a glob pattern, sorted by modification time (newest first).

    Automatically excludes Windows Office temporary lock files (prefixed with ~$)
    and other common temporary file patterns that should never be opened.
    """
    # Prefixes/suffixes that indicate a temp/lock file — never include these
    _TEMP_PREFIXES = ("~$",)
    _TEMP_SUFFIXES = (".tmp", ".~lock.")

    base = Path(directory)
    if not base.exists():
        return []
    glob_fn = base.rglob if recursive else base.glob
    files = [
        f for f in glob_fn(pattern)
        if f.is_file()
        and not any(f.name.startswith(p) for p in _TEMP_PREFIXES)
        and not any(f.name.endswith(s) for s in _TEMP_SUFFIXES)
    ]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:max_results]


def find_latest_file(
    directory: Union[str, Path],
    pattern: str = "*.xlsx",
) -> Optional[Path]:
    """Return the most recently modified file matching the pattern."""
    results = find_files(directory, pattern, max_results=1)
    return results[0] if results else None


# Standard locations searched when no directory is specified
_STANDARD_SEARCH_DIRS = [
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home(),
    Path(os.getenv("USERPROFILE", str(Path.home()))),
]

# Extension groups for natural-language type hints
EXTENSION_GROUPS: Dict[str, List[str]] = {
    "pdf":        [".pdf"],
    "excel":      [".xlsx", ".xls", ".xlsm", ".csv"],
    "word":       [".docx", ".doc"],
    "image":      [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"],
    "text":       [".txt", ".md", ".log"],
    "powerpoint": [".pptx", ".ppt"],
    "zip":        [".zip", ".rar", ".7z"],
    "video":      [".mp4", ".avi", ".mkv", ".mov"],
    "audio":      [".mp3", ".wav", ".m4a"],
}


def smart_find_file(
    hint: str = "",
    extensions: List[str] = None,
    locations: List[Union[str, Path]] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """
    Smart multi-location file search that understands natural language hints.

    - Searches Desktop, Downloads, Documents (and any extra locations) simultaneously
    - Matches by extension and keyword fragments found in the filename
    - Ranks by keyword relevance first, then by most recently modified
    - Returns a flat ranked list of file metadata dicts

    Args:
        hint:       Free-text hint — keywords extracted from this (e.g. "sales report pdf")
        extensions: Explicit list of extensions to filter (e.g. [".pdf", ".docx"]).
                    If omitted, inferred from hint keywords.
        locations:  Directories to search. Defaults to Desktop, Downloads, Documents, Home.
        max_results: Maximum total results to return.
    """
    _TEMP_PREFIXES = ("~$",)
    _TEMP_SUFFIXES = (".tmp",)

    hint_lower = (hint or "").lower()

    # --- Infer extensions from hint if not given ---
    if not extensions:
        extensions = []
        for group_name, exts in EXTENSION_GROUPS.items():
            if group_name in hint_lower:
                extensions.extend(exts)
                break
        # Also check for bare extensions like "pdf" or ".pdf" in the hint
        for word in hint_lower.split():
            word = word.lstrip(".")
            candidate = f".{word}"
            if len(word) <= 5 and candidate not in extensions:
                extensions.append(candidate)

    # --- Resolve search directories ---
    search_dirs: List[Path] = []
    for loc in (locations or _STANDARD_SEARCH_DIRS):
        p = Path(os.path.expandvars(os.path.expanduser(str(loc))))
        if p.exists() and p not in search_dirs:
            search_dirs.append(p)
    if not search_dirs:
        search_dirs = [d for d in _STANDARD_SEARCH_DIRS if d.exists()]

    # --- Extract keyword tokens from hint (ignore extension words and stop words) ---
    stop_words = {
        "the", "a", "an", "file", "document", "my", "on", "in", "from",
        "find", "open", "read", "latest", "recent", "newest", "pdf",
        "excel", "word", "image", "text", "folder",
    }
    hint_keywords = [
        w for w in re.sub(r"[^a-z0-9 ]", " ", hint_lower).split()
        if w not in stop_words and len(w) > 1
    ]

    # --- Collect all matching files across all locations ---
    seen: set = set()
    candidates: List[Tuple[int, float, Path]] = []  # (score, -mtime, path)

    for search_dir in search_dirs:
        patterns = [f"*{ext}" for ext in extensions] if extensions else ["*.*"]
        for pat in patterns:
            for f in search_dir.rglob(pat):
                if not f.is_file():
                    continue
                if str(f) in seen:
                    continue
                if any(f.name.startswith(p) for p in _TEMP_PREFIXES):
                    continue
                if any(f.name.endswith(s) for s in _TEMP_SUFFIXES):
                    continue
                seen.add(str(f))

                name_lower = f.name.lower()
                # Keyword relevance score: count how many hint keywords appear in filename
                kw_score = sum(1 for kw in hint_keywords if kw in name_lower)

                mtime = f.stat().st_mtime
                candidates.append((kw_score, mtime, f))

    # --- Sort: highest keyword score first, then newest file first ---
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

    results = []
    for kw_score, mtime, f in candidates[:max_results]:
        meta = file_metadata(f)
        meta["relevance_score"] = kw_score
        results.append(meta)

    return results


def file_metadata(path: Union[str, Path]) -> Dict[str, Any]:
    """Return dict with file size, dates, extension."""
    p = Path(path)
    if not p.exists():
        return {}
    stat = p.stat()
    return {
        "name": p.name,
        "path": str(p.absolute()),
        "size_bytes": stat.st_size,
        "size_kb": round(stat.st_size / 1024, 1),
        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "extension": p.suffix.lower(),
    }


# ─────────────────────────────────────────────
# JSON Utilities
# ─────────────────────────────────────────────

def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract the first valid JSON object from an LLM response string.
    Handles markdown code fences and bare JSON.
    """
    # Strip ```json ... ``` fences
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find first { ... } block
    brace_match = re.search(r"\{[\s\S]+\}", text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def safe_json_dumps(obj: Any, indent: int = 2) -> str:
    """Serialize to JSON with datetime and Path support."""
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Path):
            return str(o)
        if hasattr(o, "model_dump"):
            return o.model_dump()
        return str(o)
    return json.dumps(obj, default=default, indent=indent, ensure_ascii=False)


# ─────────────────────────────────────────────
# Windows Utilities
# ─────────────────────────────────────────────

def open_file_in_explorer(path: Union[str, Path]):
    """Open Windows Explorer with the given file/folder selected."""
    p = Path(path)
    if p.is_file():
        subprocess.run(["explorer", "/select,", str(p)], check=False)
    else:
        subprocess.run(["explorer", str(p)], check=False)


def open_file(path: Union[str, Path]):
    """Open a file with its default Windows application."""
    os.startfile(str(path))


def is_office_available() -> Dict[str, bool]:
    """Check which Office COM servers are registered."""
    result = {"excel": False, "word": False, "outlook": False}
    if sys.platform != "win32":
        return result
    try:
        import win32com.client as win32
        try:
            win32.Dispatch("Excel.Application")
            result["excel"] = True
        except Exception:
            pass
        try:
            win32.Dispatch("Word.Application")
            result["word"] = True
        except Exception:
            pass
        try:
            win32.Dispatch("Outlook.Application")
            result["outlook"] = True
        except Exception:
            pass
    except ImportError:
        pass
    return result


# ─────────────────────────────────────────────
# Timing / Retry
# ─────────────────────────────────────────────

def retry(fn, max_attempts: int = 3, delay: float = 1.0, exceptions=(Exception,)):
    """Simple synchronous retry wrapper."""
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except exceptions as e:
            last_error = e
            if attempt < max_attempts:
                time.sleep(delay * attempt)
    raise last_error


# ─────────────────────────────────────────────
# String Utilities
# ─────────────────────────────────────────────

def truncate(text: str, max_len: int = 200, suffix: str = "...") -> str:
    """Truncate a string to max_len characters."""
    if len(text) <= max_len:
        return text
    return text[:max_len - len(suffix)] + suffix


def bullet_list(items: List[str]) -> str:
    """Format a list as a markdown bullet list."""
    return "\n".join(f"• {item}" for item in items)


def short_id() -> str:
    """Return a short 8-character UUID fragment."""
    return str(uuid.uuid4())[:8]


def human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"
