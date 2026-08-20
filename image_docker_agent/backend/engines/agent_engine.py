
import threading
import functools
from io import BytesIO
import os

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