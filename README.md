# Desktop Automation Agent

A production-grade AI-powered Windows desktop automation system with a polished PySide6 frontend. Type natural language — the agent plans and executes multi-step workflows automatically.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![PySide6](https://img.shields.io/badge/UI-PySide6-green) ![Groq](https://img.shields.io/badge/LLM-Groq%20API-orange) ![Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey)

---

## What It Does

You type a request in plain English. The system:
1. Uses an LLM to generate a structured execution plan
2. Routes each step to a specialized agent
3. Executes everything automatically — finding files, opening Excel, writing Word reports, sending emails
4. Asks your approval before any risky action (email send, file delete)
5. Remembers your name, email, and preferences across sessions

**Example:**
> *"Open the sales Excel from Downloads, summarize totals by category, create a Word report, and email it to my manager."*

The agent finds the file, opens it, groups the data, generates a formatted report, drafts the email with the file attached — all in under 30 seconds.

---

## Features

- **Autonomous LLM planning** — natural language → structured JSON execution plan via Groq API
- **7 specialized agents** — Excel, Word, Email, File, Memory, App Launcher, UI Automation
- **Smart file discovery** — finds files by vague description across Desktop, Downloads, Documents
- **PDF extraction** — 4-library auto-fallback chain (pdfplumber → pypdf → PyPDF2 → pdfminer)
- **Persistent memory** — SQLite-backed cross-session memory; agent remembers your preferences
- **App launcher** — open any Windows application by name ("open Chrome", "launch VS Code")
- **Gmail SMTP** — works without Outlook; full email with attachments via SMTP
- **Safety checkpoints** — approval dialogs before email sends, file deletion, bulk edits
- **Re-planning on failure** — LLM generates a revised plan when a step fails
- **Modern PySide6 UI** — Lucide SVG icons, chat bubbles, live execution panel, artifact list

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/your-username/phillips.git
cd phillips
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Groq API — get your key at console.groq.com
GROK_API_KEY=gsk_your_key_here
GROK_BASE_URL=https://api.groq.com/openai/v1
GROK_MODEL=openai/gpt-oss-120b

# Gmail SMTP (used when Outlook is not installed)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your_app_password   # Google App Password — NOT your Gmail login
```

### 3. Run

```bash
python main.py
```

---

## Gmail App Password Setup

Gmail requires an **App Password** (not your regular password) for SMTP. Regular passwords will be rejected.

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** (required)
3. Go to **App Passwords** → Select app: *Mail* → Select device: *Windows Computer*
4. Copy the 16-character password → paste into `SMTP_PASSWORD` in `.env`

---

## Demo Without API Key

```env
MOCK_LLM=true
DEMO_MODE=true
```

Runs a pre-built mock plan (Excel → Word → Email draft) without calling any API or opening Office apps.

---

## Example Requests

```
Find the sales Excel in Downloads, summarize totals by category, create a Word report and save to Desktop.
```

```
Open the PDF I attached and summarize the key points. Draft an email to my manager with the summary.
```

```
Open invoices.xlsx from Desktop. Calculate total pending payments.
Create a Word document with a summary table. Email it to finance@company.com.
```

```
Open the latest Excel from Downloads, tell me what sheets it has and the column headers.
```

```
Remember that my manager's email is john@company.com
```

```
Open Chrome and VS Code
```

```
What do you remember about me?
```

---

## Agents

### Planner Agent
The LLM brain. Interprets user requests and produces structured JSON execution plans. Uses Groq API (model: `openai/gpt-oss-120b`). Re-plans automatically when a step fails.

### File Agent
- Smart multi-location file search by vague description (`files.smart_find`)
- PDF text extraction with 4-library auto-fallback chain
- Search by name, type, date across Desktop / Downloads / Documents / Home
- Read/write text and CSV files
- File metadata, copy, verify existence

### Excel Agent
- Open workbooks via COM (full Excel) or openpyxl (fallback)
- Read sheets, ranges, and used ranges
- Compute column statistics — sum, mean, min, max (auto-detects numeric columns)
- Group-by aggregation with smart fuzzy column matching
- Apply filters, formatting, charts
- Export to CSV or save as XLSX

### Word Agent
- Create documents from scratch or templates
- Insert headings, paragraphs, tables, images, page breaks
- Set headers, footers, themes
- Rewrite sections using LLM
- Save as DOCX

### Email Agent
- Uses Outlook COM when installed; automatically falls back to Gmail SMTP
- LLM-generated email bodies
- File attachments (Word, Excel, PDF)
- Requires explicit approval before sending

### Memory Agent
- Persistent cross-session SQLite storage
- Categories: user, contacts, paths, preferences, facts
- Auto-extracts facts from messages ("my name is...", "my email is...")
- Injected into every LLM call — agent never asks for info it already knows
- Tools: `memory.save`, `memory.recall`, `memory.list`, `memory.forget`

### App Launcher Agent
- Opens any Windows application by natural language name
- Covers 100+ apps with aliases ("browser" → Chrome, "terminal" → Windows Terminal)
- Resolution order: built-in registry → PATH → Start Menu shortcuts → Program Files → Registry App Paths
- Tools: `app.open`, `app.close`, `app.is_running`, `app.list`

### UI Automation Agent (fallback)
- pyautogui for mouse/keyboard/screenshot
- pywinauto for window detection and focus
- Used when no COM or native API is available

---

## Architecture

```
User Request (text + optional file attachments)
        │
        ▼
  Orchestrator  ──── ContextManager (template variables, step results)
        │
        ├── PlannerAgent ──── Groq API ──→ ExecutionPlan (JSON steps)
        │         └── MemoryStore ──→ injects remembered facts into LLM prompt
        │
        ├── For each PlanStep (mutable queue — supports live re-planning):
        │    ├── Resolve template vars  {{step_N.result.path}}, {{excel_group_by.table_data}}, …
        │    ├── Approval check         (ApprovalService — blocks on high-risk actions)
        │    ├── Route to agent         ExcelAgent / WordAgent / EmailAgent / FileAgent / …
        │    ├── Execute tool call
        │    ├── Store result in context (step number + tool-name keys)
        │    ├── Detect artifacts       (files produced by the step)
        │    └── On failure → re-plan   (LLM generates revised remaining steps)
        │
        └── Build summary message → emit to UI
```

### Context Template Variables

| Variable | Resolved to |
|---|---|
| `{{attached_file}}` | Path of the first file the user attached |
| `{{attached_file_0}}` … `{{attached_file_N}}` | Indexed attached file paths |
| `{{step_N.result.path}}` | File path returned by step N |
| `{{step_N.result.sheets}}` | Sheet name(s) from `excel.list_sheets` |
| `{{files_smart_find.path}}` | Path found by `files.smart_find` |
| `{{excel_group_by.table_data}}` | Table rows from `excel.group_by` |
| `{{excel_group_by.table_headers}}` | Headers from `excel.group_by` |
| `{{excel_compute_summary.summary}}` | Stats from `excel.compute_summary` |
| `{{memory_recall.value}}` | Value from `memory.recall` |
| `{{output_dir}}` | Desktop path |
| `{{current_date}}` | Today's date (`YYYY-MM-DD`) |
| `{{current_datetime}}` | Timestamp (`YYYY-MM-DD_HHMMSS`) |

---

## Project Structure

```
phillips/
├── main.py                        # Entry point — creates QApplication, MainWindow
├── requirements.txt
├── .env                           # Your config (gitignored)
│
├── app/
│   ├── orchestrator.py            # Central execution engine + QThread worker
│   └── context_manager.py        # Template variable resolution across steps
│
├── agents/
│   ├── base_agent.py              # Abstract base with tool registration & execution
│   ├── planner_agent.py           # LLM-powered planner (Groq API)
│   ├── excel_agent.py             # Excel COM + openpyxl + pandas analytics
│   ├── word_agent.py              # Word COM + python-docx
│   ├── email_agent.py             # Outlook COM + Gmail SMTP fallback
│   ├── file_agent.py              # Smart file discovery + PDF extraction
│   ├── memory_agent.py            # Persistent memory tools
│   ├── app_launcher_agent.py      # Windows app launcher
│   └── ui_automation_agent.py     # pyautogui / pywinauto fallback
│
├── services/
│   ├── llm_service.py             # Groq API client (OpenAI-compatible)
│   └── approval_service.py        # Safety checkpoint management
│
├── models/
│   └── schemas.py                 # All Pydantic v2 data models
│
├── storage/
│   ├── database.py                # SQLite — sessions, plans, messages, artifacts
│   ├── memory_store.py            # Persistent cross-session memory (SQLite)
│   └── __init__.py
│
├── prompts/
│   ├── planner_prompts.py         # LLM system prompts + tool documentation
│   └── agent_prompts.py           # Agent-specific generation prompts
│
├── ui/
│   ├── styles.py                  # QSS dark theme stylesheet
│   ├── widgets.py                 # Chat bubbles, step cards, agent badges
│   ├── main_window.py             # Main application window
│   ├── chat_panel.py              # Chat input + message display
│   ├── sidebar.py                 # Sessions, mode selector, memory status
│   ├── execution_panel.py         # Tabbed plan/log/artifact monitor
│   ├── plan_viewer.py             # Expandable step tree
│   ├── artifact_panel.py          # Generated files list + open/copy buttons
│   ├── log_panel.py               # Real-time log with pause/clear/copy
│   └── approval_dialog.py         # Approval confirmation dialogs
│
├── icons/
│   └── icon_manager.py            # Lucide SVG icon renderer (QSvgRenderer + lru_cache)
│
└── utils/
    ├── logger.py                  # Centralized logging + UI bridge signal
    └── helpers.py                 # File utils, smart_find, JSON helpers, path resolution
```

---

## Execution Modes

| Mode | Behavior |
|---|---|
| **Safe** | Confirms all medium and high-risk actions |
| **Semi-Auto** | Confirms only email sends and file deletion |
| **Demo** | Auto-approves everything except email sends |
| **Dry-Run** | Simulates all actions — nothing actually executed |

Select the mode in the left sidebar. Default is **Safe**.

---

## Safety

- Email sends always require approval (configurable)
- File deletion and overwrites require approval in Safe mode
- Bulk edits flagged as medium risk
- Dry-Run mode simulates everything with zero side effects
- COM errors trigger openpyxl / python-docx / SMTP fallback automatically
- Re-planning on step failure — LLM generates a revised plan for remaining steps

---

## Requirements

- **Python 3.10+**
- **Windows 10/11**
- **Microsoft Office** — optional (openpyxl, python-docx, and SMTP fallbacks cover all cases)
- **Groq API key** — optional (mock mode available for testing)

### Key Python packages

```
PySide6          # UI framework
openai           # Groq API client (OpenAI-compatible)
pandas           # Excel data processing
openpyxl         # Excel file read/write fallback
python-docx      # Word document generation fallback
pdfplumber       # PDF text extraction (primary)
pypdf            # PDF fallback 1
PyPDF2           # PDF fallback 2
pdfminer.six     # PDF fallback 3
pywin32          # Windows COM automation
pyautogui        # Mouse/keyboard automation
pywinauto        # Window management
tenacity         # Retry logic for API calls
pydantic         # Data validation (v2)
python-dotenv    # .env configuration
```

---

## Extending the System

To add a new agent (e.g. a PowerPoint agent):

1. Create `agents/powerpoint_agent.py` extending `BaseAgent`
2. Implement `_register_tools()` with `self.register_tool(...)` calls
3. Add `POWERPOINT = "powerpoint"` to `AgentType` in `models/schemas.py`
4. Add the agent to `_parse_agent()` in `agents/planner_agent.py`
5. Instantiate and map it in `app/orchestrator.py` `_agent_map`
6. Document the tools in `prompts/planner_prompts.py`
