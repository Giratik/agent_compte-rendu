#frontend/agent_summary/script.py

import streamlit as st
import requests
import api_client as api
from ui.ui_components import render_preview
from ui.ui_sidebar import render_sidebar, set_variables
import core_logic as core




def render_agent_summary():
    # --- Sidebar : Configuration et sélection des agents ---
    backend_url = st.session_state.backend_url 
    ollama_base_url = st.session_state.ollama_base_url 
    model_name = st.session_state.model_name 
    verbosity = st.session_state.verbosity 
    agent_order = st.session_state.agent_order 

    transcript = st.session_state.transcript_text

    # --- Lancement de l'analyse ---
    st.subheader("Lancer l'analyse")
    no_agent_active = not any(st.session_state.agent_config.get(k, True) for k in agent_order)
    

    is_transcript_ready = bool(transcript.strip())
    has_no_results_yet = st.session_state.results is None
    auto_run = st.session_state.get("auto_process_enabled", False) and is_transcript_ready and not no_agent_active and has_no_results_yet

    if auto_run:
        run = st.button("🚀 Lancer les agents", type="primary", disabled=True)
    else:
        run = st.button("🚀 Lancer les agents", type="primary", disabled=not transcript.strip() or no_agent_active)

    # 3. Exécution si clic manuel OU condition automatique remplie
    if run or auto_run:
        # L'appel à la fonction gère la requête, le polling, et les mises à jour UI/session_state
        core.execute_analysis(backend_url, transcript, st.session_state.agent_config, model_name, ollama_base_url, verbosity)
        
        # Force le rafraîchissement de la page pour afficher directement la section 3 après le traitement automatique
        if auto_run:
            st.rerun()

    # --- Aperçu et modifications ---
    st.markdown("<div id='section-3'></div>", unsafe_allow_html=True)
    st.subheader("Aperçu du compte-rendu final")

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
                if core.apply_global_modifications(backend_url, model_name, ollama_base_url, verbosity, global_instructions):
                    st.session_state.success_msg = "Vos modifications ont été appliquées ! Le nouvel aperçu est affiché juste au-dessus ([ici](#section-3)), et le fichier Word a été mis à jour."
                    st.rerun()



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
                    
                    # Auto-correction silencieuse
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
                    
                    st.session_state.success_msg = "Nouvelle rédaction terminée ! Le nouvel aperçu est affiché juste au-dessus ([ici](#section-3)), et le fichier Word a été mis à jour."
                    st.rerun()
                except requests.RequestException as e:
                    st.error(f"Échec de la relance détaillée : {e}")

            # Affichage du message de succès persistant si une action de modification vient de se terminer
        if st.session_state.success_msg:
            st.success(st.session_state.success_msg, icon="✅")
            st.session_state.success_msg = None  # On le vide pour ne l'afficher qu'une seule fois

        # --- Export et rattrapages d'erreurs ---
        st.subheader("Export Word")
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

        # with col_expand:
                

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
                        st.session_state.success_msg = "JSON corrigé avec succès ! L'aperçu et le fichier Word sont à jour."
                        st.rerun()
                    except requests.RequestException as e:
                        st.error(f"Échec de la correction automatique : {e}")
    else:
        st.info("Collez ou uploadez un transcript, puis cliquez sur 'Lancer les agents'.")