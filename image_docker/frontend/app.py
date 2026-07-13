import os
import time

import streamlit as st
import requests

import api_client as api

BACKEND_URL_DEFAULT = os.environ.get("BACKEND_URL", "http://backend:8000")
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://10.75.12.5:11434" )
st.set_page_config(page_title="Analyse de compte-rendu — CrewAI", page_icon="🧩", layout="wide")

st.title("🧩 Analyse multi-agents d'un compte-rendu de réunion")
st.caption("Frontend Streamlit — parle au backend FastAPI en HTTP, aucune logique CrewAI ici.")

# --- Sidebar : backend + LLM + agents ---
with st.sidebar:
    st.header("🔌 Backend")
    backend_url = st.text_input("URL du backend FastAPI", value=BACKEND_URL_DEFAULT).rstrip("/")

    st.header("⚙️ Configuration LLM (Ollama)")
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

    if st.session_state.agents_meta:
        agent_order = st.session_state.agents_meta["agent_order"]
        agent_meta = st.session_state.agents_meta["agent_meta"]

        if "agent_config" not in st.session_state:
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
        agent_order = []
        st.stop()


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

no_agent_active = not any(st.session_state.agent_config.get(k, True) for k in agent_order)
run = st.button("🚀 Lancer les agents", type="primary", disabled=not transcript.strip() or no_agent_active)

for key in ["results", "analyses", "redaction_raw", "docx_ok", "docx_error"]:
    if key not in st.session_state:
        st.session_state[key] = None


if run:
    try:
        job = api.start_analysis(
            backend_url=backend_url,
            transcript=transcript,
            agent_config=st.session_state.agent_config,
            model_name=model_name,
            ollama_base_url=ollama_base_url,
            verbosity=verbosity,
        )
    except requests.RequestException as e:
        st.error(f"Impossible de démarrer l'analyse : {e}")
        job = None

    if job:
        job_id = job["job_id"]
        status_box = st.status("Lancement des agents...", expanded=True)
        seen_done = set()

        while True:
            try:
                job = api.poll_job(backend_url, job_id)
            except requests.RequestException as e:
                status_box.update(label="Erreur de communication avec le backend ❌", state="error")
                st.error(f"Erreur pendant le suivi du job : {e}")
                break

            for step in job["steps"]:
                if step["status"] == "done" and step["key"] not in seen_done:
                    seen_done.add(step["key"])
                    status_box.write(f"✅ {step['label']} — terminé ({len(seen_done)}/{job['total_steps']})")
                    status_box.update(label=f"Analyse en cours... ({len(seen_done)}/{job['total_steps']})")

            if job["status"] == "done":
                status_box.update(
                    label=f"Analyse terminée ({job['total_steps']}/{job['total_steps']}) ✅",
                    state="complete",
                    expanded=False,
                )
                st.session_state.results = job["results"]
                st.session_state.analyses = job["analyses"]
                st.session_state.redaction_raw = job["redaction_raw"]
                st.session_state.docx_ok = job["docx_ok"]
                st.session_state.docx_error = job["docx_error"]

                if job["redaction_raw"] and job["docx_ok"]:
                    st.success("✅ JSON valide — le .docx est prêt à être téléchargé.")
                elif job["redaction_raw"] and not job["docx_ok"]:
                    st.warning(
                        "⚠️ Le JSON du rédacteur reste invalide même après réparation "
                        f"automatique côté backend. Détail : {job['docx_error']}"
                    )
                break

            if job["status"] == "error":
                status_box.update(label="Erreur pendant l'analyse ❌", state="error")
                st.error(f"Erreur lors de l'exécution de la crew : {job['error']}")
                st.session_state.results = None
                break

            time.sleep(1.2)

st.subheader("3. Résultats par agent")

if st.session_state.results:
    tabs = st.tabs([r["label"] for r in st.session_state.results])
    for tab, r in zip(tabs, st.session_state.results):
        key, label, content = r["key"], r["label"], r["content"]
        with tab:
            st.markdown(content)

            if key != "redacteur":
                st.divider()
                instructions = st.text_area(
                    "Instructions de modification pour l'IA",
                    placeholder="Ex: rends le texte plus formel, ajoute ce détail oublié, sois plus concis...",
                    key=f"inst_{key}",
                )
                if st.button("Appliquer la modification", key=f"btn_{key}"):
                    if not instructions.strip():
                        st.warning("Décris la modification souhaitée avant de valider.")
                    else:
                        try:
                            with st.spinner(f"L'agent réviseur retravaille '{label}'..."):
                                new_content = api.revise_section(
                                    backend_url=backend_url,
                                    section_name=label,
                                    current_text=content,
                                    instructions=instructions,
                                    model_name=model_name,
                                    ollama_base_url=ollama_base_url,
                                )
                                st.session_state.results = [
                                    {**rr, "content": new_content} if rr["key"] == key else rr
                                    for rr in st.session_state.results
                                ]
                                if st.session_state.analyses and key in st.session_state.analyses:
                                    st.session_state.analyses[key] = new_content

                            # Resynchronise automatiquement le rédacteur avec la section modifiée
                            if st.session_state.agent_config.get("redacteur", True) and st.session_state.analyses:
                                with st.spinner("🔄 Synchronisation du compte-rendu JSON..."):
                                    redaction = api.redaction_retry(
                                        backend_url=backend_url,
                                        analyses=st.session_state.analyses,
                                        model_name=model_name,
                                        ollama_base_url=ollama_base_url,
                                        verbosity=verbosity,
                                    )
                                    st.session_state.redaction_raw = redaction["raw_json"]
                                    st.session_state.docx_ok = redaction["docx_ok"]
                                    st.session_state.docx_error = redaction["docx_error"]
                                    st.session_state.results = [
                                        {**rr, "content": redaction["raw_json"]} if rr["key"] == "redacteur" else rr
                                        for rr in st.session_state.results
                                    ]

                            st.success("Modification intégrée au compte-rendu.")
                            st.rerun()
                        except requests.RequestException as e:
                            st.error(f"Échec de la modification : {e}")

    st.subheader("4. Export Word")
    if not st.session_state.agent_config.get("redacteur", True):
        st.info("L'agent rédacteur est désactivé : l'export Word n'est pas disponible.")
    elif st.session_state.docx_ok:
        col_dl, col_expand = st.columns([2, 1])
        with col_dl:
            try:
                docx_bytes = api.docx_build(backend_url, st.session_state.redaction_raw)
                st.download_button(
                    "⬇️ Télécharger le compte-rendu (.docx)",
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
                        st.session_state.redaction_raw = redaction["raw_json"]
                        st.session_state.docx_ok = redaction["docx_ok"]
                        st.session_state.docx_error = redaction["docx_error"]
                        st.rerun()
                    except requests.RequestException as e:
                        st.error(f"Échec de la relance détaillée : {e}")

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

        col_retry, col_autofix, col_fix = st.columns(3)

        with col_retry:
            st.markdown("**Option A — Relancer le rédacteur**")
            if st.button("🔄 Relancer l'agent rédacteur"):
                with st.spinner("Nouvelle tentative de mise en forme JSON..."):
                    try:
                        redaction = api.redaction_retry(
                            backend_url, st.session_state.analyses, model_name, ollama_base_url, verbosity
                        )
                        st.session_state.redaction_raw = redaction["raw_json"]
                        st.session_state.docx_ok = redaction["docx_ok"]
                        st.session_state.docx_error = redaction["docx_error"]
                        st.rerun()
                    except requests.RequestException as e:
                        st.error(f"Échec de la relance : {e}")

        with col_autofix:
            st.markdown("**Option B — Agent correcteur**")
            if st.button("🩹 Corriger automatiquement le JSON"):
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

        with col_fix:
            st.markdown("**Option C — Corriger à la main**")

        edited_json = st.text_area(
            "JSON brut renvoyé par l'agent rédacteur (éditable)",
            value=st.session_state.redaction_raw or "",
            height=250,
        )
        if st.button("🛠️ Générer le .docx depuis ce JSON corrigé"):
            try:
                diag = api.docx_diagnose(backend_url, edited_json)
                if diag["valid"]:
                    st.session_state.redaction_raw = edited_json
                    st.session_state.docx_ok = True
                    st.session_state.docx_error = None
                    st.success("JSON valide — le bouton de téléchargement ci-dessus est à jour.")
                    st.rerun()
                else:
                    st.session_state.docx_error = diag["error_report"]
                    st.error(f"Toujours invalide : {diag['error_report']}")
            except requests.RequestException as e:
                st.error(f"Échec de la vérification : {e}")
else:
    st.info("Collez ou uploadez un transcript, puis cliquez sur 'Lancer les agents'.")