import time
import streamlit as st
import requests
import api_client as api
from utility.session_state_central_cr import SK, get, set as ss_set

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
            ss_set(SK.ANALYSE, job["analyses"])
            ss_set(SK.REDACTION_RAW, current_raw)
            ss_set(SK.DOCX_OK, current_ok)
            ss_set(SK.DOCX_ERROR, current_error)

            # Mise à jour des résultats avec le JSON final
            ss_set(SK.RESULTS, [
                {**rr, "content": current_raw} if rr["key"] == "redacteur" else rr
                for rr in job["results"]
            ])

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
            ss_set(SK.RESULTS, None)
            return False

        time.sleep(1.2)


def apply_global_modifications(backend_url, model_name, ollama_base_url, verbosity, global_instructions):
    """Applique les modifications globales à l'ensemble des sections."""
    try:
        editable_results = [r for r in get(SK.RESULTS) if r["key"] != "redacteur"]

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
        ss_set(SK.RESULTS, [
            {**rr, "content": new_results_dict.get(rr["key"], rr["content"])}
            for rr in get(SK.RESULTS)
        ])
        for k, v in new_results_dict.items():
            if get(SK.ANALYSE) and k in get(SK.ANALYSE):
                ss_set(SK.ANALYSE, {**get(SK.ANALYSE), k: v})

        # Resynchronise automatiquement le rédacteur final avec l'ensemble des analyses corrigées
        if get(SK.AGENT_CONFIG).get("redacteur", True) and get(SK.ANALYSE):
            my_bar.progress(0.85, text="🔄 Consolidation du compte-rendu final en cours...")
            redaction = api.redaction_retry(
                backend_url=backend_url,
                analyses=get(SK.ANALYSE),
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
                    ss_set(SK.REDACTION_RAW, fixed["raw_json"])
                    ss_set(SK.DOCX_OK, fixed["docx_ok"])
                    ss_set(SK.DOCX_ERROR, fixed["docx_error"])
                except requests.RequestException:
                    ss_set(SK.REDACTION_RAW, redaction["raw_json"])
                    ss_set(SK.DOCX_OK, redaction["docx_ok"])
                    ss_set(SK.DOCX_ERROR, redaction["docx_error"])
            else:
                ss_set(SK.REDACTION_RAW, redaction["raw_json"])
                ss_set(SK.DOCX_OK, redaction["docx_ok"])
                ss_set(SK.DOCX_ERROR, redaction["docx_error"])

            ss_set(SK.RESULTS, [
                {**rr, "content": get(SK.REDACTION_RAW)} if rr["key"] == "redacteur" else rr
                for rr in get(SK.RESULTS)
            ])

        my_bar.empty()
        #st.success("Modifications globales intégrées au compte-rendu avec succès.")
        return True

    except requests.RequestException as e:
        st.error(f"Échec de la modification : {e}")
        return False