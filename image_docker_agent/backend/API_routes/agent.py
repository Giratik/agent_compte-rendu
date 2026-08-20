

import threading
import functools
from io import BytesIO
import os

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse


OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434" )

from agents import (
    AGENT_ORDER,
    AGENT_META,
    TASK_LABELS,
    DEFAULT_AGENT_CONFIG,
    build_crew,
    build_redaction_retry_crew,
    build_json_fix_crew,
    build_revision_crew,
)
from docx_export import parse_redaction_json, diagnose_json_error, build_docx
from job_store import job_store
from schemas import (
    AnalyzeRequest,
    JobStatusResponse,
    JobStepStatus,
    SectionResult,
    ReviseRequest,
    ReviseResponse,
    RedactionRetryRequest,
    RedactionResultResponse,
    JsonFixRequest,
    JsonDiagnoseRequest,
    JsonDiagnoseResponse,
    DocxBuildRequest,
)

from engines.agent_engine import _try_build_docx, _run_analysis_job, _job_to_response

router = APIRouter(prefix="/agent", tags=["Agent tools"])

# --------------------------------------------------------------------------
# Config des agents (pour que le frontend construise son UI dynamiquement)
# --------------------------------------------------------------------------


@router.get("/config")
def get_agents_config():
    return {
        "agent_order": AGENT_ORDER,
        "agent_meta": AGENT_META,
        "default_agent_config": DEFAULT_AGENT_CONFIG,
    }


# --------------------------------------------------------------------------
# Analyse complète (asynchrone, avec suivi de progression)
# --------------------------------------------------------------------------

@router.post("/analyze", response_model=JobStatusResponse)
def analyze(req: AnalyzeRequest):
    cfg = req.agent_config.model_dump()
    used_keys = [k for k in AGENT_ORDER if cfg.get(k)]
    if not used_keys:
        raise HTTPException(400, "Aucun agent d'analyse activé.")
    if cfg.get("redacteur"):
        used_keys = used_keys + ["redacteur"]

    planned_steps = [{"key": k, "label": TASK_LABELS.get(k, k), "status": "pending"} for k in used_keys]
    job = job_store.create(total_steps=len(planned_steps), planned_steps=planned_steps)

    thread = threading.Thread(target=_run_analysis_job, args=(job.job_id, req), daemon=True)
    thread.start()

    return _job_to_response(job)





@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job introuvable.")
    return _job_to_response(job)


# --------------------------------------------------------------------------
# Révision d'une section (rapide, synchrone — pas besoin de job)
# --------------------------------------------------------------------------


@router.post("/revise", response_model=ReviseResponse)
def revise(req: ReviseRequest):
    try:
        crew = build_revision_crew(
            section_name=req.section_name,
            current_text=req.current_text,
            instructions=req.instructions,
            model_name=req.llm.model_name,
            base_url=req.llm.base_url,
        )
        output = crew.kickoff()
        return ReviseResponse(new_text=output.tasks_output[-1].raw)
    except Exception as e:
        raise HTTPException(500, f"Échec de la révision : {e}")


# --------------------------------------------------------------------------
# Rédacteur : relance / correction JSON
# --------------------------------------------------------------------------


@router.post("/redaction/retry", response_model=RedactionResultResponse)
def redaction_retry(req: RedactionRetryRequest):
    try:
        crew = build_redaction_retry_crew(
            analyses=req.analyses,
            model_name=req.llm.model_name,
            base_url=req.llm.base_url,
            verbosity=req.verbosity,
        )
        output = crew.kickoff()
        raw_json = output.tasks_output[-1].raw
        docx_ok, docx_error = _try_build_docx(raw_json)
        return RedactionResultResponse(raw_json=raw_json, docx_ok=docx_ok, docx_error=docx_error)
    except Exception as e:
        raise HTTPException(500, f"Échec de la relance du rédacteur : {e}")


@router.post("/redaction/fix", response_model=RedactionResultResponse)
def redaction_fix(req: JsonFixRequest):
    error_report = diagnose_json_error(req.broken_json)
    if error_report is None:
        docx_ok, docx_error = _try_build_docx(req.broken_json)
        return RedactionResultResponse(raw_json=req.broken_json, docx_ok=docx_ok, docx_error=docx_error)
    try:
        crew = build_json_fix_crew(
            broken_json=req.broken_json,
            error_report=error_report,
            model_name=req.llm.model_name,
            base_url=req.llm.base_url,
        )
        output = crew.kickoff()
        raw_json = output.tasks_output[-1].raw
        docx_ok, docx_error = _try_build_docx(raw_json)
        return RedactionResultResponse(raw_json=raw_json, docx_ok=docx_ok, docx_error=docx_error)
    except Exception as e:
        raise HTTPException(500, f"Échec de la correction JSON : {e}")


# --------------------------------------------------------------------------
# Diagnostic / génération du .docx (aucun appel LLM)
# --------------------------------------------------------------------------


@router.post("/docx/diagnose", response_model=JsonDiagnoseResponse)
def docx_diagnose(req: JsonDiagnoseRequest):
    report = diagnose_json_error(req.raw_json)
    return JsonDiagnoseResponse(valid=report is None, error_report=report)


@router.post("/docx/build")
def docx_build(req: DocxBuildRequest):
    try:
        structured = parse_redaction_json(req.raw_json)
        buffer = build_docx(structured)
    except Exception as e:
        raise HTTPException(422, f"JSON invalide, impossible de générer le .docx : {e}")

    return StreamingResponse(
        BytesIO(buffer.getvalue()),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=compte_rendu.docx"},
    )


@router.get("/health")
def health():
    return {"status": "ok"}


