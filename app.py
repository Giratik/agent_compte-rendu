import streamlit as st

from agents import build_crew, build_redaction_retry_crew, build_json_fix_crew, TASK_LABELS, DEFAULT_AGENT_CONFIG
from docx_export import parse_redaction_json, diagnose_json_error, build_docx

st.set_page_config(page_title="Analyse de compte-rendu — CrewAI", page_icon="🧩", layout="wide")

st.title("🧩 Analyse multi-agents d'un compte-rendu de réunion")
st.caption("Prototype CrewAI + Streamlit — chaque agent analyse un point précis du transcript.")

# --- Sidebar : configuration du LLM (Ollama) ---
with st.sidebar:
    st.header("⚙️ Configuration LLM (Ollama)")
    base_url = st.text_input("URL du serveur Ollama", value="http://localhost:11434")
    model_name = st.text_input("Modèle Ollama", value="gemma4:e4b", help="ex: gemma2:9b, qwen2.5:14b, llama3.1:8b...")
    st.markdown("---")

    # --- Configuration des agents ---
    st.header("🤖 Configuration des agents")
    st.caption("Activez/désactivez les agents individuels selon vos besoins")

    # Initialize agent config in session state if not present
    if "agent_config" not in st.session_state:
        st.session_state.agent_config = DEFAULT_AGENT_CONFIG.copy()

    # Create agent configuration UI
    agent_config = st.session_state.agent_config.copy()

    #col1, col2 = st.columns(2)
    #with col1:
    agent_config["participants"] = st.checkbox("👥 Participants", value=True, help="Cet agent récupère la liste des participants dont le nom apparaît dans le transcript.")
    agent_config["objectif"] = st.checkbox("🎯 Objectif", value=True, help="Cet agent récupère l'objectif de la réunion mentionnée dans le transcript.")
    agent_config["points_cles"] = st.checkbox("🔑 Points clés",value=True, help="Cet agent récupère les points clés abordés dans la réunion.")
    #with col2:
    agent_config["decisions"] = st.checkbox("✅ Décisions", value=True, help="Cet agent récupère les décisions prises au terme de la réunion.")
    agent_config["actions"] = st.checkbox("📋 Actions", value=True, help="Cet agent récupère les actions à mener décidées lors de la réunion.")
    agent_config["risques"] = st.checkbox("⚠️ Risques", value=True, help="Cet agent récupère une liste des risques mentionnées lors de la réunion.")

    agent_config["redacteur"] = st.checkbox("📝 Rédacteur (JSON)", value=True, help="Cet agent s'occupe de la rédaction du compte-rendu final.", disabled=True)

    # Update session state if config changed
    if agent_config != st.session_state.agent_config:
        st.session_state.agent_config = agent_config



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

st.subheader("2. Lancer l'analyse")

run = st.button("🚀 Lancer les agents", type="primary", disabled=not transcript.strip())

# Clés internes alignées avec l'ordre des 6 premiers agents d'analyse
ANALYSIS_KEYS = ["participants", "objectif", "points_cles", "decisions", "actions", "risques"]

if "results" not in st.session_state:
    st.session_state.results = None
if "analyses" not in st.session_state:
    st.session_state.analyses = None
if "redaction_raw" not in st.session_state:
    st.session_state.redaction_raw = None
if "docx_data" not in st.session_state:
    st.session_state.docx_data = None
if "docx_error" not in st.session_state:
    st.session_state.docx_error = None


def try_build_docx_from_raw(raw_json_text: str):
    """Tente de parser un JSON et de générer le docx. Met à jour le session_state."""
    try:
        structured = parse_redaction_json(raw_json_text)
        st.session_state.docx_data = build_docx(structured).getvalue()
        st.session_state.docx_error = None
        return True
    except Exception as parse_err:
        st.session_state.docx_data = None
        st.session_state.docx_error = str(parse_err)
        return False


if run:
    with st.spinner("Les agents analysent le transcript... (peut prendre 1-2 minutes selon le modèle)"):
        try:
            crew = build_crew(transcript=transcript, model_name=model_name, base_url=base_url, agent_config=st.session_state.agent_config)
            crew_output = crew.kickoff()

            # Generate dynamic task labels based on active agents
            active_labels = []
            if st.session_state.agent_config["participants"]:
                active_labels.append("👥 Participants")
            if st.session_state.agent_config["objectif"]:
                active_labels.append("🎯 Objectif de la réunion")
            if st.session_state.agent_config["points_cles"]:
                active_labels.append("🔑 Points clés abordés")
            if st.session_state.agent_config["decisions"]:
                active_labels.append("✅ Décisions prises")
            if st.session_state.agent_config["actions"]:
                active_labels.append("📋 Actions à faire")
            if st.session_state.agent_config["risques"]:
                active_labels.append("⚠️ Points de blocage")
            if st.session_state.agent_config["redacteur"]:
                active_labels.append("📝 Compte-rendu formaté (JSON)")

            # crew_output.tasks_output est une liste alignée avec l'ordre des tasks
            results = []
            for label, task_output in zip(active_labels, crew_output.tasks_output):
                results.append((label, task_output.raw))
            st.session_state.results = results

            # Build analyses dict for retry functionality (only for active analysis agents)
            analysis_results = {}
            analysis_keys = []
            task_idx = 0

            if st.session_state.agent_config["participants"]:
                analysis_keys.append("participants")
                if task_idx < len(crew_output.tasks_output):
                    analysis_results["participants"] = crew_output.tasks_output[task_idx].raw
                    task_idx += 1

            if st.session_state.agent_config["objectif"]:
                analysis_keys.append("objectif")
                if task_idx < len(crew_output.tasks_output):
                    analysis_results["objectif"] = crew_output.tasks_output[task_idx].raw
                    task_idx += 1

            if st.session_state.agent_config["points_cles"]:
                analysis_keys.append("points_cles")
                if task_idx < len(crew_output.tasks_output):
                    analysis_results["points_cles"] = crew_output.tasks_output[task_idx].raw
                    task_idx += 1

            if st.session_state.agent_config["decisions"]:
                analysis_keys.append("decisions")
                if task_idx < len(crew_output.tasks_output):
                    analysis_results["decisions"] = crew_output.tasks_output[task_idx].raw
                    task_idx += 1

            if st.session_state.agent_config["actions"]:
                analysis_keys.append("actions")
                if task_idx < len(crew_output.tasks_output):
                    analysis_results["actions"] = crew_output.tasks_output[task_idx].raw
                    task_idx += 1

            if st.session_state.agent_config["risques"]:
                analysis_keys.append("risques")
                if task_idx < len(crew_output.tasks_output):
                    analysis_results["risques"] = crew_output.tasks_output[task_idx].raw
                    task_idx += 1

            st.session_state.analyses = analysis_results

            # Le dernier task_output est le JSON produit par l'agent rédacteur (s'il est activé)
            redaction_raw = ""
            if st.session_state.agent_config["redacteur"] and len(crew_output.tasks_output) > 0:
                redaction_raw = crew_output.tasks_output[-1].raw
            st.session_state.redaction_raw = redaction_raw
            try_build_docx_from_raw(redaction_raw)
        except Exception as e:
            st.error(f"Erreur lors de l'exécution de la crew : {e}")
            st.session_state.results = None
            st.session_state.docx_data = None

st.subheader("3. Résultats par agent")

if st.session_state.results:
    tabs = st.tabs([label for label, _ in st.session_state.results])
    for tab, (label, content) in zip(tabs, st.session_state.results):
        with tab:
            st.markdown(content)

    with st.expander("📄 Voir tout le résultat en un seul bloc (pour copier/coller)"):
        full_text = "\n\n".join(f"## {label}\n{content}" for label, content in st.session_state.results)
        st.text_area("Résultat complet", value=full_text, height=400)

    st.subheader("4. Export Word")
    if st.session_state.docx_data:
        st.download_button(
            "⬇️ Télécharger le compte-rendu (.docx)",
            data=st.session_state.docx_data,
            file_name="compte_rendu.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    if st.session_state.docx_error:
        st.warning(
            "L'agent rédacteur n'a pas renvoyé un JSON exploitable, impossible "
            f"de générer le .docx automatiquement. Détail : {st.session_state.docx_error}"
        )

        detailed_report = diagnose_json_error(st.session_state.redaction_raw or "")
        if detailed_report:
            with st.expander("🔍 Diagnostic détaillé (ligne / colonne / contexte)"):
                st.code(detailed_report, language="text")

        col_retry, col_autofix, col_fix = st.columns(3)

        # --- Option A : relancer uniquement l'agent rédacteur ---
        with col_retry:
            st.markdown("**Option A — Relancer le rédacteur**")
            st.caption("Réutilise les 5 analyses déjà produites, sans re-router tout le transcript.")
            if st.button("🔄 Relancer l'agent rédacteur"):
                with st.spinner("Nouvelle tentative de mise en forme JSON..."):
                    try:
                        retry_crew = build_redaction_retry_crew(
                            analyses=st.session_state.analyses,
                            model_name=model_name,
                            base_url=base_url,
                        )
                        retry_output = retry_crew.kickoff()
                        new_raw = retry_output.tasks_output[-1].raw
                        st.session_state.redaction_raw = new_raw
                        if try_build_docx_from_raw(new_raw):
                            st.rerun()
                    except Exception as retry_err:
                        st.error(f"Échec de la relance : {retry_err}")

        # --- Option B : agent correcteur, ciblé sur l'erreur exacte ---
        with col_autofix:
            st.markdown("**Option B — Agent correcteur**")
            st.caption("Un agent lit le message d'erreur exact (ligne/colonne) et corrige juste ce point.")
            if st.button("🩹 Corriger automatiquement le JSON"):
                error_report = diagnose_json_error(st.session_state.redaction_raw or "")
                if error_report is None:
                    # Le JSON est en fait valide (ex: erreur venait d'ailleurs) — on regénère direct
                    try_build_docx_from_raw(st.session_state.redaction_raw)
                    st.rerun()
                else:
                    with st.spinner("L'agent correcteur localise et corrige l'erreur..."):
                        try:
                            fix_crew = build_json_fix_crew(
                                broken_json=st.session_state.redaction_raw,
                                error_report=error_report,
                                model_name=model_name,
                                base_url=base_url,
                            )
                            fix_output = fix_crew.kickoff()
                            fixed_raw = fix_output.tasks_output[-1].raw
                            st.session_state.redaction_raw = fixed_raw
                            if try_build_docx_from_raw(fixed_raw):
                                st.rerun()
                        except Exception as fix_err:
                            st.error(f"Échec de la correction automatique : {fix_err}")

        # --- Option C : corriger le JSON à la main ---
        with col_fix:
            st.markdown("**Option C — Corriger à la main**")
            st.caption("Édite la sortie brute puis régénère le .docx à partir de ta version corrigée.")

        edited_json = st.text_area(
            "JSON brut renvoyé par l'agent rédacteur (éditable)",
            value=st.session_state.redaction_raw or "",
            height=250,
        )
        if st.button("🛠️ Générer le .docx depuis ce JSON corrigé"):
            if try_build_docx_from_raw(edited_json):
                st.session_state.redaction_raw = edited_json
                st.success("JSON valide — le bouton de téléchargement ci-dessus est à jour.")
                st.rerun()
            else:
                st.error(f"Toujours invalide : {st.session_state.docx_error}")

    if not st.session_state.docx_data and not st.session_state.docx_error:
        st.caption("Tu peux copier le contenu de l'onglet 'Compte-rendu formaté' ci-dessus si besoin.")
else:
    st.info("Collez ou uploadez un transcript, puis cliquez sur 'Lancer les agents'.")