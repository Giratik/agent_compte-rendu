# frontend/utility/session_state_central.py

from typing import Any, Optional, Dict
import streamlit as st
import uuid
import os

API_URL = os.environ.get("API_URL", "http://backend:8000")
DEFAULT_LLM = os.environ.get("DEFAULT_LLM", "gemma4:e4b")

# ─── Constantes (noms des clés) ───────────────────────────────────────────────

class SK:
    """Session Keys — toutes les clés en un seul endroit."""
    # Identité & conversation
    SESSION_ID                   = "session_id"
    AGENT_ORDER                  = "agent_order"
    THINK_MODE                   = "think_mode"
    VERBOSITY                    = "verbosity"

    IS_TRANSCRIBING              = "is_transcribing"
    TRANSCRIPTION_QUEUE_TOKEN    = "transcription_queue_token"
    TRANSCRIPTION_QUEUE_POSITION = "transcription_queue_position"
    TRANSCRIPT_TEXT              = "transcript_text"
    TOKEN_COUNT                  = "token_count"

    AGENT_META                   = "agent_meta"
    AGENTS_META                  = "agents_meta"
    AGENT_CONFIG                 = "agent_config"

    RESULTS                      = "results"
    ANALYSE                      = "analyse"
    REDACTION_RAW                = "redaction_raw"
    DOCX_OK                      = "docx_ok"
    DOCX_ERROR                   = "docx_error"
    SUCCESS_MSG                  = "success_msg"

    # RAG
    RAG_CONFIG                   = "rag_config"
    AUTO_RUN                     = "auto_run_agents"

    USER_INPUT                   = "user_input"


_DEFAULTS: dict[str, Any] = {
    SK.VERBOSITY:                    None,
    SK.AGENT_ORDER:                  [],
    SK.SESSION_ID:                   None,

    SK.IS_TRANSCRIBING:              False,
    SK.TRANSCRIPTION_QUEUE_TOKEN:    None,
    SK.TRANSCRIPTION_QUEUE_POSITION: None,
    SK.TRANSCRIPT_TEXT:              "",
    SK.TOKEN_COUNT:                  0,

    SK.AGENTS_META:                  None,
    SK.AGENT_CONFIG:                 {},
    SK.AGENT_META:                   {},

    SK.RESULTS:                      None,
    SK.ANALYSE:                      None,
    SK.REDACTION_RAW:                None,
    SK.DOCX_OK:                      False,
    SK.DOCX_ERROR:                   None,
    SK.SUCCESS_MSG:                  None,

    SK.RAG_CONFIG: lambda: {
        "collection": [],
        "model":      DEFAULT_LLM,
        "n_results":  250,
        "seuil":      0.6,
        "alpha":      0.5,
    },
    SK.AUTO_RUN:                     True,
    SK.USER_INPUT:                   None,
}

# ─── Initialisation ───────────────────────────────────────────────────────────

def init_session_state() -> None:
    """À appeler une seule fois au démarrage (Main.py)."""
    for key, default in _DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default() if callable(default) else default

    if st.session_state[SK.SESSION_ID] is None:
        st.session_state[SK.SESSION_ID] = str(uuid.uuid4())

def set_rag_config(**kwargs) -> None:
    """Met à jour une ou plusieurs clés de RAG_CONFIG."""
    config = get(SK.RAG_CONFIG) or {}
    config.update(kwargs)
    set(SK.RAG_CONFIG, config)

def get_rag_collections() -> list[str]:
    return get(SK.RAG_CONFIG).get("collection", [])

def set_rag_collections(collections: list[str]) -> None:
    set_rag_config(collection=collections)

# ─── Accesseurs bas niveau ────────────────────────────────────────────────────

def get(key: str) -> Any:
    return st.session_state.get(key)

def set(key: str, value: Any) -> None:
    st.session_state[key] = value

def reset_session_state() -> None:
    """Réinitialise toutes les variables de session à leurs valeurs par défaut."""
    for key, default in _DEFAULTS.items():
        st.session_state[key] = default() if callable(default) else default


# ─── Helpers — transcription ──────────────────────────────────────────────────

def is_transcription_in_progress() -> bool:
    return get(SK.IS_TRANSCRIBING) or False

def is_in_queue() -> bool:
    return get(SK.TRANSCRIPTION_QUEUE_TOKEN) is not None

def has_transcript() -> bool:
    transcript = get(SK.TRANSCRIPT_TEXT) or ""
    return bool(transcript.strip())

def get_queue_position() -> Optional[int]:
    return get(SK.TRANSCRIPTION_QUEUE_POSITION)

def start_transcription() -> None:
    set(SK.IS_TRANSCRIBING, True)

def stop_transcription() -> None:
    set(SK.IS_TRANSCRIBING, False)

def set_transcript_text(text: str) -> None:
    set(SK.TRANSCRIPT_TEXT, text)
    set(SK.TOKEN_COUNT, len(text.split()) if text else 0)

def set_queue_info(token: Optional[str], position: Optional[int]) -> None:
    set(SK.TRANSCRIPTION_QUEUE_TOKEN, token)
    set(SK.TRANSCRIPTION_QUEUE_POSITION, position)

def clear_queue_info() -> None:
    set(SK.TRANSCRIPTION_QUEUE_TOKEN, None)
    set(SK.TRANSCRIPTION_QUEUE_POSITION, None)


# ─── Helpers — agents ────────────────────────────────────────────────────────

def get_agent_config() -> Dict[str, Any]:
    return get(SK.AGENT_CONFIG) or {}

def set_agent_config(config: Dict[str, Any]) -> None:
    set(SK.AGENT_CONFIG, config)

def get_agents_meta() -> Optional[Dict[str, Any]]:
    return get(SK.AGENTS_META)

def set_agents_meta(meta: Dict[str, Any]) -> None:
    set(SK.AGENTS_META, meta)


# ─── Helpers — résultats ──────────────────────────────────────────────────────

def has_analysis_results() -> bool:
    return get(SK.RESULTS) is not None

def get_analysis_results() -> Optional[Dict[str, Any]]:
    return get(SK.RESULTS)

def set_analysis_results(results: Dict[str, Any]) -> None:
    set(SK.RESULTS, results)

def get_redaction_raw() -> Optional[str]:
    return get(SK.REDACTION_RAW)

def set_redaction_raw(redaction: str) -> None:
    set(SK.REDACTION_RAW, redaction)

def update_redaction_status(docx_ok: bool, docx_error: Optional[str] = None) -> None:
    set(SK.DOCX_OK, docx_ok)
    set(SK.DOCX_ERROR, docx_error)