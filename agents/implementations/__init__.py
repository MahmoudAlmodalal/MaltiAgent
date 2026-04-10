"""
Concrete BaseAgent subclasses, one per agent_type.

The AGENT_CLASSES registry maps agent_type strings to their classes —
Phase 7's Celery tasks use it to look up the right class from the orchestrator's
execution plan.
"""
from agents.base_agent import BaseAgent

from .api_designer import APIDesignerAgent
from .bug_fixer import BugFixerAgent
from .code_review import CodeReviewAgent
from .db_schema import DBSchemaAgent
from .documentation import DocumentationAgent
from .pm import PMAgent
from .research import ResearchAgent
from .system_designer import SystemDesignerAgent
from .testing import TestingAgent

AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "research": ResearchAgent,
    "pm": PMAgent,
    "system_designer": SystemDesignerAgent,
    "db_schema": DBSchemaAgent,
    "api_designer": APIDesignerAgent,
    "code_review": CodeReviewAgent,
    "bug_fixer": BugFixerAgent,
    "testing": TestingAgent,
    "documentation": DocumentationAgent,
}

__all__ = [
    "AGENT_CLASSES",
    "ResearchAgent",
    "PMAgent",
    "SystemDesignerAgent",
    "DBSchemaAgent",
    "APIDesignerAgent",
    "CodeReviewAgent",
    "BugFixerAgent",
    "TestingAgent",
    "DocumentationAgent",
]
