import os
import streamlit as st
import uuid

from ui.ui_sidebar import set_variables
# from config.Configuration import set_rag_stats

LOGO_PATH = "ressource/Eau_de_Paris_bleu.svg.png"
IS_DEV = os.environ.get("IS_DEV", "no")

st.set_page_config(page_title="Analyse de compte-rendu CrewAI", page_icon="📄", layout="wide")




def initialize_session_state():
    """Initialise toutes les variables de session utilisées par l'application."""
    default_states = {
        "results": None,
        "analyses": None,
        "redaction_raw": None,
        "docx_ok": None,
        "docx_error": None,
        "success_msg": None,
        "agent_config": None,
        "auto_process_enabled": True,
    }
    for key, default_value in default_states.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

    agent_keys = {
        "backend_url": None,
        "ollama_base_url": None,
        "model_name": None,
        "verbosity": None,
        "agent_order": None,

    }
    for key, default_value in agent_keys.items():
            if key not in st.session_state:
                st.session_state[key] = default_value


    for key in [
        "transcript_text",
        "format_instructions_fichier",
        "final_summary",
        "combined_notes",
        "is_transcribing",
        
        ]:
        if key not in st.session_state:
            if key == "is_transcribing":
                st.session_state[key] = False

            else:
                st.session_state[key] = None if key != "transcript_text" else ""

    # Côté Streamlit, une seule fois au démarrage de la session
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "is_dev" not in st.session_state:
        st.session_state.is_dev = IS_DEV

    ## Initialize rag_config for RAG configuration
    #if "rag_config" not in st.session_state:
    #    from config.Configuration import set_rag_stats
    #    st.session_state.rag_config = set_rag_stats()

# 1. On initialise les états AVANT de charger le moindre composant UI


# ─── ROUTAGE ET NAVIGATION ─────────────────────────────────────────────
def main():
    initialize_session_state()
    with st.sidebar:
        st.markdown("### ⚙️ Options")
        st.toggle(
        "Mode automatique",
        key="auto_process_enabled",
        help="Si activé, le processus de génération de compte-rendu se lance automatiquement après la transcription"
    )
    backend_url, ollama_base_url, model_name, verbosity, agent_order = set_variables()
    st.session_state.backend_url = backend_url
    st.session_state.ollama_base_url = ollama_base_url
    st.session_state.model_name = model_name
    st.session_state.verbosity = verbosity
    st.session_state.agent_order = agent_order
    # Déclaration des pages
    page_CR = st.Page("pages/main_page.py", title="Rédacteur Compte-rendu", default=True)
    #page_changelog = st.Page("eeeeeeeeeeeeee/zzz.py", title="Changelog", icon="📝")
    #page_config = st.Page("config/Configuration.py", title="Configuration", icon="⚙️")

    # Construction dynamique de la navigation
    pages_visibles = [page_CR]

    # Ajout conditionnel de la page de config
    #if st.session_state.is_dev == "yes":
    #    #pages_visibles.append(page_changelog)
    #    pages_visibles.append(page_config)
#
    # Exécution de la navigation
    pg = st.navigation(pages_visibles)
    pg.run()

if __name__ == "__main__":
    main()