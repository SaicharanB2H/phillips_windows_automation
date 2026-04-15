"""
Dark theme stylesheet for the Desktop Automation Agent.
Professional futuristic console aesthetic with strong readability.
"""

# ─────────────────────────────────────────────
# Color Palette
# ─────────────────────────────────────────────
COLORS = {
    "bg_primary":     "#0D1117",   # Deep dark background
    "bg_secondary":   "#161B22",   # Card/panel background
    "bg_tertiary":    "#1C2128",   # Input, sidebar items
    "bg_hover":       "#21262D",   # Hover state
    "bg_selected":    "#1F4068",   # Selected item
    "border":         "#30363D",   # Subtle borders
    "border_accent":  "#388BFD",   # Active/focus borders
    "text_primary":   "#E6EDF3",   # Main text
    "text_secondary": "#8B949E",   # Dimmed/secondary text
    "text_muted":     "#484F58",   # Very dim text
    "accent_blue":    "#388BFD",   # Primary accent
    "accent_green":   "#3FB950",   # Success
    "accent_orange":  "#D29922",   # Warning
    "accent_red":     "#F85149",   # Error/danger
    "accent_purple":  "#BC8CFF",   # Planner
    "accent_teal":    "#39C5CF",   # Excel
    "accent_yellow":  "#F0E68C",   # Word
    "accent_pink":    "#FF79C6",   # Email
    "bubble_user":    "#1F4068",   # User chat bubble
    "bubble_bot":     "#1C2128",   # Assistant chat bubble
    "scrollbar":      "#30363D",
    "scrollbar_hover":"#484F58",
}

MAIN_STYLESHEET = f"""
/* ═══════════════════════════════════════════
   Global Reset & Base
══════════════════════════════════════════ */
QWidget {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_primary']};
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
    border: none;
    outline: none;
}}

QMainWindow {{
    background-color: {COLORS['bg_primary']};
}}

/* ═══════════════════════════════════════════
   Splitter
══════════════════════════════════════════ */
QSplitter::handle {{
    background-color: {COLORS['border']};
    width: 1px;
    height: 1px;
}}
QSplitter::handle:hover {{
    background-color: {COLORS['accent_blue']};
}}

/* ═══════════════════════════════════════════
   Scroll Areas
══════════════════════════════════════════ */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: {COLORS['bg_secondary']};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['scrollbar']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS['scrollbar_hover']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {COLORS['bg_secondary']};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {COLORS['scrollbar']};
    border-radius: 4px;
}}

/* ═══════════════════════════════════════════
   Labels
══════════════════════════════════════════ */
QLabel {{
    color: {COLORS['text_primary']};
    background: transparent;
}}
QLabel#heading {{
    font-size: 15px;
    font-weight: 700;
    color: {COLORS['text_primary']};
}}
QLabel#subheading {{
    font-size: 12px;
    color: {COLORS['text_secondary']};
}}
QLabel#badge_planner  {{ color: {COLORS['accent_purple']}; font-weight: 600; }}
QLabel#badge_excel    {{ color: {COLORS['accent_teal']};   font-weight: 600; }}
QLabel#badge_word     {{ color: {COLORS['accent_yellow']};  font-weight: 600; }}
QLabel#badge_email    {{ color: {COLORS['accent_pink']};   font-weight: 600; }}
QLabel#badge_file     {{ color: {COLORS['accent_blue']};   font-weight: 600; }}

/* ═══════════════════════════════════════════
   Buttons
══════════════════════════════════════════ */
QPushButton {{
    background-color: {COLORS['bg_tertiary']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 7px 16px;
    font-size: 13px;
    font-weight: 500;
    min-height: 28px;
}}
QPushButton:hover {{
    background-color: {COLORS['bg_hover']};
    border-color: {COLORS['border_accent']};
    color: {COLORS['text_primary']};
}}
QPushButton:pressed {{
    background-color: {COLORS['bg_selected']};
}}
QPushButton:disabled {{
    color: {COLORS['text_muted']};
    border-color: {COLORS['text_muted']};
}}

QPushButton#btn_primary {{
    background-color: {COLORS['accent_blue']};
    border-color: {COLORS['accent_blue']};
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton#btn_primary:hover {{
    background-color: #4D9FFF;
    border-color: #4D9FFF;
}}
QPushButton#btn_danger {{
    background-color: transparent;
    border-color: {COLORS['accent_red']};
    color: {COLORS['accent_red']};
}}
QPushButton#btn_danger:hover {{
    background-color: {COLORS['accent_red']};
    color: #FFFFFF;
}}
QPushButton#btn_success {{
    background-color: {COLORS['accent_green']};
    border-color: {COLORS['accent_green']};
    color: #000000;
    font-weight: 600;
}}
QPushButton#btn_icon {{
    background: transparent;
    border: none;
    padding: 4px;
    border-radius: 4px;
    font-size: 16px;
}}
QPushButton#btn_icon:hover {{
    background-color: {COLORS['bg_hover']};
}}
QPushButton#send_button {{
    background-color: {COLORS['accent_blue']};
    border: none;
    border-radius: 8px;
    color: white;
    font-size: 18px;
    min-width: 44px;
    max-width: 44px;
    min-height: 44px;
    max-height: 44px;
    font-weight: bold;
}}
QPushButton#send_button:hover {{
    background-color: #4D9FFF;
}}
QPushButton#send_button:disabled {{
    background-color: {COLORS['bg_tertiary']};
    color: {COLORS['text_muted']};
}}

/* ═══════════════════════════════════════════
   Text Input (Chat Box)
══════════════════════════════════════════ */
QTextEdit#chat_input {{
    background-color: {COLORS['bg_tertiary']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 14px;
    line-height: 1.5;
    selection-background-color: {COLORS['accent_blue']};
}}
QTextEdit#chat_input:focus {{
    border-color: {COLORS['border_accent']};
}}
QTextEdit {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 8px;
    selection-background-color: {COLORS['accent_blue']};
}}

QLineEdit {{
    background-color: {COLORS['bg_tertiary']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 7px 12px;
    font-size: 13px;
    selection-background-color: {COLORS['accent_blue']};
}}
QLineEdit:focus {{
    border-color: {COLORS['border_accent']};
}}

/* ═══════════════════════════════════════════
   ComboBox (mode selector)
══════════════════════════════════════════ */
QComboBox {{
    background-color: {COLORS['bg_tertiary']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    min-width: 120px;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {COLORS['text_secondary']};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    selection-background-color: {COLORS['bg_selected']};
    outline: none;
}}
QComboBox:hover {{
    border-color: {COLORS['border_accent']};
}}

/* ═══════════════════════════════════════════
   List & Tree Widgets
══════════════════════════════════════════ */
QListWidget, QTreeWidget {{
    background-color: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 12px;
    border-radius: 6px;
    margin: 1px 4px;
    color: {COLORS['text_primary']};
}}
QListWidget::item:hover {{
    background-color: {COLORS['bg_hover']};
}}
QListWidget::item:selected {{
    background-color: {COLORS['bg_selected']};
    color: {COLORS['text_primary']};
}}
QTreeWidget::item {{
    padding: 4px 8px;
    color: {COLORS['text_primary']};
}}
QTreeWidget::item:hover {{
    background-color: {COLORS['bg_hover']};
}}
QTreeWidget::item:selected {{
    background-color: {COLORS['bg_selected']};
    color: {COLORS['text_primary']};
}}
QHeaderView::section {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_secondary']};
    border: none;
    border-bottom: 1px solid {COLORS['border']};
    padding: 6px 8px;
    font-weight: 600;
    font-size: 12px;
}}

/* ═══════════════════════════════════════════
   Tab Widget
══════════════════════════════════════════ */
QTabWidget::pane {{
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    background: {COLORS['bg_secondary']};
    top: -1px;
}}
QTabBar::tab {{
    background: {COLORS['bg_tertiary']};
    color: {COLORS['text_secondary']};
    border: 1px solid {COLORS['border']};
    border-bottom: none;
    padding: 8px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    font-size: 12px;
    font-weight: 500;
}}
QTabBar::tab:selected {{
    background: {COLORS['bg_secondary']};
    color: {COLORS['accent_blue']};
    border-bottom: 2px solid {COLORS['accent_blue']};
}}
QTabBar::tab:hover:!selected {{
    background: {COLORS['bg_hover']};
    color: {COLORS['text_primary']};
}}

/* ═══════════════════════════════════════════
   Progress Bar
══════════════════════════════════════════ */
QProgressBar {{
    background-color: {COLORS['bg_tertiary']};
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {COLORS['accent_blue']};
    border-radius: 4px;
}}

/* ═══════════════════════════════════════════
   Tooltips
══════════════════════════════════════════ */
QToolTip {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ═══════════════════════════════════════════
   Menu
══════════════════════════════════════════ */
QMenu {{
    background-color: {COLORS['bg_secondary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 24px;
    color: {COLORS['text_primary']};
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {COLORS['bg_selected']};
}}
QMenu::separator {{
    height: 1px;
    background: {COLORS['border']};
    margin: 4px 8px;
}}

/* ═══════════════════════════════════════════
   Status Bar
══════════════════════════════════════════ */
QStatusBar {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_secondary']};
    border-top: 1px solid {COLORS['border']};
    font-size: 12px;
    padding: 2px 8px;
}}
QStatusBar::item {{
    border: none;
}}

/* ═══════════════════════════════════════════
   Frames / Panels
══════════════════════════════════════════ */
QFrame#panel {{
    background-color: {COLORS['bg_secondary']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
}}
QFrame#panel_flat {{
    background-color: {COLORS['bg_secondary']};
    border: none;
}}
QFrame#sidebar {{
    background-color: {COLORS['bg_secondary']};
    border-right: 1px solid {COLORS['border']};
}}
QFrame#step_card {{
    background-color: {COLORS['bg_tertiary']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 4px;
}}
QFrame#step_card_running {{
    background-color: {COLORS['bg_tertiary']};
    border: 1px solid {COLORS['accent_blue']};
    border-radius: 8px;
}}
QFrame#step_card_success {{
    background-color: {COLORS['bg_tertiary']};
    border: 1px solid {COLORS['accent_green']};
    border-radius: 8px;
}}
QFrame#step_card_failed {{
    background-color: {COLORS['bg_tertiary']};
    border: 1px solid {COLORS['accent_red']};
    border-radius: 8px;
}}
QFrame#artifact_card {{
    background-color: {COLORS['bg_tertiary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 6px;
}}
QFrame#artifact_card:hover {{
    border-color: {COLORS['accent_blue']};
}}

/* ═══════════════════════════════════════════
   Chat Bubbles
══════════════════════════════════════════ */
QFrame#bubble_user {{
    background-color: {COLORS['bubble_user']};
    border-radius: 12px;
    border-bottom-right-radius: 2px;
}}
QFrame#bubble_bot {{
    background-color: {COLORS['bubble_bot']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
    border-bottom-left-radius: 2px;
}}
QFrame#bubble_tool {{
    background-color: {COLORS['bg_primary']};
    border: 1px solid {COLORS['border']};
    border-left: 3px solid {COLORS['accent_blue']};
    border-radius: 4px;
}}

/* ═══════════════════════════════════════════
   Checkboxes
══════════════════════════════════════════ */
QCheckBox {{
    color: {COLORS['text_primary']};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {COLORS['border']};
    border-radius: 3px;
    background: {COLORS['bg_tertiary']};
}}
QCheckBox::indicator:checked {{
    background: {COLORS['accent_blue']};
    border-color: {COLORS['accent_blue']};
}}

/* ═══════════════════════════════════════════
   Sidebar Session Items
══════════════════════════════════════════ */
QFrame#session_item {{
    background: transparent;
    border-radius: 6px;
    padding: 6px;
}}
QFrame#session_item:hover {{
    background: {COLORS['bg_hover']};
}}
QFrame#session_item_active {{
    background: {COLORS['bg_selected']};
    border-radius: 6px;
    padding: 6px;
}}
"""


def get_status_color(status: str) -> str:
    """Return a hex color for a given step status string."""
    return {
        "pending":          COLORS["text_muted"],
        "running":          COLORS["accent_blue"],
        "success":          COLORS["accent_green"],
        "failed":           COLORS["accent_red"],
        "skipped":          COLORS["text_secondary"],
        "waiting_approval": COLORS["accent_orange"],
        "cancelled":        COLORS["text_secondary"],
    }.get(status, COLORS["text_secondary"])


def get_agent_color(agent: str) -> str:
    """Return accent color for a given agent type."""
    return {
        "planner":       COLORS["accent_purple"],
        "excel":         COLORS["accent_teal"],
        "word":          COLORS["accent_yellow"],
        "email":         COLORS["accent_pink"],
        "file":          COLORS["accent_blue"],
        "ui_automation": COLORS["accent_orange"],
        "orchestrator":  COLORS["text_secondary"],
    }.get(agent.lower(), COLORS["text_secondary"])


def get_agent_icon(agent: str) -> str:
    """Return icon name (for IconManager) per agent — fallback to emoji string."""
    return {
        "planner":       "zap",
        "excel":         "file-spreadsheet",
        "word":          "file-text",
        "email":         "mail",
        "file":          "folder",
        "ui_automation": "cpu",
        "orchestrator":  "layers",
    }.get(agent.lower(), "bot")


def get_status_icon(status: str) -> str:
    """Return Lucide icon name for a step status."""
    return {
        "pending":          "clock",
        "running":          "loader",
        "success":          "check-circle",
        "failed":           "x-circle",
        "skipped":          "skip-forward",
        "waiting_approval": "pause",
        "cancelled":        "x-circle",
    }.get(status, "clock")
