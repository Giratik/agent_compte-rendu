import streamlit as st

from agents import build_crew, build_redaction_retry_crew, build_json_fix_crew, TASK_LABELS, DEFAULT_AGENT_CONFIG, AGENT_ORDER, build_revision_crew
from docx_export import parse_redaction_json, diagnose_json_error, build_docx

st.set_page_config(page_title="Analyse de compte-rendu — CrewAI", page_icon="🧩", layout="wide")

st.title("🧩 Analyse multi-agents d'un compte-rendu de réunion")
st.caption("Prototype CrewAI + Streamlit — chaque agent analyse un point précis du transcript.")

# --- Sidebar : configuration du LLM (Ollama) ---
with st.sidebar:
    st.header("⚙️ Configuration LLM (Ollama)")
    base_url = st.text_input("URL du serveur Ollama", value="http://localhost:11434")
    model_name = st.text_input("Modèle Ollama", value="gemma4:e4b", help="ex: gemma2:9b, qwen2.5:14b, llama3.1:8b...")


    verbosity ="concis"

    st.markdown("---")

    # --- Configuration des agents ---
    st.header("🤖 Configuration des agents")
    st.caption("Chaque agent ci-dessous correspond à une partie du compte-rendu qui sera rédigé. Activez/désactivez les selon vos besoins.")

    # Initialize agent config in session state if not present
    if "agent_config" not in st.session_state:
        st.session_state.agent_config = DEFAULT_AGENT_CONFIG.copy()

    # Create agent configuration UI
    agent_config = st.session_state.agent_config.copy()

    #col1, col2 = st.columns(2)
    #with col1:
    agent_config["participants"] = st.checkbox("👥 Participants", value=st.session_state.agent_config.get("participants", True), help="Cet agent récupère la liste des participants dont le nom apparaît dans le transcript.")
    agent_config["objectif"] = st.checkbox("🎯 Objectif", value=st.session_state.agent_config.get("objectif", True), help="Cet agent récupère l'objectif de la réunion mentionnée dans le transcript.")
    agent_config["points_cles"] = st.checkbox("🔑 Points clés", value=st.session_state.agent_config.get("points_cles", True), help="Cet agent récupère les points clés abordés dans la réunion.")
    agent_config["outils_chiffres"] = st.checkbox("🛠️ Outils & chiffres", value=st.session_state.agent_config.get("outils_chiffres", True), help="Cet agent relève les outils/technologies cités et les chiffres clés mentionnés.")
    #with col2:
    agent_config["decisions"] = st.checkbox("✅ Décisions", value=st.session_state.agent_config.get("decisions", True), help="Cet agent récupère les décisions prises au terme de la réunion.")
    agent_config["actions"] = st.checkbox("📋 Actions", value=st.session_state.agent_config.get("actions", True), help="Cet agent récupère les actions à mener décidées lors de la réunion.")
    agent_config["risques"] = st.checkbox("⚠️ Risques", value=st.session_state.agent_config.get("risques", True), help="Cet agent récupère une liste des risques mentionnées lors de la réunion.")

    agent_config["redacteur"] = st.checkbox("📝 Rédacteur (JSON)", value=True, help="Cet agent s'occupe de la rédaction du compte-rendu final.", disabled=True)

    if not any(agent_config[k] for k in AGENT_ORDER):
        st.warning("Active au moins un agent d'analyse pour pouvoir lancer une analyse.")

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

no_agent_active = not any(st.session_state.agent_config.get(k, True) for k in AGENT_ORDER)
run = st.button("🚀 Lancer les agents", type="primary", disabled=not transcript.strip() or no_agent_active)

# Clés internes alignées avec l'ordre des 7 agents d'analyse
ANALYSIS_KEYS = ["participants", "objectif", "points_cles", "outils_chiffres", "decisions", "actions", "risques"]

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
    cfg = st.session_state.agent_config
    total_steps = sum(1 for k in AGENT_ORDER if cfg[k]) + (1 if cfg["redacteur"] else 0)

    # --- Suivi d'avancement agent par agent ---
    # CrewAI appelle task.callback dès qu'une Task se termine. Comme
    # Process.sequential exécute les tasks une par une dans le même thread,
    # ce callback est synchrone : on peut mettre à jour l'UI Streamlit
    # pendant crew.kickoff(), sans thread ni polling.
    status_box = st.status("Lancement des agents...", expanded=True)
    progress = {"count": 0}

    def on_task_complete(key, output):
        progress["count"] += 1
        label = TASK_LABELS.get(key, key)
        status_box.write(f"✅ {label} — terminé ({progress['count']}/{total_steps})")
        status_box.update(label=f"Analyse en cours... ({progress['count']}/{total_steps})")

    try:
        crew = build_crew(
            transcript=transcript,
            model_name=model_name,
            base_url=base_url,
            agent_config=cfg,
            on_task_complete=on_task_complete,
        )
        crew_output = crew.kickoff()
        status_box.update(
            label=f"Analyse terminée ({total_steps}/{total_steps}) ✅", state="complete", expanded=False
        )

            # Generate dynamic task labels based on active agents
        active_items = []
        if st.session_state.agent_config["participants"]: active_items.append(("participants", "👥 Participants"))
        if st.session_state.agent_config["objectif"]: active_items.append(("objectif", "🎯 Objectif de la réunion"))
        if st.session_state.agent_config["points_cles"]: active_items.append(("points_cles", "🔑 Points clés abordés"))
        if st.session_state.agent_config["outils_chiffres"]: active_items.append(("outils_chiffres", "🛠️ Outils & chiffres"))
        if st.session_state.agent_config["decisions"]: active_items.append(("decisions", "✅ Décisions prises"))
        if st.session_state.agent_config["actions"]: active_items.append(("actions", "📋 Actions à faire"))
        if st.session_state.agent_config["risques"]: active_items.append(("risques", "⚠️ Points de blocage"))
        if st.session_state.agent_config["redacteur"]: active_items.append(("redacteur", "📝 Compte-rendu formaté (JSON)"))

        results = []
        for (key, label), task_output in zip(active_items, crew_output.tasks_output):
            results.append((key, label, task_output.raw))
        st.session_state.results = results

        # Build analyses dict for retry functionality (only for active analysis agents)
        analysis_results = {}
        task_idx = 0

        if st.session_state.agent_config["participants"]:
            if task_idx < len(crew_output.tasks_output):
                analysis_results["participants"] = crew_output.tasks_output[task_idx].raw
                task_idx += 1

        if st.session_state.agent_config["objectif"]:
            if task_idx < len(crew_output.tasks_output):
                analysis_results["objectif"] = crew_output.tasks_output[task_idx].raw
                task_idx += 1

        if st.session_state.agent_config["points_cles"]:
            if task_idx < len(crew_output.tasks_output):
                analysis_results["points_cles"] = crew_output.tasks_output[task_idx].raw
                task_idx += 1

        if st.session_state.agent_config["outils_chiffres"]:
            if task_idx < len(crew_output.tasks_output):
                analysis_results["outils_chiffres"] = crew_output.tasks_output[task_idx].raw
                task_idx += 1

        if st.session_state.agent_config["decisions"]:
            if task_idx < len(crew_output.tasks_output):
                analysis_results["decisions"] = crew_output.tasks_output[task_idx].raw
                task_idx += 1

        if st.session_state.agent_config["actions"]:
            if task_idx < len(crew_output.tasks_output):
                analysis_results["actions"] = crew_output.tasks_output[task_idx].raw
                task_idx += 1

        if st.session_state.agent_config["risques"]:
            if task_idx < len(crew_output.tasks_output):
                analysis_results["risques"] = crew_output.tasks_output[task_idx].raw
                task_idx += 1

        st.session_state.analyses = analysis_results

        # Le dernier task_output est le JSON produit par l'agent rédacteur (s'il est activé)
        redaction_raw = ""
        if st.session_state.agent_config["redacteur"] and len(crew_output.tasks_output) > 0:
            redaction_raw = crew_output.tasks_output[-1].raw
        st.session_state.redaction_raw = redaction_raw
        docx_ok = try_build_docx_from_raw(redaction_raw)

        # --- Réparation automatique si le JSON du rédacteur est invalide ---
        if st.session_state.agent_config["redacteur"] and not docx_ok:
            st.warning(
                "⚠️ L'agent rédacteur a renvoyé un JSON invalide "
                f"(détail : {st.session_state.docx_error}). Lancement de la réparation automatique..."
            )

            MAX_AUTO_FIX_ATTEMPTS = 2
            attempt = 0
            with st.spinner("🩹 Réparation automatique du JSON en cours..."):
                while not docx_ok and attempt < MAX_AUTO_FIX_ATTEMPTS:
                    attempt += 1
                    error_report = diagnose_json_error(st.session_state.redaction_raw or "")
                    if error_report is None:
                        # Le JSON est en fait valide (edge case) — on retente juste le parsing
                        docx_ok = try_build_docx_from_raw(st.session_state.redaction_raw)
                        break
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
                        docx_ok = try_build_docx_from_raw(fixed_raw)
                    except Exception as fix_err:
                        st.session_state.docx_error = f"Échec de la réparation automatique : {fix_err}"
                        break

            if docx_ok:
                st.success(f"✅ JSON réparé automatiquement en {attempt} tentative(s) — le .docx est prêt.")
            else:
                st.error(
                    "La réparation automatique n'a pas suffi "
                    f"(après {attempt} tentative(s)). Utilise les options ci-dessous "
                    "pour finaliser l'export."
                )
    except Exception as e:
        status_box.update(label="Erreur pendant l'analyse ❌", state="error")
        st.error(f"Erreur lors de l'exécution de la crew : {e}")
        st.session_state.results = None
        st.session_state.docx_data = None

st.subheader("3. Résultats par agent")

if st.session_state.results:
    # On récupère uniquement le label pour les titres des onglets
    tabs = st.tabs([label for _, label, _ in st.session_state.results])
    
    # On itère avec l'index pour pouvoir mettre à jour le session_state
    for i, (tab, (key, label, content)) in enumerate(zip(tabs, st.session_state.results)):
        with tab:
            # Affichage du contenu généré
            st.markdown(content)
            
            # On ne permet pas de modifier directement la sortie JSON brute du rédacteur ici
            if key != "redacteur":
                st.divider()
                #with st.expander(f"✨ Demander une modification pour : {label}"):
                instructions = st.text_area(
                    "Instructions de modification pour l'IA", 
                    placeholder="Ex: Rends le texte plus formel, ajoute ce détail oublié, sois plus concis...",
                    key=f"inst_{key}"
                )
                
                if st.button(f"Appliquer la modification", key=f"btn_{key}"):
                    if instructions.strip():
                        try:
                            # ÉTAPE 1 : Lancement de la micro-crew de révision pour l'onglet en cours
                            with st.spinner(f"L'agent réviseur modifie la section '{label}'..."):
                                revision_crew = build_revision_crew(
                                    section_name=label,
                                    current_text=content,
                                    instructions=instructions,
                                    model_name=model_name,
                                    base_url=base_url
                                )
                                revision_output = revision_crew.kickoff()
                                new_content = revision_output.tasks_output[-1].raw
                                
                                # Mise à jour locale de la section modifiée
                                st.session_state.results[i] = (key, label, new_content)
                                st.session_state.analyses[key] = new_content

                            # ÉTAPE 2 : Ré-exécution AUTOMATIQUE du rédacteur pour synchroniser le JSON
                            if st.session_state.agent_config.get("redacteur", True):
                                with st.spinner("🔄 Synchronisation et re-génération du compte-rendu JSON..."):
                                    retry_crew = build_redaction_retry_crew(
                                        analyses=st.session_state.analyses,
                                        model_name=model_name,
                                        base_url=base_url,
                                        verbosity=verbosity  # Utilise la variable définie en haut de ton script
                                    )
                                    retry_output = retry_crew.kickoff()
                                    new_json = retry_output.tasks_output[-1].raw
                                    
                                    # Mise à jour du JSON brut de session et du fichier Word (.docx)
                                    st.session_state.redaction_raw = new_json
                                    try_build_docx_from_raw(new_json)
                                    
                                    # Mise à jour dynamique du texte affiché dans l'onglet "Rédacteur (JSON)"
                                    for idx, (r_key, r_label, _) in enumerate(st.session_state.results):
                                        if r_key == "redacteur":
                                            st.session_state.results[idx] = ("redacteur", r_label, new_json)
                                            break
                            
                            st.success("Modification intégrée avec succès au compte-rendu global !")
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Échec de la modification ou de la mise à jour du JSON : {e}")
                    else:
                        st.warning("Veuillez entrer des instructions avant de modifier.")

    #with st.expander("📄 Voir tout le résultat en un seul bloc (pour copier/coller)"):
    #    full_text = "\n\n".join(f"## {label}\n{content}" for _, label, content in st.session_state.results)
    #    st.text_area("Résultat complet", value=full_text, height=400)

    st.subheader("4. Export Word")
    if not st.session_state.agent_config.get("redacteur", True):
        st.info("L'agent rédacteur est désactivé : l'export Word n'est pas disponible.")
    elif st.session_state.docx_data:
        col_dl, col_expand = st.columns([2, 1])
        with col_dl:
            st.download_button(
                "⬇️ Télécharger le compte-rendu (.docx)",
                data=st.session_state.docx_data,
                file_name="compte_rendu.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        with col_expand:
            st.caption("Rédaction trop synthétique ?")
            if st.button("📝 Refaire en plus détaillé", disabled=not st.session_state.analyses):
                with st.spinner("Nouvelle rédaction, plus étoffée..."):
                    try:
                        detailed_crew = build_redaction_retry_crew(
                            analyses=st.session_state.analyses,
                            model_name=model_name,
                            base_url=base_url,
                            verbosity="detaille",
                        )
                        detailed_output = detailed_crew.kickoff()
                        new_raw = detailed_output.tasks_output[-1].raw
                        st.session_state.redaction_raw = new_raw
                        if try_build_docx_from_raw(new_raw):
                            st.rerun()
                    except Exception as detail_err:
                        st.error(f"Échec de la relance détaillée : {detail_err}")

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
            st.caption("Réutilise les analyses déjà produites, sans re-router tout le transcript.")
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

    if not st.session_state.docx_data and not st.session_state.docx_error and st.session_state.agent_config.get("redacteur", True):
        st.caption("Tu peux copier le contenu de l'onglet 'Compte-rendu formaté' ci-dessus si besoin.")
else:
    st.info("Collez ou uploadez un transcript, puis cliquez sur 'Lancer les agents'.")