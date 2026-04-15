"""
Tool schema registry — exposes all agent tools with their JSON schemas.
Used for introspection, validation, and future MCP-compatible serving.
"""
from agents.excel_agent import ExcelAgent
from agents.word_agent import WordAgent
from agents.email_agent import EmailAgent
from agents.file_agent import FileAgent
from agents.ui_automation_agent import UIAutomationAgent


def get_all_tool_names():
    """Return all registered tool names across all agents."""
    agents = [ExcelAgent(), WordAgent(), EmailAgent(), FileAgent(), UIAutomationAgent()]
    tools = []
    for agent in agents:
        tools.extend(agent.get_tool_names())
    return tools
