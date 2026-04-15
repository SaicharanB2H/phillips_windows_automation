# Desktop Automation Agent

A production-grade AI-powered Windows desktop automation system with a polished PySide6 frontend.

## Features

- **Grok-powered planning** — natural language → structured execution plan
- **Multi-agent architecture** — Excel, Word, Email, File, UI Automation agents
- **Modern PySide6 UI** — dark theme, chat bubbles, live execution cards
- **Safety system** — approval checkpoints for risky actions
- **Demo/Dry-Run mode** — test without Office or an API key

## Project Structure

```
phillips/
├── main.py                    # Entry point
├── requirements.txt
├── .env.example               # Configuration template
├── app/
│   ├── orchestrator.py        # Central execution engine
│   └── context_manager.py     # Shared memory across agents
├── agents/
│   ├── base_agent.py          # Abstract base with tool registration
│   ├── planner_agent.py       # Grok-powered planner
│   ├── excel_agent.py         # Excel COM + openpyxl
│   ├── word_agent.py          # Word COM + python-docx
│   ├── email_agent.py         # Outlook COM + SMTP
│   ├── file_agent.py          # File discovery & management
│   └── ui_automation_agent.py # pyautogui/pywinauto fallback
├── services/
│   ├── llm_service.py         # Grok API client (OpenAI-compatible)
│   └── approval_service.py    # Safety checkpoint management
├── models/
│   └── schemas.py             # All Pydantic data models
├── storage/
│   └── database.py            # SQLite persistence
├── prompts/
│   ├── planner_prompts.py     # LLM system prompts
│   └── agent_prompts.py       # Agent-specific prompts
├── ui/
│   ├── styles.py              # Dark theme QSS stylesheet
│   ├── widgets.py             # Chat bubbles, step cards, artifacts
│   ├── main_window.py         # Main application window
│   ├── chat_panel.py          # Chat interface + input
│   ├── sidebar.py             # Sessions, mode selector, quick prompts
│   ├── execution_panel.py     # Tabbed execution monitor
│   ├── plan_viewer.py         # Expandable step tree
│   ├── artifact_panel.py      # Generated files list
│   ├── log_panel.py           # Real-time log display
│   └── approval_dialog.py     # Approval confirmation dialogs
└── utils/
    ├── logger.py              # Centralized logging + UI bridge
    └── helpers.py             # File utils, path resolution, JSON helpers
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and add your Grok API key:

```env
GROK_API_KEY=xai-your-key-here
GROK_MODEL=grok-2-1212
```

Get your key at: [console.x.ai](https://console.x.ai)

### 3. Run

```bash
python main.py
```

## Execution Modes

| Mode | Behavior |
|------|----------|
| **Safe** | Confirms all medium/high-risk actions |
| **Semi-Auto** | Confirms only email sending and file deletion |
| **Demo** | Auto-approves everything except email sending |
| **Dry-Run** | Simulates all actions — nothing actually executed |

Select mode in the sidebar. Default is **Safe**.

## Demo Without API Key

Set in `.env`:
```env
MOCK_LLM=true
DEMO_MODE=true
```

This runs a mock plan (Excel → Word → Email draft) without calling Grok or opening Office.

## Example Requests

```
Find the latest Excel sales file in Downloads, summarize Q1 revenue by region,
and create a Word report. Save to Desktop.
```

```
Read invoices.xlsx from Desktop. Calculate total pending payments.
Create a Word document with a summary table. Draft an email to finance@company.com
with the document attached.
```

```
Open report.docx, rewrite the introduction in a professional executive tone,
and save as report_revised.docx.
```

```
Find the most recently modified Excel file in Downloads. Tell me what sheets it has
and the column headers in each sheet.
```

## Agent Capabilities

### Excel Agent (`excel_agent.py`)
- Open workbooks via COM (full Excel) or openpyxl (lightweight)
- Read sheets, ranges, used ranges
- Compute column statistics (sum, mean, min, max)
- Filter rows by condition
- Highlight rows, apply formatting
- Create charts (COM or matplotlib)
- Save as XLSX/CSV

### Word Agent (`word_agent.py`)
- Create documents from scratch or templates
- Insert headings, paragraphs, tables, images
- Set headers/footers, page breaks, TOC
- Format titles, apply themes
- Rewrite content using LLM
- Save as DOCX or PDF

### Email Agent (`email_agent.py`)
- Draft emails via Outlook COM
- SMTP fallback when Outlook is unavailable
- LLM-generated email bodies
- File attachments (Word, Excel, PDF)
- Save to Drafts or send (requires approval)

### File Agent (`file_agent.py`)
- Search by name, type, date, directory
- Resolve `Downloads`, `Desktop`, `Documents` aliases
- Find latest modified file
- Read/write text files
- Safe versioned writes (auto-backup existing files)

### UI Automation Agent (`ui_automation_agent.py`)
- pyautogui for mouse/keyboard/screenshot
- pywinauto for window detection/focus
- Template image matching (find & click UI elements)
- Fallback for apps without COM interfaces

## Architecture

```
User Request
     │
     ▼
Orchestrator (QThread worker)
     │
     ├── PlannerAgent ──── Grok API ──→ ExecutionPlan (JSON)
     │
     ├── For each PlanStep:
     │    ├── Check approval (ApprovalService)
     │    ├── Resolve template variables (ContextManager)
     │    ├── Route to agent (ExcelAgent / WordAgent / etc.)
     │    ├── Execute tool call
     │    ├── Store result in context
     │    └── Detect and register artifacts
     │
     └── Build summary → emit to UI
```

## Safety

- All email sends require approval (configurable)
- File deletion/overwrite requires approval in Safe mode
- Bulk edits flagged as medium risk
- Dry-run mode simulates everything
- COM errors trigger openpyxl/python-docx fallback
- Screenshot captured on UI automation failure

## Requirements

- **Python 3.11+**
- **Windows 10/11** (for COM automation)
- **Microsoft Office** (optional — fallbacks available)
- **Grok API key** (optional — mock mode available)

## Extending the System

To add a new agent (e.g. PowerPoint):

1. Create `agents/powerpoint_agent.py` extending `BaseAgent`
2. Register tools in `_register_tools()`
3. Add `AgentType.POWERPOINT` to `models/schemas.py`
4. Map in `app/orchestrator.py` `_agent_map`
5. Add tool descriptions to `prompts/planner_prompts.py`
