"""
Schémas Pydantic partagés entre les endpoints FastAPI.

Séparés du reste pour que main.py reste lisible et que le frontend puisse
potentiellement réutiliser ces définitions (ex: génération d'un client typé).
"""

from typing import Optional
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Reflète les clés de agents.AGENT_ORDER + 'redacteur'."""

    participants: bool = True
    objectif: bool = True
    points_cles: bool = True
    outils_chiffres: bool = True
    decisions: bool = True
    actions: bool = True
    risques: bool = True
    redacteur: bool = True


class LLMConfig(BaseModel):
    model_name: str = "gemma4:e4b"
    base_url: str = "http://ollama:11434"  # nom de service Docker par défaut


class AnalyzeRequest(BaseModel):
    transcript: str
    agent_config: AgentConfig = Field(default_factory=AgentConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    verbosity: str = "concis"  # "concis" | "detaille"
    user_input: str = ""


class JobStepStatus(BaseModel):
    key: str
    label: str
    status: str  # "pending" | "done"


class SectionResult(BaseModel):
    key: str
    label: str
    content: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # "running" | "done" | "error"
    total_steps: int
    completed_steps: int
    steps: list[JobStepStatus] = []
    results: Optional[list[SectionResult]] = None
    analyses: Optional[dict[str, str]] = None
    redaction_raw: Optional[str] = None
    docx_ok: Optional[bool] = None
    docx_error: Optional[str] = None
    error: Optional[str] = None


class ReviseRequest(BaseModel):
    section_name: str
    current_text: str
    instructions: str
    llm: LLMConfig = Field(default_factory=LLMConfig)


class ReviseResponse(BaseModel):
    new_text: str


class RedactionRetryRequest(BaseModel):
    analyses: dict[str, str]
    llm: LLMConfig = Field(default_factory=LLMConfig)
    verbosity: str = "concis"
    user_input: str = ""


class RedactionResultResponse(BaseModel):
    raw_json: str
    docx_ok: bool
    docx_error: Optional[str] = None


class JsonFixRequest(BaseModel):
    broken_json: str
    llm: LLMConfig = Field(default_factory=LLMConfig)


class JsonDiagnoseRequest(BaseModel):
    raw_json: str


class JsonDiagnoseResponse(BaseModel):
    valid: bool
    error_report: Optional[str] = None


class DocxBuildRequest(BaseModel):
    raw_json: str


# Pydantic model
class RedactionReviseRequest(BaseModel):
    current_raw_json: str
    instructions: str
    llm: LLMConfig