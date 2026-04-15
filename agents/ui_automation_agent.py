"""
UI Automation Agent — fallback for apps not accessible via COM/API.

Uses pyautogui / pywinauto for:
- Window detection and focusing
- Mouse click and keyboard input
- Screenshot capture
- Text recognition (basic)

This agent is the LAST resort — prefer COM or file-library agents.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from models.schemas import AgentType, RiskLevel
from utils.helpers import ensure_dir, timestamped_filename
from utils.logger import get_logger

logger = get_logger("agents.ui_automation", "ui")

try:
    import pyautogui
    pyautogui.FAILSAFE = True   # Move mouse to corner to abort
    pyautogui.PAUSE = 0.5       # Small delay between actions
    _PYAUTOGUI_AVAILABLE = True
except ImportError:
    _PYAUTOGUI_AVAILABLE = False
    logger.warning("pyautogui not available")

_PYWINAUTO_AVAILABLE = False
if sys.platform == "win32":
    try:
        from pywinauto import Application, Desktop
        from pywinauto.findwindows import ElementNotFoundError
        _PYWINAUTO_AVAILABLE = True
    except ImportError:
        logger.warning("pywinauto not available")

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


class UIAutomationAgent(BaseAgent):
    """Generic desktop UI automation via pyautogui / pywinauto."""

    def __init__(self):
        self._screenshot_dir = Path(
            os.getenv("SCREENSHOT_DIR", str(Path.home() / "AppData/Local/AutoAgent/Screenshots"))
        )
        self._active_window = None
        self._app = None
        super().__init__(AgentType.UI_AUTOMATION)

    def _register_tools(self):
        self.register_tool("ui.find_window",    self.find_window,    "Find a window by title", ["title_pattern"])
        self.register_tool("ui.focus_window",   self.focus_window,   "Focus a window", ["title_pattern"])
        self.register_tool("ui.click",          self.click,          "Click at coordinates", ["x", "y"], risk_level=RiskLevel.MEDIUM)
        self.register_tool("ui.right_click",    self.right_click,    "Right-click at coordinates", ["x", "y"], risk_level=RiskLevel.MEDIUM)
        self.register_tool("ui.double_click",   self.double_click,   "Double-click at coordinates", ["x", "y"], risk_level=RiskLevel.MEDIUM)
        self.register_tool("ui.type_text",      self.type_text,      "Type text into focused window", ["text"], risk_level=RiskLevel.MEDIUM)
        self.register_tool("ui.press_key",      self.press_key,      "Press a keyboard key", ["key"])
        self.register_tool("ui.hotkey",         self.hotkey,         "Press a keyboard shortcut", ["keys"])
        self.register_tool("ui.take_screenshot",self.take_screenshot,"Capture a screenshot")
        self.register_tool("ui.find_image",     self.find_image,     "Find image on screen", ["template_path"])
        self.register_tool("ui.click_image",    self.click_image,    "Click on a template image", ["template_path"], risk_level=RiskLevel.MEDIUM)
        self.register_tool("ui.scroll",         self.scroll,         "Scroll in a window", ["x", "y", "amount"])
        self.register_tool("ui.get_windows",    self.get_windows,    "List all visible windows")
        self.register_tool("ui.wait_for_image", self.wait_for_image, "Wait for image to appear", ["template_path"])

    def _require_pyautogui(self):
        if not _PYAUTOGUI_AVAILABLE:
            raise RuntimeError("pyautogui is not installed. Run: pip install pyautogui")

    def _require_pywinauto(self):
        if not _PYWINAUTO_AVAILABLE:
            raise RuntimeError("pywinauto is not installed. Run: pip install pywinauto")

    # ─────────────────────────────────────────
    # Window Management
    # ─────────────────────────────────────────

    def find_window(self, title_pattern: str) -> Dict[str, Any]:
        """Find a window whose title matches the pattern."""
        if _PYWINAUTO_AVAILABLE:
            try:
                desktop = Desktop(backend="uia")
                windows = desktop.windows()
                matches = [w for w in windows
                           if title_pattern.lower() in (w.window_text() or "").lower()]
                return {
                    "found": len(matches) > 0,
                    "count": len(matches),
                    "windows": [{"title": w.window_text(), "handle": w.handle} for w in matches[:5]],
                }
            except Exception as e:
                return {"found": False, "error": str(e)}

        elif _PYAUTOGUI_AVAILABLE:
            windows = pyautogui.getAllWindows() if hasattr(pyautogui, "getAllWindows") else []
            matches = [w for w in windows if title_pattern.lower() in w.title.lower()]
            return {
                "found": len(matches) > 0,
                "count": len(matches),
                "windows": [{"title": w.title} for w in matches[:5]],
            }

        return {"found": False, "error": "No window automation library available"}

    def get_windows(self) -> Dict[str, Any]:
        """List all visible windows."""
        if _PYWINAUTO_AVAILABLE:
            try:
                desktop = Desktop(backend="uia")
                windows = [
                    {"title": w.window_text(), "handle": w.handle}
                    for w in desktop.windows()
                    if w.window_text()
                ]
                return {"windows": windows, "count": len(windows)}
            except Exception as e:
                return {"windows": [], "error": str(e)}
        return {"windows": [], "error": "pywinauto not available"}

    def focus_window(self, title_pattern: str) -> Dict[str, Any]:
        """Bring a window to focus."""
        if _PYWINAUTO_AVAILABLE:
            try:
                desktop = Desktop(backend="uia")
                for w in desktop.windows():
                    if title_pattern.lower() in (w.window_text() or "").lower():
                        w.set_focus()
                        time.sleep(0.5)
                        return {"focused": True, "title": w.window_text()}
            except Exception as e:
                return {"focused": False, "error": str(e)}
        return {"focused": False, "error": "pywinauto not available"}

    # ─────────────────────────────────────────
    # Mouse Actions
    # ─────────────────────────────────────────

    def click(self, x: int, y: int, button: str = "left") -> Dict[str, Any]:
        """Click at screen coordinates."""
        self._require_pyautogui()
        # Safety: don't click on corners (pyautogui failsafe zone)
        screen_w, screen_h = pyautogui.size()
        if x < 10 or y < 10 or x > screen_w - 10 or y > screen_h - 10:
            raise ValueError(f"Click coordinates too close to screen edge: ({x}, {y})")
        pyautogui.click(x, y, button=button)
        return {"clicked": True, "x": x, "y": y, "button": button}

    def right_click(self, x: int, y: int) -> Dict[str, Any]:
        return self.click(x, y, button="right")

    def double_click(self, x: int, y: int) -> Dict[str, Any]:
        self._require_pyautogui()
        pyautogui.doubleClick(x, y)
        return {"double_clicked": True, "x": x, "y": y}

    def scroll(self, x: int, y: int, amount: int = 3) -> Dict[str, Any]:
        """Scroll at coordinates."""
        self._require_pyautogui()
        pyautogui.scroll(amount, x=x, y=y)
        return {"scrolled": True, "x": x, "y": y, "amount": amount}

    # ─────────────────────────────────────────
    # Keyboard Actions
    # ─────────────────────────────────────────

    def type_text(self, text: str, interval: float = 0.05) -> Dict[str, Any]:
        """Type text into the focused window."""
        self._require_pyautogui()
        pyautogui.write(text, interval=interval)
        return {"typed": True, "length": len(text)}

    def press_key(self, key: str) -> Dict[str, Any]:
        """Press a single key (e.g. 'enter', 'tab', 'escape')."""
        self._require_pyautogui()
        pyautogui.press(key)
        return {"pressed": True, "key": key}

    def hotkey(self, keys: List[str]) -> Dict[str, Any]:
        """Press a keyboard shortcut (e.g. ['ctrl', 's'])."""
        self._require_pyautogui()
        pyautogui.hotkey(*keys)
        return {"hotkey": True, "keys": keys}

    # ─────────────────────────────────────────
    # Screenshots & Image Recognition
    # ─────────────────────────────────────────

    def take_screenshot(self, output_path: str = None) -> Dict[str, Any]:
        """Capture the full screen."""
        self._require_pyautogui()
        if not output_path:
            ensure_dir(self._screenshot_dir)
            output_path = str(self._screenshot_dir / timestamped_filename("screenshot", "png"))
        screenshot = pyautogui.screenshot()
        screenshot.save(output_path)
        return {"captured": True, "path": output_path}

    def find_image(self, template_path: str, confidence: float = 0.8) -> Dict[str, Any]:
        """Find a template image on screen. Returns center coordinates."""
        self._require_pyautogui()
        if not Path(template_path).exists():
            return {"found": False, "error": f"Template not found: {template_path}"}
        try:
            location = pyautogui.locateCenterOnScreen(template_path, confidence=confidence)
            if location:
                return {"found": True, "x": location.x, "y": location.y}
            return {"found": False}
        except Exception as e:
            return {"found": False, "error": str(e)}

    def click_image(self, template_path: str, confidence: float = 0.8) -> Dict[str, Any]:
        """Find and click a template image on screen."""
        result = self.find_image(template_path, confidence)
        if result.get("found"):
            return self.click(result["x"], result["y"])
        return {"clicked": False, "error": "Image not found on screen"}

    def wait_for_image(
        self,
        template_path: str,
        timeout: float = 10.0,
        confidence: float = 0.8,
    ) -> Dict[str, Any]:
        """Wait until a template image appears on screen."""
        self._require_pyautogui()
        start = time.time()
        while time.time() - start < timeout:
            result = self.find_image(template_path, confidence)
            if result.get("found"):
                return result
            time.sleep(0.5)
        return {"found": False, "timeout": True}
