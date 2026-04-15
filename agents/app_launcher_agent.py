"""
App Launcher Agent — open any Windows application by name.

Capabilities:
- Open apps by name, alias, or description ("chrome", "browser", "excel")
- Searches: built-in registry → PATH → Start Menu shortcuts → Program Files
- Returns immediately after launching (non-blocking)
- list_apps() to discover installed apps
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import winreg
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from models.schemas import AgentType, RiskLevel
from utils.logger import get_logger

logger = get_logger("agents.app_launcher", "launcher")


# ─────────────────────────────────────────────
# Built-in app registry — common name → command
# ─────────────────────────────────────────────

_BUILTIN_APPS: Dict[str, str] = {
    # Browsers
    "chrome":           "chrome",
    "google chrome":    "chrome",
    "browser":          "chrome",
    "firefox":          "firefox",
    "mozilla firefox":  "firefox",
    "edge":             "msedge",
    "microsoft edge":   "msedge",
    "internet explorer": "iexplore",
    "brave":            "brave",

    # Microsoft Office
    "excel":            "excel",
    "microsoft excel":  "excel",
    "word":             "winword",
    "microsoft word":   "winword",
    "powerpoint":       "powerpnt",
    "microsoft powerpoint": "powerpnt",
    "outlook":          "outlook",
    "microsoft outlook": "outlook",
    "onenote":          "onenote",
    "teams":            "teams",
    "microsoft teams":  "teams",

    # Windows built-ins
    "notepad":          "notepad",
    "notepad++":        "notepad++",
    "calculator":       "calc",
    "calc":             "calc",
    "paint":            "mspaint",
    "ms paint":         "mspaint",
    "wordpad":          "wordpad",
    "explorer":         "explorer",
    "file explorer":    "explorer",
    "task manager":     "taskmgr",
    "control panel":    "control",
    "settings":         "ms-settings:",
    "windows settings": "ms-settings:",
    "snipping tool":    "snippingtool",
    "snip":             "snippingtool",
    "screenshot":       "snippingtool",
    "cmd":              "cmd",
    "command prompt":   "cmd",
    "powershell":       "powershell",
    "terminal":         "wt",
    "windows terminal": "wt",
    "regedit":          "regedit",
    "registry editor":  "regedit",
    "device manager":   "devmgmt.msc",
    "disk management":  "diskmgmt.msc",
    "event viewer":     "eventvwr.msc",
    "services":         "services.msc",
    "msconfig":         "msconfig",
    "system info":      "msinfo32",
    "character map":    "charmap",
    "clock":            "timedate.cpl",

    # Media & entertainment
    "vlc":              "vlc",
    "media player":     "wmplayer",
    "windows media player": "wmplayer",
    "spotify":          "spotify",
    "photos":           "ms-photos:",

    # Development
    "vscode":           "code",
    "vs code":          "code",
    "visual studio code": "code",
    "visual studio":    "devenv",
    "pycharm":          "pycharm",
    "git bash":         "git-bash",
    "github desktop":   "github",
    "postman":          "postman",

    # Utilities
    "7zip":             "7zFM",
    "7-zip":            "7zFM",
    "winrar":           "winrar",
    "zoom":             "zoom",
    "slack":            "slack",
    "discord":          "discord",
    "telegram":         "telegram",
    "whatsapp":         "whatsapp",
    "skype":            "skype",
    "steam":            "steam",
    "epic games":       "epicgameslauncher",
    "obs":              "obs64",
    "obs studio":       "obs64",
    "anydesk":          "anydesk",
    "teamviewer":       "teamviewer",
    "cpu-z":            "cpuz",
    "cpu z":            "cpuz",
    "gpu-z":            "gpuz",
    "hwinfo":           "hwinfo64",
    "winamp":           "winamp",

    # Adobe
    "photoshop":        "photoshop",
    "adobe photoshop":  "photoshop",
    "acrobat":          "acrobat",
    "adobe acrobat":    "acrobat",
    "premiere":         "premiere",
    "illustrator":      "illustrator",

    # Productivity
    "notion":           "notion",
    "obsidian":         "obsidian",
    "todoist":          "todoist",
    "onenote":          "onenote",
    "evernote":         "evernote",
    "keepass":          "keepass",
    "bitwarden":        "bitwarden",
}

# Windows shell protocol URIs (launched via explorer)
_PROTOCOL_APPS = {"ms-settings:", "ms-photos:"}

# Start Menu search paths
_START_MENU_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
]

# Program Files search paths
_PROG_DIRS = [
    Path(r"C:\Program Files"),
    Path(r"C:\Program Files (x86)"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
    Path(os.environ.get("LOCALAPPDATA", "")),
    Path(os.environ.get("APPDATA", "")),
]


class AppLauncherAgent(BaseAgent):
    """Launches Windows applications by name."""

    def __init__(self):
        self._lnk_cache: Optional[List[Dict[str, str]]] = None
        super().__init__(AgentType.APP_LAUNCHER)

    def _register_tools(self):
        self.register_tool(
            "app.open",
            self.open_app,
            "Open / launch any Windows application by name",
            ["name"],
            risk_level=RiskLevel.LOW,
        )
        self.register_tool(
            "app.launch",          # alias
            self.open_app,
            "Launch a Windows application by name",
            ["name"],
            risk_level=RiskLevel.LOW,
        )
        self.register_tool(
            "app.list",
            self.list_apps,
            "List installed applications found in Start Menu",
            [],
            risk_level=RiskLevel.LOW,
        )
        self.register_tool(
            "app.close",
            self.close_app,
            "Close / kill a running application by name",
            ["name"],
            risk_level=RiskLevel.MEDIUM,
        )
        self.register_tool(
            "app.is_running",
            self.is_running,
            "Check if an application is currently running",
            ["name"],
            risk_level=RiskLevel.LOW,
        )

    # ─────────────────────────────────────────
    # Tools
    # ─────────────────────────────────────────

    def open_app(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        Launch an application by natural-language name.

        Resolution order:
        1. Built-in alias registry
        2. PATH lookup via `where`
        3. Start Menu .lnk shortcuts (fuzzy name match)
        4. Program Files executable search
        5. Windows Registry App Paths
        """
        logger.info(f"Launching app: {name!r}")
        key = name.strip().lower()

        # ── 1. Built-in aliases ───────────────
        cmd = _BUILTIN_APPS.get(key)
        if cmd:
            return self._launch(cmd, name)

        # ── 2. Fuzzy alias match ──────────────
        for alias, exe in _BUILTIN_APPS.items():
            if key in alias or alias in key:
                return self._launch(exe, name)

        # ── 3. PATH lookup ────────────────────
        result = self._find_in_path(key)
        if result:
            return self._launch(result, name)

        # ── 4. Start Menu shortcuts ───────────
        lnk = self._find_in_start_menu(key)
        if lnk:
            return self._launch_lnk(lnk, name)

        # ── 5. Program Files scan ─────────────
        exe = self._find_in_prog_files(key)
        if exe:
            return self._launch(str(exe), name)

        # ── 6. Registry App Paths ─────────────
        reg_path = self._find_in_registry(key)
        if reg_path:
            return self._launch(reg_path, name)

        raise ValueError(
            f"Could not find application '{name}'.\n"
            f"Try: app.list() to see installed apps, or provide the exact exe name."
        )

    def list_apps(self, filter: str = "", **kwargs) -> Dict[str, Any]:
        """List installed applications from Start Menu shortcuts."""
        apps = self._get_lnk_cache()
        if filter:
            fl = filter.lower()
            apps = [a for a in apps if fl in a["name"].lower()]

        return {
            "count": len(apps),
            "apps": apps,
            "filter": filter or None,
        }

    def close_app(self, name: str, **kwargs) -> Dict[str, Any]:
        """Kill a running process by name (taskkill)."""
        key = name.strip().lower()
        # Map friendly name to process name
        proc = _BUILTIN_APPS.get(key, key)
        # Strip path, keep exe name
        proc_exe = Path(proc).stem if "\\" in proc or "/" in proc else proc
        if not proc_exe.endswith(".exe"):
            proc_exe += ".exe"

        result = subprocess.run(
            ["taskkill", "/F", "/IM", proc_exe],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info(f"Closed: {proc_exe}")
            return {"closed": True, "process": proc_exe, "message": f"Closed {name}"}
        else:
            raise RuntimeError(
                f"Could not close '{name}' ({proc_exe}): {result.stderr.strip()}"
            )

    def is_running(self, name: str, **kwargs) -> Dict[str, Any]:
        """Check if a process is running via tasklist."""
        key = name.strip().lower()
        proc = _BUILTIN_APPS.get(key, key)
        proc_exe = Path(proc).stem if "\\" in proc or "/" in proc else proc
        if not proc_exe.endswith(".exe"):
            proc_exe += ".exe"

        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {proc_exe}", "/NH"],
            capture_output=True, text=True,
        )
        running = proc_exe.lower() in result.stdout.lower()
        return {"running": running, "process": proc_exe, "app": name}

    # ─────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────

    def _launch(self, cmd: str, friendly_name: str) -> Dict[str, Any]:
        """Launch a command / exe and return immediately."""
        try:
            if cmd in _PROTOCOL_APPS or cmd.endswith(":"):
                # Windows URI protocol (e.g. ms-settings:)
                os.startfile(cmd)
            else:
                subprocess.Popen(
                    cmd,
                    shell=True,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            logger.info(f"Launched: {cmd!r}")
            return {
                "launched": True,
                "app": friendly_name,
                "command": cmd,
                "message": f"✓ Opened {friendly_name}",
            }
        except Exception as e:
            raise RuntimeError(f"Failed to launch '{friendly_name}': {e}")

    def _launch_lnk(self, lnk_path: str, friendly_name: str) -> Dict[str, Any]:
        """Launch via a .lnk Start Menu shortcut using os.startfile."""
        try:
            os.startfile(lnk_path)
            logger.info(f"Launched via shortcut: {lnk_path!r}")
            return {
                "launched": True,
                "app": friendly_name,
                "command": lnk_path,
                "message": f"✓ Opened {friendly_name}",
            }
        except Exception as e:
            raise RuntimeError(f"Failed to launch shortcut '{lnk_path}': {e}")

    def _find_in_path(self, name: str) -> Optional[str]:
        """Try `where <name>` and `where <name>.exe`."""
        for candidate in [name, f"{name}.exe"]:
            try:
                r = subprocess.run(
                    ["where", candidate],
                    capture_output=True, text=True,
                )
                if r.returncode == 0:
                    first = r.stdout.strip().splitlines()[0]
                    if first:
                        return first
            except Exception:
                pass
        return None

    def _find_in_start_menu(self, name: str) -> Optional[str]:
        """Fuzzy-match name against Start Menu .lnk files."""
        best: Optional[str] = None
        best_score = 0

        for d in _START_MENU_DIRS:
            try:
                for lnk in glob.glob(str(d / "**" / "*.lnk"), recursive=True):
                    stem = Path(lnk).stem.lower()
                    score = self._match_score(name, stem)
                    if score > best_score:
                        best_score = score
                        best = lnk
            except Exception:
                continue

        # Only return if reasonably confident
        return best if best_score >= 60 else None

    def _find_in_prog_files(self, name: str) -> Optional[Path]:
        """Search Program Files directories for an exe matching name."""
        for base in _PROG_DIRS:
            if not base.exists():
                continue
            try:
                for exe in base.rglob(f"{name}*.exe"):
                    # Avoid uninstallers / updaters
                    if any(skip in exe.name.lower() for skip in ("unins", "setup", "update", "crash")):
                        continue
                    return exe
            except (PermissionError, OSError):
                continue
        return None

    def _find_in_registry(self, name: str) -> Optional[str]:
        """Check HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths."""
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
        candidates = [name, f"{name}.exe"]
        for candidate in candidates:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{key_path}\\{candidate}")
                path, _ = winreg.QueryValueEx(key, "")
                winreg.CloseKey(key)
                if path:
                    return path
            except FileNotFoundError:
                continue
            except Exception:
                continue
        return None

    def _match_score(self, query: str, target: str) -> int:
        """Simple fuzzy score: 100 = exact, 80 = startswith, 60 = contains."""
        q, t = query.lower(), target.lower()
        if q == t:
            return 100
        if t.startswith(q) or q.startswith(t):
            return 85
        if q in t or t in q:
            return 70
        # Word-level partial match
        query_words = set(re.split(r"[\s\-_]+", q))
        target_words = set(re.split(r"[\s\-_]+", t))
        overlap = query_words & target_words
        if overlap:
            return 60
        return 0

    def _get_lnk_cache(self) -> List[Dict[str, str]]:
        """Build and cache a list of all Start Menu apps."""
        if self._lnk_cache is not None:
            return self._lnk_cache

        apps = []
        seen = set()
        for d in _START_MENU_DIRS:
            try:
                for lnk in sorted(glob.glob(str(d / "**" / "*.lnk"), recursive=True)):
                    name = Path(lnk).stem
                    if name.lower() in seen:
                        continue
                    seen.add(name.lower())
                    apps.append({"name": name, "shortcut": lnk})
            except Exception:
                continue

        self._lnk_cache = sorted(apps, key=lambda a: a["name"].lower())
        logger.info(f"App cache built: {len(self._lnk_cache)} apps")
        return self._lnk_cache
