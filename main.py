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

    # ── 4. Launch main window ─────────────────
    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    # ── 5. Event loop ─────────────────────────
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
