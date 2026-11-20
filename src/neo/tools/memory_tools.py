from typing import Optional
from neo.core.memory import (
    update_project_memory as _update_project_memory,
    save_to_memory as _save_to_memory,
    recall_memory as _recall_memory,
    log_successful_debug as _log_successful_debug,
    save_concept as _save_concept,
)

def updateProjectMemory(section: str, content: str, mode: str = "replace", project_name: Optional[str] = None) -> str:
    """Update a canonical section of project-specific working memory."""
    return _update_project_memory(section=section, content=content, mode=mode, project_name=project_name)

def saveToGlobalMemory(information: str, category: str = "preference") -> str:
    """Save user preferences, instructions, or environment facts into global memory with duplicate and conflict resolution."""
    return _save_to_memory(information=information, category=category)

def recallEpisodicMemory(query: str) -> str:
    """Recall solutions, debugging insights, and architectural concepts using fast BM25 search."""
    return _recall_memory(query=query)

def logSuccessfulDebug(error_description: str, solution: str) -> str:
    """Log an error and verified resolution into episodic memory."""
    return _log_successful_debug(error_description=error_description, solution=solution)

def saveConcept(concept_name: str, explanation: str) -> str:
    """Save an architectural or codebase concept into episodic memory."""
    return _save_concept(concept_name=concept_name, explanation=explanation)

