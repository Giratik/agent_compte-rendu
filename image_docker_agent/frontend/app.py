import os
import time
import json
import re
import ast
import streamlit as st
import requests
import api_client as api
from ui.ui_components import render_preview
from ui.ui_sidebar import render_sidebar, set_variables

from core_logic import execute_analysis, apply_global_modifications

st.set_page_config(page_title="Analyse de compte-rendu CrewAI", page_icon="📄", layout="wide")
st.title("📄 Analyse multi-agents d'un compte-rendu de réunion")
st.caption("Frontend Streamlit – parle au backend FastAPI en HTTP, aucune logique CrewAI ici.")

# --- Sidebar : Configuration et sélection des agents ---
backend_url, ollama_base_url, model_name, verbosity, agent_order = set_variables()

# --- Initialisation des états de session ---
for key in ["results", "analyses", "redaction_raw", "docx_ok", "docx_error"]:
    if key not in st.session_state:
        st.session_state[key] = None

# --- Entrée du transcript ---
st.subheader("1. Transcript de la réunion")
input_mode = st.radio("Source du transcript", ["Coller le texte", "Uploader un fichier .txt"], horizontal=True)

transcript = ""
if input_mode == "Coller le texte":
    transcript = st.text_area(
        "Collez le transcript ici",
        height=280,
        placeholder="[10:02] Marie: Bonjour à tous, on est réunis pour...",
    )
else:
    uploaded = st.file_uploader("Fichier texte (.txt)", type=["txt"])
    if uploaded is not None:
        transcript = uploaded.read().decode("utf-8", errors="ignore")
        st.text_area("Aperçu du transcript", value=transcript, height=280, disabled=True)

# --- Lancement de l'analyse ---
st.subheader("2. Lancer l'analyse")
no_agent_active = not any(st.session_state.agent_config.get(k, True) for k in agent_order)
run = st.button("🚀 Lancer les agents", type="primary", disabled=not transcript.strip() or no_agent_active)

if run:
    # L'appel à la fonction gère la requête, le polling, et les mises à jour UI/session_state
    execute_analysis(backend_url, transcript, st.session_state.agent_config, model_name, ollama_base_url, verbosity)

# --- Aperçu et modifications ---
st.subheader("3. Aperçu du compte-rendu final")
if st.session_state.results:
    if st.session_state.docx_ok and st.session_state.redaction_raw:
        with st.container(border=True):
            render_preview(st.session_state.redaction_raw)
    else:
        st.info("L'aperçu n'est pas disponible car le document n'a pas encore été généré correctement.")

    st.divider()
    
    st.markdown("#### Demander des modifications globales")
    st.caption("Vos instructions s'appliqueront à l'ensemble du compte-rendu (toutes les sections). L'IA retravaillera chaque partie concernée et mettra à jour l'aperçu automatiquement.")
    
    global_instructions = st.text_area(
        "Que souhaitez-vous modifier dans le compte-rendu ?",
        placeholder="Ex: rends le texte plus formel, retire le nom de 'Jean', vulgarise les termes techniques...",
        key="inst_global",
    )

    if st.button("Appliquer la modification globale", key="btn_global"):
        if not global_instructions.strip():
            st.warning("Décris la modification souhaitée avant de valider.")
        else:
            # L'appel à la logique métier applique les modifications et met à jour st.session_state
            if apply_global_modifications(backend_url, model_name, ollama_base_url, verbosity, global_instructions):
                st.rerun()

    # --- Export et rattrapages d'erreurs ---
    st.subheader("4. Export Word")
    if not st.session_state.agent_config.get("redacteur", True):
        st.info("L'agent rédacteur est désactivé : l'export Word n'est pas disponible.")
    elif st.session_state.docx_ok:
        col_dl, col_expand = st.columns([2, 1])
        with col_dl:
            try:
                docx_bytes = api.docx_build(backend_url, st.session_state.redaction_raw)
                st.download_button(
                    "📥 Télécharger le compte-rendu (.docx)",
                    data=docx_bytes,
                    file_name="compte_rendu.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            except requests.RequestException as e:
                st.error(f"Échec de la génération du .docx : {e}")

        with col_expand:
            st.caption("Rédaction trop synthétique ?")
            if st.button("📝 Refaire en plus détaillé", disabled=not st.session_state.analyses):
                with st.spinner("Nouvelle rédaction, plus étoffée..."):
                    try:
                        redaction = api.redaction_retry(
                            backend_url=backend_url,
                            analyses=st.session_state.analyses,
                            model_name=model_name,
                            ollama_base_url=ollama_base_url,
                            verbosity="detaille",
                        )
                        
                        # Auto-correction
                        if not redaction["docx_ok"]:
                            st.toast("🛠️ Format JSON invalide, l'agent correcteur tente de réparer...")
                            try:
                                fixed = api.redaction_fix(backend_url, redaction["raw_json"], model_name, ollama_base_url)
                                st.session_state.redaction_raw = fixed["raw_json"]
                                st.session_state.docx_ok = fixed["docx_ok"]
                                st.session_state.docx_error = fixed["docx_error"]
                            except requests.RequestException:
                                st.session_state.redaction_raw = redaction["raw_json"]
                                st.session_state.docx_ok = redaction["docx_ok"]
                                st.session_state.docx_error = redaction["docx_error"]
                        else:
                            st.session_state.redaction_raw = redaction["raw_json"]
                            st.session_state.docx_ok = redaction["docx_ok"]
                            st.session_state.docx_error = redaction["docx_error"]
                        
                        st.rerun()
                    except requests.RequestException as e:
                        st.error(f"Échec de la relance détaillée : {e}")

    # Section d'erreur 
    if st.session_state.docx_error:
        st.warning(
            "L'agent rédacteur n'a pas renvoyé un JSON exploitable, impossible "
            f"de générer le .docx. Détail : {st.session_state.docx_error}"
        )
        try:
            diag = api.docx_diagnose(backend_url, st.session_state.redaction_raw or "")
            if diag.get("error_report"):
                with st.expander("🔍 Diagnostic détaillé (ligne / colonne / contexte)"):
                    st.code(diag["error_report"], language="text")
        except requests.RequestException:
            pass

        st.markdown("**Action requise :**")
        if st.button("🛠️ Tenter de corriger automatiquement le JSON"):
            with st.spinner("L'agent correcteur localise et corrige l'erreur..."):
                try:
                    fixed = api.redaction_fix(
                        backend_url, st.session_state.redaction_raw, model_name, ollama_base_url
                    )
                    st.session_state.redaction_raw = fixed["raw_json"]
                    st.session_state.docx_ok = fixed["docx_ok"]
                    st.session_state.docx_error = fixed["docx_error"]
                    st.rerun()
                except requests.RequestException as e:
                    st.error(f"Échec de la correction automatique : {e}")
else:
    st.info("Collez ou uploadez un transcript, puis cliquez sur 'Lancer les agents'.")