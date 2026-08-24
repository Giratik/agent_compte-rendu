"""
Client HTTP vers le backend FastAPI. Aucune logique métier ici — juste des
appels requests avec un timeout généreux (les appels LLM locaux peuvent être
lents) et des erreurs explicites.
"""

import requests

# Les appels LLM peuvent prendre plusieurs dizaines de secondes chacun.
DEFAULT_TIMEOUT = 600


def get_agents_config(backend_url: str) -> dict:
    r = requests.get(f"{backend_url}/agent/config", timeout=30)
    r.raise_for_status()
    return r.json()


def start_analysis(
    backend_url: str,
    transcript: str,
    agent_config: dict,
    model_name: str,
    ollama_base_url: str,
    verbosity: str = "concis",
    user_input: str = "",
) -> dict:
    payload = {
        "transcript": transcript,
        "agent_config": agent_config,
        "llm": {"model_name": model_name, "base_url": ollama_base_url},
        "verbosity": verbosity,
        "user_input": user_input,
    }
    r = requests.post(f"{backend_url}/agent/analyze", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def poll_job(backend_url: str, job_id: str) -> dict:
    r = requests.get(f"{backend_url}/agent/jobs/{job_id}", timeout=30)
    r.raise_for_status()
    return r.json()


def revise_section(
    backend_url: str,
    section_name: str,
    current_text: str,
    instructions: str,
    model_name: str,
    ollama_base_url: str,
) -> str:
    payload = {
        "section_name": section_name,
        "current_text": current_text,
        "instructions": instructions,
        "llm": {"model_name": model_name, "base_url": ollama_base_url},
    }
    r = requests.post(f"{backend_url}/agent/revise", json=payload, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return r.json()["new_text"]


def redaction_retry(
    backend_url: str,
    analyses: dict,
    model_name: str,
    ollama_base_url: str,
    verbosity: str = "concis",
    #user_input: str = "",
) -> dict:
    payload = {
        "analyses": analyses,
        "llm": {"model_name": model_name, "base_url": ollama_base_url},
        "verbosity": verbosity,
        #"user_input": user_input,
    }
    r = requests.post(f"{backend_url}/agent/redaction/retry", json=payload, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return r.json()


def redaction_fix(backend_url: str, broken_json: str, model_name: str, ollama_base_url: str) -> dict:
    payload = {
        "broken_json": broken_json,
        "llm": {"model_name": model_name, "base_url": ollama_base_url},
    }
    r = requests.post(f"{backend_url}/agent/redaction/fix", json=payload, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return r.json()


def docx_diagnose(backend_url: str, raw_json: str) -> dict:
    r = requests.post(f"{backend_url}/agent/docx/diagnose", json={"raw_json": raw_json}, timeout=30)
    r.raise_for_status()
    return r.json()


def docx_build(backend_url: str, raw_json: str) -> bytes:
    """Renvoie les octets du .docx, ou lève requests.HTTPError (422 si JSON invalide)."""
    r = requests.post(f"{backend_url}/agent/docx/build", json={"raw_json": raw_json}, timeout=60)
    r.raise_for_status()
    return r.content