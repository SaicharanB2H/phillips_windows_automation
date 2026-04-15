"""
Prompt templates for specialized agents (Excel, Word, Email).
Used when agents need LLM assistance for content generation.
"""

# ─────────────────────────────────────────────
# Excel Agent Prompts
# ─────────────────────────────────────────────

EXCEL_SUMMARIZE_PROMPT = """
You are a data analyst. You are given tabular Excel data.
Analyze the data and provide:
1. A brief executive summary (2-3 sentences)
2. Key metrics (totals, averages, top/bottom performers)
3. Notable patterns or anomalies
4. Recommendations based on the data

Format your response as structured text suitable for inserting into a Word document.
"""

EXCEL_COLUMN_DETECT_PROMPT = """
Given these Excel column headers: {headers}
And a user request: "{request}"

Identify which columns are most relevant to the request.
Return JSON: {{"relevant_columns": [...], "aggregate_column": "column_name", "filter_column": "column_name", "date_column": "column_name"}}
"""


# ─────────────────────────────────────────────
# Word Agent Prompts
# ─────────────────────────────────────────────

WORD_REPORT_INTRO_PROMPT = """
Write a professional executive introduction for a business report titled: "{title}"
Context: {context}
The introduction should be 2-3 paragraphs, formal but readable.
Start directly with the content — no meta-commentary.
"""

WORD_SECTION_PROMPT = """
Write a professional section for a business document.
Section title: {title}
Context/data: {context}
Tone: {tone}
Length: approximately {word_count} words.
Write in flowing prose. Start directly with content.
"""

WORD_REWRITE_PROMPT = """
Rewrite the following text in a {tone} professional tone.
Improve clarity, fix grammar, and make it executive-ready.
Preserve all key facts and numbers.
Original text:
---
{original_text}
---
Return only the rewritten text, no commentary.
"""


# ─────────────────────────────────────────────
# Email Agent Prompts
# ─────────────────────────────────────────────

EMAIL_DRAFT_PROMPT = """
Write a professional business email with these details:
- Recipient context: {recipient_context}
- Subject: {subject}
- Key points to cover: {key_points}
- Tone: {tone}
- Attachments to mention: {attachments}

Write a complete email body. Include a proper greeting, clear body paragraphs, and a professional sign-off.
Do not include the subject line — only the body.
Return only the email body text.
"""

EMAIL_SUMMARY_PROMPT = """
Write a concise email body that summarizes the following content:
{content}

The email should be:
- Professional and clear
- 2-4 short paragraphs
- Include a polite call to action at the end
- Sign off as "Best regards, [Your Name]"
"""


# ─────────────────────────────────────────────
# File Agent Prompts
# ─────────────────────────────────────────────

FILE_AMBIGUITY_PROMPT = """
The user asked for: "{user_request}"
These files were found matching the criteria:
{file_list}

Which file most likely matches what the user wants?
Return JSON: {{"selected_index": 0, "confidence": "high|medium|low", "reason": "..."}}
If confidence is low, set selected_index to -1 and explain in reason.
"""
