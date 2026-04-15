"""
Chat Panel — the main conversation area.

Features:
- Scrollable message history with styled bubbles
- Multi-line input box with Ctrl+Enter to send
- Drag-and-drop file attachment
- File picker button
- Preview plan button
- Stop execution button
- Spinner during processing
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, Signal, QMimeData, QThread
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout,
    QWidget,
)

from icons.icon_manager import IconButton, get_pixmap
from models.schemas import Message, MessageRole
from ui.styles import COLORS
from ui.widgets import ChatBubble, HDivider, LoadingSpinner, SectionLabel, ToastNotification


class VoiceInputThread(QThread):
    result_ready = Signal(str)
    error_occurred = Signal(str)

    SAMPLE_RATE = 16000

    def __init__(self):
        super().__init__()
        self._running = True
        self._stream = None  # ← keep reference for abort

    def stop(self):
        self._running = False
        if self._stream is not None:
            try:
                self._stream.abort()  # ← unblocks stream.read() immediately
            except Exception:
                pass

    def run(self):
        try:
            import sounddevice as sd
            import numpy as np
            import speech_recognition as sr
            import io, wave
        except ImportError as e:
            self.error_occurred.emit(f"Missing dependency: {e}")
            return

        chunk = int(self.SAMPLE_RATE * 0.1)
        frames = []

        try:
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=chunk,
            ) as stream:
                self._stream = stream
                while self._running:
                    data, _ = stream.read(chunk)
                    frames.append(data.copy())
        except Exception as e:
            self.error_occurred.emit(f"Recording error: {e}")
            return
        finally:
            self._stream = None

        if not frames:
            self.error_occurred.emit("No audio recorded")
            return

        try:
            import numpy as np
            audio_data = np.concatenate(frames, axis=0)

            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(audio_data.tobytes())
            wav_buffer.seek(0)

            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_buffer) as source:
                audio = recognizer.record(source)

            text = recognizer.recognize_google(audio)
            self.result_ready.emit(text)

        except sr.UnknownValueError:
            self.error_occurred.emit("Could not understand audio — please speak clearly")
        except sr.RequestError as e:
            self.error_occurred.emit(f"Google Speech API error: {e}")
        except Exception as e:
            self.error_occurred.emit(f"Transcription error: {e}")
class ChatInput(QTextEdit):
    """Multi-line input that sends on Ctrl+Enter and grows up to max height."""

    send_triggered = Signal()
    files_dropped = Signal(list)   # list of file paths

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chat_input")
        self.setAcceptDrops(True)
        self.setPlaceholderText(
            "Type a request… e.g. 'Open the latest sales Excel, summarize Q1, create a Word report and draft an email to manager@company.com'"
        )
        self.setMinimumHeight(52)
        self.setMaximumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.document().contentsChanged.connect(self._adjust_height)

    def keyPressEvent(self, event: QKeyEvent):
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier):
            self.send_triggered.emit()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def _adjust_height(self):
        doc_height = self.document().size().height()
        new_h = max(52, min(160, int(doc_height) + 20))
        self.setFixedHeight(new_h)

class ChatPanel(QWidget):
    """
    Main chat conversation panel.
    Sends user messages upward via signals; receives responses via slots.
    """

    message_submitted    = Signal(str, list)  # text, attachment paths
    stop_requested       = Signal()
    plan_preview_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._attachments: List[str] = []
        self._processing = False
        self._voice_thread: VoiceInputThread | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ───────────────────────────────
        header = QFrame()
        header.setStyleSheet(
            f"background: {COLORS['bg_secondary']}; "
            f"border-bottom: 1px solid {COLORS['border']};"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 10, 16, 10)
        h_layout.setSpacing(10)

        title = QLabel("Desktop Automation Agent")
        title.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 15px; font-weight: 700;"
        )
        h_layout.addWidget(title)
        h_layout.addStretch()

        self._spinner = LoadingSpinner(20, COLORS["accent_blue"])
        h_layout.addWidget(self._spinner)

        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 12px;"
        )
        h_layout.addWidget(self._status_lbl)

        # Stop button with square/stop-circle icon
        self._stop_btn = IconButton(
            icon_name="stop-circle",
            size=14,
            color=COLORS["accent_red"],
            hover_color="#FF6B6B",
            btn_size=None,
            text="  Stop",
            parent=header,
        )
        self._stop_btn.setObjectName("btn_danger")
        self._stop_btn.setFixedSize(72, 28)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {COLORS['accent_red']}; "
            f"font-size: 12px; font-weight: 600; border: 1px solid {COLORS['accent_red']}; "
            f"border-radius: 5px; padding: 0 8px; }}"
            f"QPushButton:hover {{ background: rgba(239,68,68,0.12); }}"
            f"QPushButton:disabled {{ color: {COLORS['text_muted']}; border-color: {COLORS['border']}; }}"
        )
        self._stop_btn.clicked.connect(self.stop_requested)
        h_layout.addWidget(self._stop_btn)

        layout.addWidget(header)

        # ── Messages Area ─────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent; border: none;")

        self._msg_container = QWidget()
        self._msg_container.setStyleSheet(f"background: {COLORS['bg_primary']};")
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(16, 16, 16, 16)
        self._msg_layout.setSpacing(8)
        self._msg_layout.addStretch()

        # Welcome message
        self._add_welcome()

        self._scroll.setWidget(self._msg_container)
        layout.addWidget(self._scroll, 1)

        layout.addWidget(HDivider())

        # ── Input Area ────────────────────────────
        input_area = QWidget()
        input_area.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        i_layout = QVBoxLayout(input_area)
        i_layout.setContentsMargins(12, 10, 12, 12)
        i_layout.setSpacing(8)

        # Attachments row (shown when files added)
        self._attach_row = QWidget()
        self._attach_row.setStyleSheet("background: transparent;")
        self._attach_layout = QHBoxLayout(self._attach_row)
        self._attach_layout.setContentsMargins(0, 0, 0, 0)
        self._attach_layout.setSpacing(6)
        self._attach_row.hide()
        i_layout.addWidget(self._attach_row)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._input = ChatInput()
        self._input.send_triggered.connect(self._send)
        self._input.files_dropped.connect(self._on_files_dropped)
        input_row.addWidget(self._input, 1)

        # Mic button — toggles voice recording
        self._mic_btn = IconButton(
            icon_name="mic",
            size=18,
            color=COLORS["text_secondary"],
            hover_color=COLORS["text_primary"],
            btn_size=40,
            circular=True,
            parent=input_area,
        )
        self._mic_btn.setObjectName("mic_button")
        self._mic_btn.setToolTip("Voice input — click to speak")
        self._mic_btn.setStyleSheet(
            f"QPushButton {{ background: {COLORS['bg_tertiary']}; border: none; "
            f"border-radius: 20px; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; }}"
            f"QPushButton:pressed {{ background: {COLORS['border']}; }}"
            f"QPushButton:disabled {{ background: {COLORS['bg_tertiary']}; opacity: 0.4; }}"
        )
        self._mic_btn.clicked.connect(self._toggle_voice)
        input_row.addWidget(self._mic_btn)

        # Send button — circular, accent blue, send icon
        self._send_btn = IconButton(
            icon_name="send",
            size=18,
            color="#FFFFFF",
            hover_color="#FFFFFF",
            btn_size=40,
            circular=True,
            parent=input_area,
        )
        self._send_btn.setObjectName("send_button")
        self._send_btn.setToolTip("Send (Ctrl+Enter)")
        self._send_btn.setStyleSheet(
            f"QPushButton {{ background: {COLORS['accent_blue']}; border: none; "
            f"border-radius: 20px; }}"
            f"QPushButton:hover {{ background: {COLORS.get('accent_blue_hover', '#388BFD')}; }}"
            f"QPushButton:pressed {{ background: {COLORS.get('accent_blue_active', '#2563EB')}; }}"
            f"QPushButton:disabled {{ background: {COLORS['bg_tertiary']}; }}"
        )
        self._send_btn.clicked.connect(self._send)
        input_row.addWidget(self._send_btn)

        i_layout.addLayout(input_row)

        # Bottom toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        # Attach button
        attach_btn = IconButton(
            icon_name="paperclip",
            size=13,
            color=COLORS["text_secondary"],
            hover_color=COLORS["text_primary"],
            btn_size=None,
            text="  Attach",
            parent=input_area,
        )
        attach_btn.setObjectName("btn_icon")
        attach_btn.setFixedHeight(26)
        attach_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {COLORS['text_secondary']}; "
            f"font-size: 11px; border: none; border-radius: 4px; padding: 2px 8px; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; "
            f"color: {COLORS['text_primary']}; }}"
        )
        attach_btn.clicked.connect(self._pick_files)
        toolbar.addWidget(attach_btn)

        # Preview Plan button
        plan_btn = IconButton(
            icon_name="layers",
            size=13,
            color=COLORS["text_secondary"],
            hover_color=COLORS["text_primary"],
            btn_size=None,
            text="  Preview Plan",
            parent=input_area,
        )
        plan_btn.setObjectName("btn_icon")
        plan_btn.setFixedHeight(26)
        plan_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {COLORS['text_secondary']}; "
            f"font-size: 11px; border: none; border-radius: 4px; padding: 2px 8px; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; "
            f"color: {COLORS['text_primary']}; }}"
        )
        plan_btn.clicked.connect(self.plan_preview_requested)
        toolbar.addWidget(plan_btn)

        toolbar.addStretch()

        hint_lbl = QLabel("Ctrl+Enter to send  ·  Drag & drop files  ·  🎙 Mic to speak")
        hint_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px;"
        )
        toolbar.addWidget(hint_lbl)
        i_layout.addLayout(toolbar)

        layout.addWidget(input_area)

    # ─────────────────────────────────────────
    # Message Display
    # ─────────────────────────────────────────

    def add_message(self, message: Message):
        """Append a message bubble to the chat area."""
        ts = message.timestamp.strftime("%H:%M") if hasattr(message, 'timestamp') else ""
        bubble = ChatBubble(
            content=message.content,
            role=message.role.value,
            timestamp=ts,
        )
        bubble.copy_requested.connect(self._copy_text)
        # Insert before stretch
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, bubble)
        self._scroll_to_bottom()

    def add_user_message(self, text: str):
        from models.schemas import Message as Msg, MessageRole
        msg = Msg(
            id="tmp",
            session_id="tmp",
            role=MessageRole.USER,
            content=text,
        )
        self.add_message(msg)

    def add_assistant_message(self, text: str):
        from models.schemas import Message as Msg, MessageRole
        msg = Msg(
            id="tmp",
            session_id="tmp",
            role=MessageRole.ASSISTANT,
            content=text,
        )
        self.add_message(msg)

    def clear_messages(self):
        """Remove all messages."""
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._add_welcome()

    def load_history(self, messages: List[Message]):
        """Load a previous session's messages."""
        self.clear_messages()
        for msg in messages:
            if msg.role in (MessageRole.USER, MessageRole.ASSISTANT):
                self.add_message(msg)

    # ─────────────────────────────────────────
    # Status
    # ─────────────────────────────────────────

    def set_status(self, text: str):
        self._status_lbl.setText(text)

    def set_processing(self, processing: bool):
        self._processing = processing
        self._send_btn.setEnabled(not processing)
        self._stop_btn.setEnabled(processing)
        # Disable mic while agent is running (allow it when recording is active)
        if processing and not self._is_recording():
            self._mic_btn.setEnabled(False)
        elif not processing:
            self._mic_btn.setEnabled(True)
        if processing:
            self._spinner.start()
        else:
            self._spinner.stop()
            self._status_lbl.setText("Ready")

    # ─────────────────────────────────────────
    # Sending
    # ─────────────────────────────────────────

    def _send(self):
        text = self._input.toPlainText().strip()
        if not text or self._processing:
            return
        self._input.clear()
        attachments = list(self._attachments)
        self._attachments.clear()
        self._refresh_attach_row()
        self.message_submitted.emit(text, attachments)

    def set_input_text(self, text: str):
        """Programmatically set input text (from quick prompts)."""
        self._input.setPlainText(text)
        self._input.setFocus()

    # ─────────────────────────────────────────
    # File Attachment
    # ─────────────────────────────────────────

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Attach Files",
            str(Path.home()),
            "Supported Files (*.xlsx *.xls *.docx *.doc *.csv *.pdf *.txt);;All Files (*)",
        )
        if paths:
            self._on_files_dropped(paths)

    def _on_files_dropped(self, paths: List[str]):
        for path in paths:
            if path not in self._attachments:
                self._attachments.append(path)
        self._refresh_attach_row()

    def _refresh_attach_row(self):
        while self._attach_layout.count():
            item = self._attach_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._attachments:
            self._attach_row.hide()
            return

        self._attach_row.show()
        for path in self._attachments:
            name = Path(path).name
            chip = QFrame()
            chip.setStyleSheet(
                f"background: {COLORS['bg_tertiary']}; border-radius: 12px; "
                f"border: 1px solid {COLORS['border']};"
            )
            c_layout = QHBoxLayout(chip)
            c_layout.setContentsMargins(8, 3, 8, 3)
            c_layout.setSpacing(4)

            # File icon for chip
            file_icon_lbl = QLabel()
            file_icon_lbl.setPixmap(get_pixmap("paperclip", size=11, color=COLORS["text_muted"]))
            file_icon_lbl.setStyleSheet("background: transparent;")
            c_layout.addWidget(file_icon_lbl)

            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(
                f"color: {COLORS['text_secondary']}; font-size: 11px;"
            )
            c_layout.addWidget(name_lbl)

            rm_btn = QPushButton("×")
            rm_btn.setFixedSize(14, 14)
            rm_btn.setStyleSheet(
                f"color: {COLORS['text_muted']}; background: transparent; "
                f"border: none; font-size: 12px;"
            )
            rm_btn.clicked.connect(lambda _, p=path: self._remove_attachment(p))
            c_layout.addWidget(rm_btn)
            self._attach_layout.addWidget(chip)
        self._attach_layout.addStretch()

    def _remove_attachment(self, path: str):
        self._attachments = [p for p in self._attachments if p != path]
        self._refresh_attach_row()

    # ─────────────────────────────────────────
    # Voice Input
    # ─────────────────────────────────────────

    # ── Voice methods — all at class level, properly indented ──

    def _is_recording(self) -> bool:
        return self._voice_thread is not None and self._voice_thread.isRunning()

    def _toggle_voice(self):
        if self._is_recording():
            self._stop_voice()
        else:
            self._start_voice()

    def _start_voice(self):
        self._voice_thread = VoiceInputThread()
        self._voice_thread.result_ready.connect(self._on_voice_result)
        self._voice_thread.error_occurred.connect(self._on_voice_error)
        self._voice_thread.finished.connect(self._on_voice_finished)
        self._voice_thread.start()

        # Visual feedback: turn mic button red while recording
        self._mic_btn.setStyleSheet(
            f"QPushButton {{ background: {COLORS['accent_red']}; border: none; "
            f"border-radius: 20px; }}"
            f"QPushButton:hover {{ background: #FF6B6B; }}"
        )
        self._mic_btn.setToolTip("Recording… click to stop")
        self._status_lbl.setText("🎙 Recording…")

    def _stop_voice(self):
        """Signal the thread to stop — do NOT call wait() here (blocks UI)."""
        if self._voice_thread:
            self._voice_thread.stop()
            # Don't wait() — let finished signal handle cleanup
        self._status_lbl.setText("⏳ Transcribing…")
        self._reset_mic_ui()

    def _cancel_voice(self):
        """Discard recording entirely."""
        if self._voice_thread:
            self._voice_thread.result_ready.disconnect(self._on_voice_result)
            self._voice_thread.stop()
            self._voice_thread = None
        self._reset_mic_ui()
        self._status_lbl.setText("Voice input cancelled")

    def _on_voice_result(self, text: str):
        self._input.setPlainText(text)
        cursor = self._input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        self._input.setFocus()
        self._status_lbl.setText("✅ Voice transcribed — press Ctrl+Enter to send")

    def _on_voice_error(self, message: str):
        ToastNotification.show_toast(self, message, "error")
        self._status_lbl.setText("❌ Voice failed")

    def _on_voice_finished(self):
        self._voice_thread = None   # ← clean up here, not in _stop_voice
        self._reset_mic_ui()
        if self._status_lbl.text() == "⏳ Transcribing…":
            self._status_lbl.setText("Ready")

    def _reset_mic_ui(self):
        self._mic_btn.setToolTip("Voice input — click to speak")
        self._mic_btn.setStyleSheet(
            f"QPushButton {{ background: {COLORS['bg_tertiary']}; border: none; "
            f"border-radius: 20px; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; }}"
            f"QPushButton:pressed {{ background: {COLORS['border']}; }}"
            f"QPushButton:disabled {{ background: {COLORS['bg_tertiary']}; opacity: 0.4; }}"
        )

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    def _add_welcome(self):
        welcome_widget = QWidget()
        welcome_widget.setStyleSheet("background: transparent;")
        wv = QVBoxLayout(welcome_widget)
        wv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wv.setContentsMargins(32, 32, 32, 32)
        wv.setSpacing(12)

        # Bot icon centered
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("bot", size=40, color=COLORS["accent_blue"]))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent;")
        wv.addWidget(icon_lbl)

        welcome_lbl = QLabel(
            "Welcome to Desktop Automation Agent\n\n"
            "Type a request below or choose a Quick Prompt from the sidebar.\n\n"
            "Examples:\n"
            "• Summarize the latest sales Excel and create a Word report\n"
            "• Find overdue invoices and email a summary to the team\n"
            "• Rewrite the introduction of report.docx professionally"
        )
        welcome_lbl.setWordWrap(True)
        welcome_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 13px; "
            f"padding: 0; line-height: 1.7;"
        )
        wv.addWidget(welcome_lbl)

        self._msg_layout.insertWidget(0, welcome_widget)

    def _scroll_to_bottom(self):
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _copy_text(self, text: str):
        QApplication.clipboard().setText(text)
        ToastNotification.show_toast(self, "Copied to clipboard", "success")