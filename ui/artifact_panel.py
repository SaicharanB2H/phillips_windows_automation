"""
Artifact Panel — displays generated files with open/explore buttons.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from models.schemas import Artifact
from ui.styles import COLORS
from ui.widgets import ArtifactCard, HDivider, SectionLabel
from utils.helpers import human_size, open_file, open_file_in_explorer


class ArtifactPanel(QWidget):
    """Scrollable list of all generated artifacts for the current session."""

    artifact_opened = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._artifacts: list[Artifact] = []
        self._cards: dict[str, ArtifactCard] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ───────────────────────────────
        header = QWidget()
        header.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        h_layout.addWidget(SectionLabel("Generated Files"))
        h_layout.addStretch()

        self._count_lbl = QLabel("0 files")
        self._count_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px;"
        )
        h_layout.addWidget(self._count_lbl)

        open_all_btn = QPushButton("Open Folder")
        open_all_btn.setObjectName("btn_icon")
        open_all_btn.setFixedHeight(24)
        open_all_btn.setStyleSheet(
            f"color: {COLORS['accent_blue']}; font-size: 11px; "
            f"background: transparent; border: 1px solid {COLORS['accent_blue']}; "
            f"border-radius: 4px; padding: 2px 8px;"
        )
        open_all_btn.clicked.connect(self._open_output_folder)
        h_layout.addWidget(open_all_btn)

        layout.addWidget(header)
        layout.addWidget(HDivider())

        # ── Scroll Area ───────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._items_layout = QVBoxLayout(self._container)
        self._items_layout.setContentsMargins(8, 8, 8, 8)
        self._items_layout.setSpacing(6)
        self._items_layout.addStretch()

        scroll.setWidget(self._container)
        layout.addWidget(scroll)

        # ── Empty state ───────────────────────────
        self._empty_lbl = QLabel("No files generated yet.\nFiles created by agents will appear here.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; padding: 24px;"
        )
        self._items_layout.insertWidget(0, self._empty_lbl)

    def add_artifact(self, artifact: Artifact):
        """Add a new artifact card to the panel."""
        if artifact.id in self._cards:
            return  # Deduplicate

        self._artifacts.append(artifact)
        self._empty_lbl.hide()

        size_str = human_size(artifact.size_bytes) if artifact.size_bytes else ""
        card = ArtifactCard(
            name=artifact.name,
            path=artifact.path,
            artifact_type=artifact.artifact_type.value,
            size_str=size_str,
            description=artifact.description or "",
        )
        card.open_file_requested.connect(self._open_file)
        card.open_folder_requested.connect(self._open_folder)
        self._cards[artifact.id] = card

        # Insert before the stretch
        self._items_layout.insertWidget(self._items_layout.count() - 1, card)

        # Update count
        self._count_lbl.setText(f"{len(self._artifacts)} file{'s' if len(self._artifacts) != 1 else ''}")

    def clear_artifacts(self):
        """Remove all artifact cards."""
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()
        self._artifacts.clear()
        self._count_lbl.setText("0 files")
        self._empty_lbl.show()

    def _open_file(self, path: str):
        try:
            open_file(path)
            self.artifact_opened.emit(path)
        except Exception as e:
            from ui.widgets import ToastNotification
            ToastNotification.show_toast(self, f"Could not open: {e}", "error")

    def _open_folder(self, path: str):
        try:
            open_file_in_explorer(path)
        except Exception as e:
            from ui.widgets import ToastNotification
            ToastNotification.show_toast(self, f"Could not open folder: {e}", "error")

    def _open_output_folder(self):
        from utils.helpers import get_desktop_path
        import os
        output = Path(os.getenv("OUTPUT_DIR", str(get_desktop_path() / "AutoAgent_Output")))
        if output.exists():
            open_file_in_explorer(output)
        else:
            open_file_in_explorer(get_desktop_path())
