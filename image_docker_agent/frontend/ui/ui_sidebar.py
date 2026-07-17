import os
import streamlit as st
import requests
import api_client as api

BACKEND_URL_DEFAULT = os.environ.get("BACKEND_URL", "http://backend:8000")
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://10.75.12.5:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")

def set_variables():

    backend_url = BACKEND_URL_DEFAULT
    ollama_base_url = OLLAMA_URL
    model_name = OLLAMA_MODEL
    verbosity = "concis"

    with st.sidebar:
        # --- Config des agents, récupérée dynamiquement depuis le backend ---
        st.header("Configuration des agents")
        if "agents_meta" not in st.session_state:
            try:
                st.session_state.agents_meta = api.get_agents_config(backend_url)
            except requests.RequestException as e:
                st.session_state.agents_meta = None
                st.error(f"Impossible de joindre le backend ({backend_url}) : {e}")

        agent_order = []
        if st.session_state.agents_meta:
            agent_order = st.session_state.agents_meta["agent_order"]
            agent_meta = st.session_state.agents_meta["agent_meta"]

            # CORRECTION ICI : On vérifie si c'est None
            if st.session_state.get("agent_config") is None:
                st.session_state.agent_config = st.session_state.agents_meta["default_agent_config"].copy()

            agent_config = st.session_state.agent_config.copy()
            for key in agent_order:
                meta = agent_meta[key]
                agent_config[key] = st.checkbox(
                    meta["label"],
                    value=st.session_state.agent_config.get(key, True),
                    help=meta["description"],
                    key=f"cfg_{key}",
                )
            agent_config["redacteur"] = st.checkbox(
                "📝 Rédacteur (JSON)", value=True, help="Consolide les analyses activées en compte-rendu final.", disabled=True
            )

            if not any(agent_config[k] for k in agent_order):
                st.warning("Active au moins un agent d'analyse pour pouvoir lancer une analyse.")

            if agent_config != st.session_state.agent_config:
                st.session_state.agent_config = agent_config
        else:
            st.stop()
            
        return backend_url, ollama_base_url, model_name, verbosity, agent_order

def render_sidebar():
    """Affiche la barre latérale et retourne les paramètres de configuration."""
    with st.sidebar:
        st.header("⚙️ Backend")
        backend_url = st.text_input("URL du backend FastAPI", value=BACKEND_URL_DEFAULT).rstrip("/")

        st.header("🧠 Configuration LLM (Ollama)")
        st.caption("Ces valeurs sont envoyées au backend, qui appelle Ollama depuis son propre réseau Docker.")
        ollama_base_url = st.text_input("URL du serveur Ollama (vue depuis le backend)", value=OLLAMA_URL)
        model_name = st.text_input("Modèle Ollama", value="gemma4:e4b", help="ex: gemma2:9b, qwen2.5:14b, llama3.1:8b...")
        verbosity_label = st.radio(
            "Niveau de détail de la rédaction",
            ["Concis", "Détaillé"],
            help="'Détaillé' demande au rédacteur de ne pas fusionner ni condenser les points des analyses.",
        )
        verbosity = "detaille" if verbosity_label == "Détaillé" else "concis"

        st.markdown("---")

        # --- Config des agents, récupérée dynamiquement depuis le backend ---
        st.header("🤖 Configuration des agents")
        if "agents_meta" not in st.session_state:
            try:
                st.session_state.agents_meta = api.get_agents_config(backend_url)
            except requests.RequestException as e:
                st.session_state.agents_meta = None
                st.error(f"Impossible de joindre le backend ({backend_url}) : {e}")

        agent_order = []
        if st.session_state.agents_meta:
            agent_order = st.session_state.agents_meta["agent_order"]
            agent_meta = st.session_state.agents_meta["agent_meta"]

            # CORRECTION ICI AUSSI : On vérifie si c'est None
            if st.session_state.get("agent_config") is None:
                st.session_state.agent_config = st.session_state.agents_meta["default_agent_config"].copy()

            agent_config = st.session_state.agent_config.copy()
            for key in agent_order:
                meta = agent_meta[key]
                agent_config[key] = st.checkbox(
                    meta["label"],
                    value=st.session_state.agent_config.get(key, True),
                    help=meta["description"],
                    key=f"cfg_{key}",
                )
            agent_config["redacteur"] = st.checkbox(
                "📝 Rédacteur (JSON)", value=True, help="Consolide les analyses activées en compte-rendu final.", disabled=True
            )

            if not any(agent_config[k] for k in agent_order):
                st.warning("Active au moins un agent d'analyse pour pouvoir lancer une analyse.")

            if agent_config != st.session_state.agent_config:
                st.session_state.agent_config = agent_config
        else:
            st.stop()
            
        return backend_url, ollama_base_url, model_name, verbosity, agent_order