"""
Backend FastAPI — toute la logique CrewAI/docx vit ici, sans aucun état
d'affichage. Le frontend Streamlit (ou n'importe quel autre client) parle à
cette API en HTTP.

Découpage des endpoints :
- POST /analyze         : démarre un job d'analyse complet (async, threadé)
- GET  /jobs/{job_id}    : poll de la progression / résultat du job
- POST /revise           : révise UNE section déjà générée (rapide, synchrone)
- POST /redaction/retry   : relance uniquement le rédacteur (JSON)
- POST /redaction/fix     : corrige un JSON cassé via l'agent correcteur
- POST /docx/diagnose     : diagnostic JSON (ligne/colonne/contexte), sans LLM
- POST /docx/build        : construit le .docx à partir d'un JSON, le renvoie en fichier
- GET  /agents/config     : expose AGENT_ORDER / AGENT_META pour que le frontend
                             construise dynamiquement ses checkboxes/labels
"""

import threading
import functools
from io import BytesIO

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

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

app = FastAPI(title="Compte-rendu multi-agents — API")


# --------------------------------------------------------------------------
# Config des agents (pour que le frontend construise son UI dynamiquement)
# --------------------------------------------------------------------------


@app.get("/agents/config")
def get_agents_config():
    return {
        "agent_order": AGENT_ORDER,
        "agent_meta": AGENT_META,
        "default_agent_config": DEFAULT_AGENT_CONFIG,
    }


# --------------------------------------------------------------------------
# Analyse complète (asynchrone, avec suivi de progression)
# --------------------------------------------------------------------------


def _try_build_docx(raw_json: str) -> tuple[bool, str | None]:
    try:
        structured = parse_redaction_json(raw_json)
        build_docx(structured)  # valide que la génération ne plante pas
        return True, None
    except Exception as e:
        return False, str(e)


def _run_analysis_job(job_id: str, req: AnalyzeRequest):
    cfg = req.agent_config.model_dump()

    def on_task_complete(key: str, output):
        job_store.mark_step_done(job_id, key)

    try:
        crew = build_crew(
            transcript=req.transcript,
            model_name=req.llm.model_name,
            base_url=req.llm.base_url,
            agent_config=cfg,
            on_task_complete=on_task_complete,
            verbosity=req.verbosity,
        )
        crew_output = crew.kickoff()

        used_keys = [k for k in AGENT_ORDER if cfg.get(k)]
        if cfg.get("redacteur"):
            used_keys = used_keys + ["redacteur"]

        results = [
            {"key": k, "label": TASK_LABELS.get(k, k), "content": t.raw}
            for k, t in zip(used_keys, crew_output.tasks_output)
        ]
        analyses = {r["key"]: r["content"] for r in results if r["key"] != "redacteur"}

        redaction_raw = None
        docx_ok = None
        docx_error = None
        if cfg.get("redacteur") and results:
            redaction_raw = results[-1]["content"]
            docx_ok, docx_error = _try_build_docx(redaction_raw)

            # Réparation automatique (même logique que côté Streamlit avant)
            MAX_AUTO_FIX_ATTEMPTS = 2
            attempt = 0
            while not docx_ok and attempt < MAX_AUTO_FIX_ATTEMPTS:
                attempt += 1
                error_report = diagnose_json_error(redaction_raw or "")
                if error_report is None:
                    docx_ok, docx_error = _try_build_docx(redaction_raw)
                    break
                try:
                    fix_crew = build_json_fix_crew(
                        broken_json=redaction_raw,
                        error_report=error_report,
                        model_name=req.llm.model_name,
                        base_url=req.llm.base_url,
                    )
                    fix_output = fix_crew.kickoff()
                    redaction_raw = fix_output.tasks_output[-1].raw
                    docx_ok, docx_error = _try_build_docx(redaction_raw)
                except Exception as fix_err:
                    docx_error = f"Échec de la réparation automatique : {fix_err}"
                    break

        job_store.finish(
            job_id,
            results=results,
            analyses=analyses,
            redaction_raw=redaction_raw,
            docx_ok=docx_ok,
            docx_error=docx_error,
        )
    except Exception as e:
        job_store.fail(job_id, str(e))


@app.post("/analyze", response_model=JobStatusResponse)
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


def _job_to_response(job) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        total_steps=job.total_steps,
        completed_steps=job.completed_steps,
        steps=[JobStepStatus(**s) for s in job.steps],
        results=[SectionResult(**r) for r in job.results] if job.results else None,
        analyses=job.analyses,
        redaction_raw=job.redaction_raw,
        docx_ok=job.docx_ok,
        docx_error=job.docx_error,
        error=job.error,
    )


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job introuvable.")
    return _job_to_response(job)


# --------------------------------------------------------------------------
# Révision d'une section (rapide, synchrone — pas besoin de job)
# --------------------------------------------------------------------------


@app.post("/revise", response_model=ReviseResponse)
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


@app.post("/redaction/retry", response_model=RedactionResultResponse)
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


@app.post("/redaction/fix", response_model=RedactionResultResponse)
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


@app.post("/docx/diagnose", response_model=JsonDiagnoseResponse)
def docx_diagnose(req: JsonDiagnoseRequest):
    report = diagnose_json_error(req.raw_json)
    return JsonDiagnoseResponse(valid=report is None, error_report=report)


@app.post("/docx/build")
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


@app.get("/health")
def health():
    return {"status": "ok"}