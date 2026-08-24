import os
import streamlit as st
import requests
import api_client as api
from utility.session_state_central_cr import SK, get, set as ss_set

BACKEND_URL_DEFAULT = os.environ.get("BACKEND_URL", "http://backend:8000")
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://10.75.12.5:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")


def render_sidebar():
    """Affiche la barre latérale et retourne les paramètres de configuration."""
    with st.sidebar:
        st.markdown("### ⚙️ Options")
        st.toggle(
            "Mode automatique",
            key="auto_run_agents",
            help="Si activé, le processus de génération de compte-rendu se lance automatiquement après la transcription",
        )
        #st.header("⚙️ Backend")
        backend_url = BACKEND_URL_DEFAULT

        #st.header("🧠 Configuration LLM (Ollama)")
        #st.caption("Ces valeurs sont envoyées au backend, qui appelle Ollama depuis son propre réseau Docker.")
        #ollama_base_url = st.text_input("URL du serveur Ollama (vue depuis le backend)", value=OLLAMA_URL)
        #model_name = st.text_input("Modèle Ollama", value="gemma4:e4b", help="ex: gemma2:9b, qwen2.5:14b, llama3.1:8b...")
        #verbosity_label = st.radio(
        #    "Niveau de détail de la rédaction",
        #    ["Concis", "Détaillé"],
        #    help="'Détaillé' demande au rédacteur de ne pas fusionner ni condenser les points des analyses.",
        #)
        verbosity = "concis"

        #st.markdown("---")

        # --- Config des agents, récupérée dynamiquement depuis le backend ---
        st.header("🤖 Configuration des agents")
        if get(SK.AGENTS_META) is None:
            try:
                ss_set(SK.AGENTS_META, api.get_agents_config(backend_url))
            except requests.RequestException as e:
                ss_set(SK.AGENTS_META, None)
                st.error(f"Impossible de joindre le backend ({backend_url}) : {e}")

        agent_order = []
        if get(SK.AGENTS_META):
            agent_order = get(SK.AGENTS_META)["agent_order"]
            agent_meta  = get(SK.AGENTS_META)["agent_meta"]

            # dict vide = pas encore initialisé (DEFAULTS = {})
            if not get(SK.AGENT_CONFIG):
                ss_set(SK.AGENT_CONFIG, get(SK.AGENTS_META)["default_agent_config"].copy())

            agent_config = get(SK.AGENT_CONFIG).copy()
            for key in agent_order:
                meta = agent_meta[key]
                agent_config[key] = st.checkbox(
                    meta["label"],
                    value=agent_config.get(key, True),
                    help=meta["description"],
                    key=f"cfg_{key}",
                )
            agent_config["redacteur"] = st.checkbox(
                "📝 Rédacteur (JSON)",
                value=True,
                help="Consolide les analyses activées en compte-rendu final.",
                disabled=True,
            )

            if not any(agent_config[k] for k in agent_order):
                st.warning("Active au moins un agent d'analyse pour pouvoir lancer une analyse.")

            if agent_config != get(SK.AGENT_CONFIG):
                ss_set(SK.AGENT_CONFIG, agent_config)
        else:
            st.stop()

        return verbosity, agent_order