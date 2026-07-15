import os
import time
import json
import re
import ast
import streamlit as st
import requests
import api_client as api

BACKEND_URL_DEFAULT = os.environ.get("BACKEND_URL", "http://backend:8000")
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://10.75.12.5:11434")

st.set_page_config(page_title="Analyse de compte-rendu CrewAI", page_icon="📄", layout="wide")
st.title("📄 Analyse multi-agents d'un compte-rendu de réunion")
st.caption("Frontend Streamlit – parle au backend FastAPI en HTTP, aucune logique CrewAI ici.")

# --- Fonction d'aide pour générer la preview finale ---
def render_preview(raw_json: str):
    if not raw_json:
        return
        
    text = raw_json.strip()
    
    # 1. Nettoyage des balises markdown potentielles
    text = re.sub(r"^```(json)?\n?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\n?```$", "", text, flags=re.MULTILINE)
    
    # 2. Isolement du dictionnaire principal
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx + 1]
        
    # 3. Correction des virgules traînantes (trailing commas) - erreur classique des LLM
    text = re.sub(r',\s*([\]}])', r'\1', text)
        
    data = None
    try:
        # strict=False permet d'ignorer certaines erreurs mineures de formatage (ex: sauts de ligne)
        data = json.loads(text, strict=False)
    except json.JSONDecodeError:
        # 4. Fallback : ast.literal_eval pour tolérer les guillemets simples ou clés sans guillemets
        try:
            # Remplacements pour que la syntaxe JSON corresponde à la syntaxe Python
            text_ast = re.sub(r'\btrue\b', 'True', text)
            text_ast = re.sub(r'\bfalse\b', 'False', text_ast)
            text_ast = re.sub(r'\bnull\b', 'None', text_ast)
            data = ast.literal_eval(text_ast)
        except Exception:
            st.error("Impossible d'afficher l'aperçu : le JSON ne peut pas être lu par l'interface.")
            with st.expander("Voir le texte brut reçu (Debug)"):
                st.code(raw_json, language="text")
            return

    if not isinstance(data, dict):
        st.error("L'aperçu n'est pas disponible (les données extraites ne sont pas un dictionnaire valide).")
        return

    st.markdown(f"<h2 style='text-align: center;'>{data.get('titre', 'Compte-rendu')}</h2>", unsafe_allow_html=True)
    if data.get("date"):
        st.markdown(f"<p style='text-align: center; font-style: italic;'>{data['date']}</p>", unsafe_allow_html=True)

    st.markdown("### Participants")
    if data.get("participants"):
        for p in data["participants"]: st.markdown(f"- {p}")
    else:
        st.markdown("Non précisé.")

    if data.get("absents"):
        st.markdown("#### Absents / excusés")
        for a in data["absents"]: st.markdown(f"- {a}")

    st.markdown("### Objectif de la réunion")
    st.markdown(data.get("objectif") or "Non précisé.")

    st.markdown("### Points clés abordés")
    if data.get("points_cles"):
        for pc in data["points_cles"]: st.markdown(f"- {pc}")
    else:
        st.markdown("Non précisé.")

    st.markdown("### Outils & chiffres associés")
    if data.get("outils_et_chiffres"):
        for item in data["outils_et_chiffres"]:
            outil = item.get("outil", "") if isinstance(item, dict) else str(item)
            chiffres = item.get("chiffres_associes", []) if isinstance(item, dict) else []
            st.markdown(f"**{outil}**")
            if chiffres:
                for c in chiffres: st.markdown(f"- {c}")
            else:
                st.markdown("- Aucun chiffre associé.")
    else:
        st.markdown("Aucun outil mentionné.")

    if data.get("autres_chiffres"):
        st.markdown("#### Autres chiffres clés")
        for c in data["autres_chiffres"]: st.markdown(f"- {c}")

    st.markdown("### Décisions prises")
    if data.get("decisions"):
        for d in data["decisions"]: st.markdown(f"- {d}")
    else:
        st.markdown("Aucune décision actée.")

    st.markdown("### Actions à faire")
    if data.get("actions"):
        st.markdown("| Action | Responsable | Échéance |\n|---|---|---|")
        for a in data["actions"]:
            action = str(a.get("action", "")).replace('\n', ' ')
            resp = str(a.get("responsable", "") or "Non précisé").replace('\n', ' ')
            ech = str(a.get("echeance", "") or "Non précisée").replace('\n', ' ')
            st.markdown(f"| {action} | {resp} | {ech} |")
    else:
        st.markdown("Aucune action identifiée.")

    st.markdown("### Points de blocage / questions ouvertes")
    if data.get("points_de_blocage"):
        for pt in data["points_de_blocage"]: st.markdown(f"- {pt}")
    else:
        st.markdown("Aucun point de blocage identifié.")

# --- Sidebar : backend + LLM + agents ---
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
                    status_box.write(f"✅ {step['label']} a terminé ({len(seen_done)}/{job['total_steps']})")
                    status_box.update(label=f"Analyse en cours... ({len(seen_done)}/{job['total_steps']})")

            if job["status"] == "done":
                # Vérification du format JSON dès la première génération
                current_raw = job["redaction_raw"]
                current_ok = job["docx_ok"]
                current_error = job["docx_error"]

                if current_raw and not current_ok:
                    status_box.write("🛠️ Format JSON invalide détecté, l'agent correcteur tente de réparer le document...")
                    try:
                        fixed = api.redaction_fix(
                            backend_url,
                            current_raw,
                            model_name,
                            ollama_base_url
                        )
                        current_raw = fixed["raw_json"]
                        current_ok = fixed["docx_ok"]
                        current_error = fixed["docx_error"]
                    except requests.RequestException:
                        pass # On conserve l'erreur originale si la correction échoue

                # Mise à jour des états avec la version (potentiellement) corrigée
                st.session_state.analyses = job["analyses"]
                st.session_state.redaction_raw = current_raw
                st.session_state.docx_ok = current_ok
                st.session_state.docx_error = current_error
                
                # Mise à jour des résultats avec le JSON final
                st.session_state.results = [
                    {**rr, "content": current_raw} if rr["key"] == "redacteur" else rr
                    for rr in job["results"]
                ]

                if current_raw and current_ok:
                    status_box.update(
                        label=f"Analyse terminée ({job['total_steps']}/{job['total_steps']}) 🎉",
                        state="complete",
                        expanded=False,
                    )
                    st.success("✅ JSON valide : le .docx est prêt à être téléchargé.")
                else:
                    status_box.update(
                        label=f"Analyse terminée avec des erreurs de formatage ({job['total_steps']}/{job['total_steps']})",
                        state="error",
                        expanded=False,
                    )
                    st.warning(
                        "⚠️ Le JSON du rédacteur reste invalide même après réparation "
                        f"automatique côté backend. Détail : {current_error}"
                    )
                break

            if job["status"] == "error":
                status_box.update(label="Erreur pendant l'analyse ❌", state="error")
                st.error(f"Erreur lors de l'exécution de la crew : {job['error']}")
                st.session_state.results = None
                break

            time.sleep(1.2)


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
            try:
                # On isole les résultats intermédiaires modifiables (tout sauf le rédacteur final)
                editable_results = [r for r in st.session_state.results if r["key"] != "redacteur"]
                
                progress_text = "Transmission de vos instructions aux agents..."
                my_bar = st.progress(0, text=progress_text)

                new_results_dict = {}
                
                # On itère sur chaque section pour lui appliquer la même instruction globale
                for i, r in enumerate(editable_results):
                    key, label, content = r["key"], r["label"], r["content"]
                    my_bar.progress((i) / len(editable_results), text=f"L'agent révise la section '{label}'...")
                    
                    new_content = api.revise_section(
                        backend_url=backend_url,
                        section_name=label,
                        current_text=content,
                        instructions=global_instructions,
                        model_name=model_name,
                        ollama_base_url=ollama_base_url,
                    )
                    new_results_dict[key] = new_content

                # Mise à jour de l'état de la session
                st.session_state.results = [
                    {**rr, "content": new_results_dict.get(rr["key"], rr["content"])}
                    for rr in st.session_state.results
                ]
                for k, v in new_results_dict.items():
                    if st.session_state.analyses and k in st.session_state.analyses:
                        st.session_state.analyses[k] = v

                # Resynchronise automatiquement le rédacteur final avec l'ensemble des analyses corrigées
                if st.session_state.agent_config.get("redacteur", True) and st.session_state.analyses:
                    my_bar.progress(0.85, text="🔄 Consolidation du compte-rendu final en cours...")
                    redaction = api.redaction_retry(
                        backend_url=backend_url,
                        analyses=st.session_state.analyses,
                        model_name=model_name,
                        ollama_base_url=ollama_base_url,
                        verbosity=verbosity,
                    )
                    
                    # --- NOUVEAU : Tentative d'auto-correction silencieuse ---
                    if not redaction["docx_ok"]:
                        my_bar.progress(0.95, text="🛠️ Format JSON invalide, l'agent correcteur répare le document...")
                        try:
                            fixed = api.redaction_fix(
                                backend_url,
                                redaction["raw_json"],
                                model_name,
                                ollama_base_url
                            )
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

                    st.session_state.results = [
                        {**rr, "content": st.session_state.redaction_raw} if rr["key"] == "redacteur" else rr
                        for rr in st.session_state.results
                    ]

                my_bar.empty()
                st.success("Modifications globales intégrées au compte-rendu avec succès.")
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
                        
                        # --- Auto-correction ajoutée pour le bouton de détail ---
                        if not redaction["docx_ok"]:
                            st.toast("🛠️ Format JSON invalide, l'agent correcteur tente de réparer...")
                            try:
                                fixed = api.redaction_fix(
                                    backend_url,
                                    redaction["raw_json"],
                                    model_name,
                                    ollama_base_url
                                )
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

    # Section d'erreur épurée
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