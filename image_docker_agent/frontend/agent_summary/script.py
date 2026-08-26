#frontend/agent_summary/script.py

import streamlit as st
import requests
import api_client as api
from ui.ui_components import render_preview
from ui.ui_sidebar import render_sidebar
import core_logic as core
from utility.session_state_central_cr import SK, get, set as ss_set,set_rag_collections, get_rag_collections

from plugins.wrapper_API import get_available_collection_names, fetch_full_lexicon, filter_relevant_definitions

from agent_summary.helper_lexique import enrich_transcript_with_acronyms

import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://10.75.12.5:11434")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")

def _sync_redaction(raw_json):
    ss_set(SK.RESULTS, [
        {**rr, "content": raw_json} if rr["key"] == "redacteur" else rr
        for rr in get(SK.RESULTS)
    ])


def render_agent_summary():
    # --- Sidebar : Configuration et sélection des agents ---
    backend_url = BACKEND_URL
    ollama_base_url = OLLAMA_HOST
    model_name = OLLAMA_MODEL
    verbosity = get(SK.VERBOSITY)
    agent_order = get(SK.AGENT_ORDER)
    user_input = get(SK.USER_INPUT)

    transcript = get(SK.TRANSCRIPT_TEXT)
    set_rag_collections(get_available_collection_names())
    collection_list = get_rag_collections()
    lexique_utile = None
    for element in collection_list:
            if element == "lexique":
                # 1. On récupère et filtre le lexique pertinent pour ce transcript
                lexique_complet = fetch_full_lexicon(element)
                lexique_utile = filter_relevant_definitions(lexique_complet, transcript)
                #st.write(lexique_utile)

    # --- Lancement de l'analyse ---
    st.subheader("Lancer l'analyse")
    if lexique_utile:
            transcript = enrich_transcript_with_acronyms(transcript, lexique_utile)
            #with st.expander("Voir le transcript enrichi"):
                #st.write(transcript)
        
    no_agent_active = not any(get(SK.AGENT_CONFIG).get(k, True) for k in agent_order)

    is_transcript_ready = bool(transcript.strip())
    has_no_results_yet = get(SK.RESULTS) is None
    auto_run = st.session_state.get("auto_run_agents", False) and is_transcript_ready and not no_agent_active and has_no_results_yet

    if auto_run:
        run = st.button("🚀 Lancer les agents", type="primary", disabled=True)
    else:
        run = st.button("🚀 Lancer les agents", type="primary", disabled=not transcript.strip() or no_agent_active)

    # 3. Exécution si clic manuel OU condition automatique remplie
    if run or auto_run:
        # L'appel à la fonction gère la requête, le polling, et les mises à jour UI/session_state
        core.execute_analysis(backend_url, transcript, get(SK.AGENT_CONFIG), model_name, ollama_base_url, verbosity, user_input)

        # Force le rafraîchissement de la page pour afficher directement la section 3 après le traitement automatique
        if auto_run:
            st.rerun()

    # --- Aperçu et modifications ---
    st.markdown("<div id='section-3'></div>", unsafe_allow_html=True)
    st.subheader("Aperçu du compte-rendu final")

    if get(SK.RESULTS):
        if get(SK.DOCX_OK) and get(SK.REDACTION_RAW):
            with st.container(border=True):
                render_preview(get(SK.REDACTION_RAW))
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
                if core.apply_global_modifications(backend_url, model_name, ollama_base_url, verbosity, global_instructions, user_input):
                    ss_set(SK.SUCCESS_MSG, "Vos modifications ont été appliquées ! Le nouvel aperçu est affiché juste au-dessus ([ici](#section-3)), et le fichier Word a été mis à jour.")
                    st.rerun()

        st.caption("Rédaction trop synthétique ?")
        if st.button("📝 Refaire en plus détaillé", disabled=not get(SK.ANALYSE)):
            with st.spinner("Nouvelle rédaction, plus étoffée..."):
                try:
                    redaction = api.redaction_retry(
                        backend_url=backend_url,
                        analyses=get(SK.ANALYSE),
                        model_name=model_name,
                        ollama_base_url=ollama_base_url,
                        verbosity="detaille",
                        user_input=SK.USER_INPUT,
                    )

                    # Auto-correction silencieuse
                    if not redaction["docx_ok"]:
                        try:
                            fixed = api.redaction_fix(backend_url, redaction["raw_json"], model_name, ollama_base_url)
                            ss_set(SK.REDACTION_RAW, fixed["raw_json"])
                            ss_set(SK.DOCX_OK, fixed["docx_ok"])
                            ss_set(SK.DOCX_ERROR, fixed["docx_error"])
                            # ← ici
                            _sync_redaction(fixed["raw_json"])
                        except requests.RequestException:
                            ss_set(SK.REDACTION_RAW, redaction["raw_json"])
                            ss_set(SK.DOCX_OK, redaction["docx_ok"])
                            ss_set(SK.DOCX_ERROR, redaction["docx_error"])
                            # ← et ici
                            _sync_redaction(redaction["raw_json"])
                    else:
                        ss_set(SK.REDACTION_RAW, redaction["raw_json"])
                        ss_set(SK.DOCX_OK, redaction["docx_ok"])
                        ss_set(SK.DOCX_ERROR, redaction["docx_error"])
                        # ← et ici
                        _sync_redaction(redaction["raw_json"])

                    ss_set(SK.SUCCESS_MSG, "Nouvelle rédaction terminée ! Le nouvel aperçu est affiché juste au-dessus ([ici](#section-3)), et le fichier Word a été mis à jour.")
                    st.rerun()
                except requests.RequestException as e:
                    st.error(f"Échec de la relance détaillée : {e}")

            # Affichage du message de succès persistant si une action de modification vient de se terminer
        if get(SK.SUCCESS_MSG):
            st.success(get(SK.SUCCESS_MSG), icon="✅")
            ss_set(SK.SUCCESS_MSG, None)  # On le vide pour ne l'afficher qu'une seule fois

        # --- Export et rattrapages d'erreurs ---
        st.subheader("Export Word")
        if not get(SK.AGENT_CONFIG).get("redacteur", True):
            st.info("L'agent rédacteur est désactivé : l'export Word n'est pas disponible.")
        elif get(SK.DOCX_OK):
            col_dl, col_expand = st.columns([2, 1])
            with col_dl:
                try:
                    docx_bytes = api.docx_build(backend_url, get(SK.REDACTION_RAW))
                    st.download_button(
                        "📥 Télécharger le compte-rendu (.docx)",
                        data=docx_bytes,
                        file_name="compte_rendu.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                except requests.RequestException as e:
                    st.error(f"Échec de la génération du .docx : {e}")

        # Section d'erreur
        if get(SK.DOCX_ERROR):
            st.warning(
                "L'agent rédacteur n'a pas renvoyé un JSON exploitable, impossible "
                f"de générer le .docx. Détail : {get(SK.DOCX_ERROR)}"
            )
            try:
                diag = api.docx_diagnose(backend_url, get(SK.REDACTION_RAW) or "")
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
                            backend_url, get(SK.REDACTION_RAW), model_name, ollama_base_url
                        )
                        ss_set(SK.REDACTION_RAW, fixed["raw_json"])
                        ss_set(SK.DOCX_OK, fixed["docx_ok"])
                        ss_set(SK.DOCX_ERROR, fixed["docx_error"])
                        ss_set(SK.SUCCESS_MSG, "JSON corrigé avec succès ! L'aperçu et le fichier Word sont à jour.")
                        st.rerun()
                    except requests.RequestException as e:
                        st.error(f"Échec de la correction automatique : {e}")
    else:
        st.info("Collez ou uploadez un transcript, puis cliquez sur 'Lancer les agents'.")