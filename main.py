"""
Desktop Automation Agent — Entry Point

Initializes:
1. Environment variables from .env
2. Logging
3. QApplication with dark theme
4. Main window
"""
from __future__ import annotations

import sys
import os
from pathlib import Path


def load_env():
    """Load .env file before anything else."""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        # Try .env.example as fallback for first run
        example = Path(__file__).parent / ".env.example"
        if example.exists():
            print(
                "[WARN] No .env found. Using .env.example defaults. "
                "Copy .env.example to .env and add your GROK_API_KEY."
            )
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    except ImportError:
        print("[WARN] python-dotenv not installed. Environment variables must be set manually.")


def setup_logging():
    from utils.logger import setup_logging as _setup
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_file = os.getenv("LOG_FILE", "logs/autoagent.log")
    _setup(log_level=log_level, log_file=log_file)


def _make_app_icon() -> "QIcon":
    """
    Build a multi-resolution QIcon for the title bar and taskbar.
    Renders a rounded-square accent-blue tile with a white bot SVG centred on it.
    Sizes: 16, 32, 48, 64, 128 px — Windows uses all of them.
    """
    from PySide6.QtGui import QIcon, QPainter, QColor, QPainterPath
    from PySide6.QtCore import QRectF, QSize
    from PySide6.QtWidgets import QApplication
    from icons.icon_manager import get_pixmap

    ACCENT  = QColor("#4F9DFF")   # accent blue
    FG      = "#FFFFFF"           # white bot icon

    icon = QIcon()

    for size in (16, 32, 48, 64, 128):
        from PySide6.QtGui import QPixmap
        canvas = QPixmap(size, size)
        canvas.fill(QColor(0, 0, 0, 0))          # transparent base

        p = QPainter(canvas)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rounded-square background
        radius = size * 0.22
        rect   = QRectF(0, 0, size, size)
        path   = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.fillPath(path, ACCENT)

        # Bot icon centred — 60 % of tile size
        icon_sz  = max(8, int(size * 0.60))
        offset   = (size - icon_sz) // 2
        bot_px   = get_pixmap("bot", icon_sz, FG)
        p.drawPixmap(offset, offset, bot_px)

        p.end()
        icon.addPixmap(canvas)

    return icon


def main():
    # ── 1. Load environment ──────────────────
    load_env()

    # ── 2. Setup logging ─────────────────────
    setup_logging()

    # ── 3. Create QApplication ───────────────
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon

    app = QApplication(sys.argv)
    app.setApplicationName("Desktop Automation Agent")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("AutoAgent")

    # High-DPI support
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    # Set app-wide font
    from PySide6.QtGui import QFont
    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)

    # ── App icon (title bar + taskbar) ────────
    app_icon = _make_app_icon()
    app.setWindowIcon(app_icon)

    # ── 4. Launch main window ─────────────────
    from ui.main_window import MainWindow
    window = MainWindow()
    window.setWindowIcon(app_icon)
    window.show()

    # ── 5. Event loop ─────────────────────────
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
