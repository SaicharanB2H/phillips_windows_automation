"""
File System Agent — file discovery, reading, writing, and workspace management.

Capabilities:
- Find files by name, type, directory, modification date
- Resolve ambiguous file references ("latest sales file")
- Create versioned output directories
- Read/write text files
- Verify paths and avoid overwrites
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from agents.base_agent import BaseAgent
from models.schemas import AgentType, RiskLevel
from utils.helpers import (
    EXTENSION_GROUPS, ensure_dir, file_metadata, find_files, find_latest_file,
    get_desktop_path, get_documents_path, get_downloads_path,
    human_size, safe_filename, smart_find_file, timestamped_filename,
)
from utils.logger import get_logger

logger = get_logger("agents.file", "file")


# Common search shorthand directories — includes natural-language variants
DIR_ALIASES = {
    # Standard
    "desktop":          get_desktop_path,
    "downloads":        get_downloads_path,
    "documents":        get_documents_path,
    "home":             Path.home,
    "temp":             lambda: Path(os.getenv("TEMP", "/tmp")),
    # Natural-language variants the LLM may produce
    "my desktop":       get_desktop_path,
    "my downloads":     get_downloads_path,
    "my documents":     get_documents_path,
    "the desktop":      get_desktop_path,
    "the downloads":    get_downloads_path,
    "the documents":    get_documents_path,
    "user desktop":     get_desktop_path,
    "user downloads":   get_downloads_path,
    "user home":        Path.home,
    "~":                Path.home,
}


class FileAgent(BaseAgent):
    """Manages file discovery, reading, and workspace operations."""

    def __init__(self):
        self._workspace: Optional[Path] = None
        super().__init__(AgentType.FILE)

    def _register_tools(self):
        # Primary names (files.*)
        self.register_tool("files.read_pdf",         self.read_pdf,         "Extract full text from a PDF file", ["path"])
        self.register_tool("file.read_pdf",          self.read_pdf,         "Extract full text from a PDF file", ["path"])
        self.register_tool("files.smart_find",       self.smart_find,       "Smart multi-location file search (USE THIS for vague references)", ["hint"])
        self.register_tool("files.search",           self.search,           "Search for files by pattern in a specific directory", ["directory", "pattern"])
        self.register_tool("files.list_recent",      self.list_recent,      "List recently modified files", ["extension"])
        self.register_tool("files.get_metadata",     self.get_metadata,     "Get file metadata", ["path"])
        self.register_tool("files.verify_exists",    self.verify_exists,    "Check if file exists", ["path"])
        self.register_tool("files.read_text",        self.read_text,        "Read text file contents", ["path"])
        self.register_tool("files.write_text",       self.write_text,       "Write text to file", ["path", "content"], risk_level=RiskLevel.MEDIUM)
        self.register_tool("files.copy",             self.copy,             "Copy a file", ["src", "dst"], risk_level=RiskLevel.MEDIUM)
        self.register_tool("files.delete",           self.delete,           "Delete a file", ["path"], risk_level=RiskLevel.HIGH)
        self.register_tool("files.create_directory", self.create_directory, "Create a directory", ["path"])
        self.register_tool("files.list_directory",   self.list_directory,   "List directory contents", ["path"])
        self.register_tool("files.find_by_keyword",  self.find_by_keyword,  "Find files whose name contains keyword", ["directory", "keyword"])
        self.register_tool("files.get_output_path",  self.get_output_path,  "Get a safe output file path", ["filename"])
        self.register_tool("files.setup_workspace",  self.setup_workspace,  "Create a temp workspace for the session")

        # Aliases without trailing 's' — LLM sometimes generates file.* instead of files.*
        self.register_tool("file.smart_find",        self.smart_find,       "Smart multi-location file search", ["hint"])
        self.register_tool("file.search",            self.search,           "Search for files by pattern", ["directory", "pattern"])
        self.register_tool("file.list_recent",       self.list_recent,      "List recently modified files", ["extension"])
        self.register_tool("file.get_metadata",      self.get_metadata,     "Get file metadata", ["path"])
        self.register_tool("file.verify_exists",     self.verify_exists,    "Check if file exists", ["path"])
        self.register_tool("file.read_text",         self.read_text,        "Read text file contents", ["path"])
        self.register_tool("file.list_directory",    self.list_directory,   "List directory contents", ["path"])
        self.register_tool("file.find_by_keyword",   self.find_by_keyword,  "Find files by keyword", ["directory", "keyword"])
        self.register_tool("file.get_output_path",   self.get_output_path,  "Get a safe output file path", ["filename"])

    # ─────────────────────────────────────────
    # Search & Discovery
    # ─────────────────────────────────────────

    def smart_find(
        self,
        hint: str = "",
        extensions: List[str] = None,
        locations: List[str] = None,
        latest: bool = True,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        Smart file finder — searches Desktop, Downloads, Documents and any extra
        locations simultaneously, matching by file type and keyword relevance.

        USE THIS whenever the user says things like:
        - "the PDF on my Desktop"
        - "the latest Excel file"
        - "find the invoice document"
        - "read the document in my files"

        Args:
            hint:       Natural language description — e.g. "sales pdf", "invoice excel"
            extensions: Optional explicit extension filter — e.g. [".pdf"]
            locations:  Extra directories to search in addition to the defaults
            latest:     If True, return only the single best match
            max_results: Max results to return when latest=False
        """
        resolved_locs = []
        for loc in (locations or []):
            resolved_locs.append(self._resolve_dir(loc))

        results = smart_find_file(
            hint=hint,
            extensions=extensions,
            locations=resolved_locs or None,
            max_results=max_results,
        )

        if not results:
            logger.warning(f"smart_find: no files found for hint='{hint}' ext={extensions}")
            return {
                "found": False,
                "error": (
                    f"No files found matching '{hint}'. "
                    "Searched Desktop, Downloads, Documents, and Home. "
                    "Please check the file exists or provide an exact path."
                ),
                "files": [],
                "path": None,
            }

        if latest:
            results = results[:1]

        logger.info(
            f"smart_find: found {len(results)} file(s) for hint='{hint}' — "
            f"best: {results[0]['name']}"
        )
        return {
            "found": True,
            "count": len(results),
            "hint": hint,
            "files": results,
            "path": results[0]["path"],
        }

    def search(
        self,
        directory: str,
        pattern: str = "*",
        latest: bool = False,
        max_results: int = 20,
        recursive: bool = True,
    ) -> Dict[str, Any]:
        """
        Find files matching a glob pattern in a specific directory.
        Automatically falls back to Desktop/Downloads/Documents if nothing found.
        """
        base = self._resolve_dir(directory)

        # Primary search
        if base.exists():
            files = find_files(base, pattern, recursive=recursive, max_results=max_results)
        else:
            logger.warning(f"search: directory not found — {base}, trying fallback locations")
            files = []

        # Auto-fallback: search common locations if nothing found in specified dir
        if not files:
            fallback_dirs = [
                get_desktop_path(), get_downloads_path(), get_documents_path(), Path.home()
            ]
            for fb_dir in fallback_dirs:
                if fb_dir == base or not fb_dir.exists():
                    continue
                fb_files = find_files(fb_dir, pattern, recursive=False, max_results=max_results)
                if fb_files:
                    logger.info(f"search fallback: found {len(fb_files)} file(s) in {fb_dir}")
                    files.extend(fb_files)
                    if len(files) >= max_results:
                        break

        if latest and files:
            files = [files[0]]

        results = [file_metadata(f) for f in files[:max_results]]
        logger.info(f"search: {len(results)} file(s) in '{base}' matching '{pattern}'")

        return {
            "found": len(results) > 0,
            "count": len(results),
            "directory": str(base),
            "pattern": pattern,
            "files": results,
            "path": results[0]["path"] if results else None,
        }

    def list_recent(
        self,
        extension: str = ".xlsx",
        count: int = 5,
        directories: List[str] = None,
    ) -> Dict[str, Any]:
        """List the N most recently modified files of a given type."""
        search_dirs = directories or ["downloads", "desktop", "documents"]
        all_files = []

        for d in search_dirs:
            base = self._resolve_dir(d)
            if base.exists():
                found = find_files(base, f"*{extension}", max_results=50)
                all_files.extend(found)

        # Sort by modified time
        all_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        top = all_files[:count]
        results = [file_metadata(f) for f in top]

        return {
            "count": len(results),
            "extension": extension,
            "files": results,
            "path": results[0]["path"] if results else None,
        }

    def find_by_keyword(
        self,
        directory: str,
        keyword: str,
        extension: str = None,
        latest: bool = True,
    ) -> Dict[str, Any]:
        """Find files whose names contain the given keyword."""
        base = self._resolve_dir(directory)
        if not base.exists():
            return {"found": False, "files": []}

        pattern = f"*{keyword}*{extension or ''}"
        files = find_files(base, pattern, max_results=10)

        if latest and files:
            files = [files[0]]

        results = [file_metadata(f) for f in files]
        return {
            "found": len(results) > 0,
            "count": len(results),
            "files": results,
            "path": results[0]["path"] if results else None,
        }

    def get_metadata(self, path: str) -> Dict[str, Any]:
        """Return metadata for a file."""
        resolved = self._resolve_path(path)
        if not resolved.exists():
            return {"exists": False, "path": str(resolved)}
        meta = file_metadata(resolved)
        meta["exists"] = True
        return meta

    def verify_exists(self, path: str) -> Dict[str, Any]:
        """Check if a path exists and return type (file/directory)."""
        resolved = self._resolve_path(path)
        exists = resolved.exists()
        return {
            "exists": exists,
            "path": str(resolved),
            "is_file": resolved.is_file() if exists else False,
            "is_directory": resolved.is_dir() if exists else False,
        }

    # ─────────────────────────────────────────
    # Read / Write
    # ─────────────────────────────────────────

    def read_pdf(self, path: str, max_pages: int = 0) -> Dict[str, Any]:
        """
        Extract text from a PDF file using the best available Python library.
        Tries pdfplumber → pypdf → pdfminer automatically — no external tools needed.

        Args:
            path:      Full path to the PDF file.
            max_pages: Maximum pages to extract (0 = all pages).
        """
        resolved = self._resolve_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"PDF not found: {resolved}")
        if resolved.suffix.lower() != ".pdf":
            raise ValueError(f"Not a PDF file: {resolved.name}")

        text = self._extract_pdf_text(resolved, max_pages)
        pages = text.count("\f") + 1  # form-feed chars separate pages

        logger.info(f"PDF extracted: {resolved.name} — {len(text)} chars, ~{pages} pages")
        return {
            "path":       str(resolved),
            "name":       resolved.name,
            "text":       text,
            "char_count": len(text),
            "page_count": pages,
            "size_bytes": resolved.stat().st_size,
        }

    @staticmethod
    def _extract_pdf_text(path: "Path", max_pages: int) -> str:
        """Try PDF libraries in order of quality until one succeeds."""
        # ── 1. pdfplumber (best table/layout-aware extraction) ─────────────
        try:
            import pdfplumber
            pages_text = []
            with pdfplumber.open(str(path)) as pdf:
                pages = pdf.pages if not max_pages else pdf.pages[:max_pages]
                for page in pages:
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
            if pages_text:
                return "\n\n".join(pages_text)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e} — trying pypdf")

        # ── 2. pypdf (fast, pure Python) ────────────────────────────────────
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            pages = reader.pages if not max_pages else reader.pages[:max_pages]
            parts = []
            for page in pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
            if parts:
                return "\n\n".join(parts)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"pypdf failed: {e} — trying pdfminer")

        # ── 3. PyPDF2 (older but widely installed) ──────────────────────────
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(str(path))
            pages = reader.pages if not max_pages else reader.pages[:max_pages]
            parts = [p.extract_text() or "" for p in pages]
            text = "\n\n".join(p for p in parts if p.strip())
            if text.strip():
                return text
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"PyPDF2 failed: {e} — trying pdfminer")

        # ── 4. pdfminer.six (most thorough, slowest) ────────────────────────
        try:
            from pdfminer.high_level import extract_text as pdfminer_extract
            text = pdfminer_extract(str(path), maxpages=max_pages or 0)
            if text and text.strip():
                return text
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"pdfminer failed: {e}")

        raise RuntimeError(
            "Could not extract PDF text. Install pdfplumber or pypdf:\n"
            "  pip install pdfplumber\n  pip install pypdf"
        )

    def read_text(self, path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """Read a text file."""
        resolved = self._resolve_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {resolved}")
        try:
            content = resolved.read_text(encoding=encoding, errors="replace")
        except UnicodeDecodeError:
            content = resolved.read_text(encoding="latin-1", errors="replace")
        return {
            "path": str(resolved),
            "content": content,
            "size_bytes": resolved.stat().st_size,
            "lines": content.count("\n") + 1,
        }

    def write_text(
        self,
        path: str,
        content: str,
        overwrite: bool = False,
        encoding: str = "utf-8",
    ) -> Dict[str, Any]:
        """Write text content to a file."""
        resolved = self._resolve_path(path)
        if resolved.exists() and not overwrite:
            # Version the existing file
            stem = resolved.stem
            suffix = resolved.suffix
            versioned = resolved.parent / f"{stem}_backup_{datetime.now().strftime('%H%M%S')}{suffix}"
            shutil.copy2(resolved, versioned)
            logger.info(f"Existing file backed up to: {versioned}")

        ensure_dir(resolved.parent)
        resolved.write_text(content, encoding=encoding)
        size = resolved.stat().st_size
        logger.info(f"Written: {resolved} ({human_size(size)})")
        return {"written": True, "path": str(resolved), "size_bytes": size}

    def copy(self, src: str, dst: str, overwrite: bool = False) -> Dict[str, Any]:
        """Copy a file to a new location."""
        src_path = self._resolve_path(src)
        dst_path = self._resolve_path(dst)

        if not src_path.exists():
            raise FileNotFoundError(f"Source not found: {src_path}")
        if dst_path.exists() and not overwrite:
            raise FileExistsError(f"Destination exists (use overwrite=True): {dst_path}")

        ensure_dir(dst_path.parent)
        shutil.copy2(src_path, dst_path)
        return {"copied": True, "src": str(src_path), "dst": str(dst_path)}

    def delete(self, path: str, to_trash: bool = True) -> Dict[str, Any]:
        """Delete a file (moves to recycle bin if to_trash=True on Windows)."""
        resolved = self._resolve_path(path)
        if not resolved.exists():
            return {"deleted": False, "error": f"File not found: {resolved}"}

        if to_trash and sys.platform == "win32":
            try:
                import send2trash
                send2trash.send2trash(str(resolved))
                return {"deleted": True, "method": "trash", "path": str(resolved)}
            except ImportError:
                pass  # Fall through to permanent delete

        resolved.unlink()
        logger.warning(f"Permanently deleted: {resolved}")
        return {"deleted": True, "method": "permanent", "path": str(resolved)}

    # ─────────────────────────────────────────
    # Directory Operations
    # ─────────────────────────────────────────

    def create_directory(self, path: str) -> Dict[str, Any]:
        """Create a directory (with parents)."""
        resolved = self._resolve_path(path)
        resolved.mkdir(parents=True, exist_ok=True)
        return {"created": True, "path": str(resolved)}

    def list_directory(
        self,
        path: str,
        extension_filter: str = None,
        max_items: int = 50,
    ) -> Dict[str, Any]:
        """List directory contents."""
        resolved = self._resolve_path(path)
        if not resolved.exists():
            return {"exists": False, "files": []}

        _TEMP_PREFIXES = ("~$",)
        items = sorted(resolved.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        # Exclude Office lock files (e.g. ~$sales.xlsx) and temp files
        items = [i for i in items if not any(i.name.startswith(p) for p in _TEMP_PREFIXES)]
        if extension_filter:
            items = [i for i in items if i.suffix.lower() == extension_filter.lower()]

        results = []
        for item in items[:max_items]:
            results.append({
                "name": item.name,
                "path": str(item),
                "is_file": item.is_file(),
                "is_dir": item.is_dir(),
                "size_bytes": item.stat().st_size if item.is_file() else 0,
                "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
            })

        return {"path": str(resolved), "count": len(results), "items": results}

    def setup_workspace(self, session_id: str = None) -> Dict[str, Any]:
        """Create a dedicated output workspace for this session."""
        base = Path(os.getenv("OUTPUT_DIR", str(get_desktop_path() / "AutoAgent_Output")))
        if session_id:
            ws = base / f"session_{session_id[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        else:
            ws = base / datetime.now().strftime("%Y%m%d_%H%M%S")
        ws.mkdir(parents=True, exist_ok=True)
        self._workspace = ws
        logger.info(f"Workspace created: {ws}")
        return {"workspace": str(ws), "created": True}

    def get_output_path(self, filename: str, subdir: str = None) -> Dict[str, Any]:
        """Get a safe output path within the workspace or Desktop."""
        base = self._workspace or get_desktop_path()
        if subdir:
            base = base / subdir
            base.mkdir(parents=True, exist_ok=True)
        path = base / safe_filename(filename)
        # Avoid overwrite by versioning
        if path.exists():
            stem, suffix = path.stem, path.suffix
            path = base / f"{stem}_{datetime.now().strftime('%H%M%S')}{suffix}"
        return {"path": str(path), "directory": str(base)}

    # ─────────────────────────────────────────
    # Internal Helpers
    # ─────────────────────────────────────────

    def _resolve_dir(self, directory: str) -> Path:
        """Resolve directory alias or literal path."""
        alias = directory.lower().strip().rstrip("/\\")
        if alias in DIR_ALIASES:
            return DIR_ALIASES[alias]()
        return Path(os.path.expandvars(os.path.expanduser(directory)))

    def _resolve_path(self, path: str) -> Path:
        """Expand variables/user in a file path."""
        return Path(os.path.expandvars(os.path.expanduser(path)))


import sys  # ensure sys is imported for delete method
