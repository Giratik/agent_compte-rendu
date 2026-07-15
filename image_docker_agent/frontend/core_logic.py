import time
import streamlit as st
import requests
import api_client as api

def execute_analysis(backend_url, transcript, agent_config, model_name, ollama_base_url, verbosity):
    """Lance l'analyse initiale et gère la boucle de vérification des statuts."""
    try:
        job = api.start_analysis(
            backend_url=backend_url,
            transcript=transcript,
            agent_config=agent_config,
            model_name=model_name,
            ollama_base_url=ollama_base_url,
            verbosity=verbosity,
        )
    except requests.RequestException as e:
        st.error(f"Impossible de démarrer l'analyse : {e}")
        return False

    if not job:
        return False

    job_id = job["job_id"]
    status_box = st.status("Lancement des agents...", expanded=True)
    seen_done = set()

    while True:
        try:
            job = api.poll_job(backend_url, job_id)
        except requests.RequestException as e:
            status_box.update(label="Erreur de communication avec le backend ❌", state="error")
            st.error(f"Erreur pendant le suivi du job : {e}")
            return False

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
            return True

        if job["status"] == "error":
            status_box.update(label="Erreur pendant l'analyse ❌", state="error")
            st.error(f"Erreur lors de l'exécution de la crew : {job['error']}")
            st.session_state.results = None
            return False

        time.sleep(1.2)


def apply_global_modifications(backend_url, model_name, ollama_base_url, verbosity, global_instructions):
    """Applique les modifications globales à l'ensemble des sections."""
    try:
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
            
            # Tentative d'auto-correction silencieuse
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
        return True

    except requests.RequestException as e:
        st.error(f"Échec de la modification : {e}")
        return False