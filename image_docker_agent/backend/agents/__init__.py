"""
Package `agents` — crew d'analyse de transcripts de réunion.

Imports publics recommandés depuis app.py ou tout autre module externe :

    from agents import (
        AGENT_ORDER, AGENT_META, DEFAULT_AGENT_CONFIG, TASK_LABELS,
        build_crew,
        build_revision_crew,
        build_redaction_retry_crew,
        build_json_fix_crew,
    )
"""

from .base import AGENT_META, AGENT_ORDER, DEFAULT_AGENT_CONFIG, TASK_LABELS, build_llm
from .crew import (
    build_crew,
    build_json_fix_crew,
    build_redaction_retry_crew,
    build_revision_crew,
)

__all__ = [
    # Constantes de registre
    "AGENT_ORDER",
    "AGENT_META",
    "DEFAULT_AGENT_CONFIG",
    "TASK_LABELS",
    # Utilitaire LLM (expose pour app.py si besoin de créer un LLM standalone)
    "build_llm",
    # Builders de crew
    "build_crew",
    "build_revision_crew",
    "build_redaction_retry_crew",
    "build_json_fix_crew",
]