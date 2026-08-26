"""
Orchestrateur de la crew d'agents.

Expose quatre fonctions publiques :
  - build_crew               : crew complète (analyse + rédaction)
  - build_revision_crew      : mini-crew pour réviser une section déjà rédigée
  - build_redaction_retry_crew : relance uniquement le rédacteur sur des analyses existantes
  - build_json_fix_crew      : agent correcteur de JSON syntaxiquement invalide
"""

import functools

from crewai import Crew, Process, Task

from . import actions, decisions, objectif, outils_chiffres, participants, points_cles, risques
from .base import AGENT_META, AGENT_ORDER, DEFAULT_AGENT_CONFIG, build_llm, make_agent
from .redacteur import build_agent as build_redacteur_agent
from .redacteur import build_redaction_instructions

# Mapping clé → module agent (même ordre que AGENT_ORDER)
_AGENT_MODULES = {
    "participants": participants,
    "objectif": objectif,
    "points_cles": points_cles,
    "outils_chiffres": outils_chiffres,
    "decisions": decisions,
    "actions": actions,
    "risques": risques,
}


def build_crew(
    transcript: str,
    model_name: str,
    base_url: str,
    agent_config=None,
    on_task_complete=None,
    verbosity: str = "concis",
    user_input: str = "",
) -> Crew:
    """
    Construit la crew complète.

    `agent_config` : dict {clé: bool} — clés parmi AGENT_ORDER + "redacteur".
    None (par défaut) = DEFAULT_AGENT_CONFIG (tout activé).

    `on_task_complete` : callback optionnel appelé synchroniquement dès
    qu'une task se termine, signature `on_task_complete(key: str, output: TaskOutput)`.
    Comme Process.sequential exécute les tasks une par une dans le même
    thread, ce callback permet d'afficher une progression agent par agent
    pendant crew.kickoff() (ex: mise à jour d'un st.status()).

    `verbosity` : "concis" (défaut) ou "detaille" — contrôle le niveau de
    détail demandé à l'agent rédacteur.
    """
    llm = build_llm(model_name, base_url)

    if agent_config is None:
        agent_config = DEFAULT_AGENT_CONFIG

    used_keys = [k for k in AGENT_ORDER if agent_config.get(k, True)]

    if not used_keys:
        raise ValueError(
            "Aucun agent d'analyse activé — active au moins un agent dans la "
            "configuration avant de lancer l'analyse."
        )

    common_instructions = (
        "Voici le transcript de la réunion à analyser :\n\n"
        f"----- DEBUT TRANSCRIPT -----\n{transcript}\n----- FIN TRANSCRIPT -----\n\n"
    )

    agents_list = []
    tasks_list = []
    for key in used_keys:
        agent, task = _AGENT_MODULES[key].build(llm, common_instructions)
        if on_task_complete is not None:
            task.callback = functools.partial(on_task_complete, key)
        agents_list.append(agent)
        tasks_list.append(task)

    include_redacteur = agent_config.get("redacteur", True)
    if include_redacteur:
        redacteur_agent = build_redacteur_agent(llm, user_input)
        task_redaction = Task(
            description=(
                "Voici les analyses produites par les autres agents sur le "
                "transcript de la réunion.\n\n"
                + build_redaction_instructions(used_keys, verbosity)
            ),
            expected_output="Un unique objet JSON valide respectant le schéma donné, sans texte autour.",
            agent=redacteur_agent,
            context=tasks_list,
        )
        if on_task_complete is not None:
            task_redaction.callback = functools.partial(on_task_complete, "redacteur")
        agents_list.append(redacteur_agent)
        tasks_list.append(task_redaction)

    return Crew(
        agents=agents_list,
        tasks=tasks_list,
        process=Process.sequential,
        memory=False,
        verbose=False,
    )


def build_revision_crew(
    section_name: str,
    current_text: str,
    instructions: str,
    model_name: str,
    base_url: str,
) -> Crew:
    """
    Crée une mini-crew à un seul agent générique ("Réviseur"), chargé de
    retravailler le texte d'UNE section du compte-rendu (déjà générée par un
    autre agent) selon une consigne libre donnée par l'utilisateur (ex: "sois
    plus précis sur les dates", "reformule plus formellement"...).

    Contrairement à une relance de l'agent d'origine, ce réviseur ne revoit
    pas le transcript : il retravaille uniquement le texte déjà produit, ce
    qui le rend rapide et indépendant de AGENT_ORDER (utilisable aussi pour
    réviser la sortie JSON du rédacteur si besoin).
    """
    llm = build_llm(model_name, base_url)

    agent = make_agent(
        role="Réviseur de compte-rendu",
        goal="Retravailler une section déjà rédigée selon les instructions données, sans en changer le format",
        backstory=(
            "Tu es relecteur/réviseur professionnel. On te donne le texte "
            "d'une section déjà rédigée et une consigne de modification. Tu "
            "appliques strictement cette consigne, sans changer le format ni "
            "la structure générale du texte, et sans ajouter de commentaire "
            "sur ce que tu as changé."
        ),
        llm=llm,
    )

    description = (
        f"Voici le texte actuel de la section '{section_name}' d'un compte-rendu "
        "de réunion, à réviser :\n\n"
        f"----- TEXTE ACTUEL -----\n{current_text}\n----- FIN TEXTE ACTUEL -----\n\n"
        "Voici la consigne de modification à appliquer :\n\n"
        f"----- CONSIGNE -----\n{instructions}\n----- FIN CONSIGNE -----\n\n"
        "Applique cette consigne et renvoie une NOUVELLE VERSION COMPLÈTE de "
        "cette section, dans le même format que le texte actuel (même style "
        "de liste, mêmes titres le cas échéant). Ne renvoie que le résultat "
        "final : pas de commentaire méta, pas d'explication de ce que tu as "
        "changé."
    )

    task = Task(
        description=description,
        expected_output=f"La section '{section_name}' révisée, dans le même format que l'original.",
        agent=agent,
    )

    return Crew(agents=[agent], tasks=[task], process=Process.sequential, memory=False, verbose=False)


def build_redaction_retry_crew(
    analyses: dict, model_name: str, base_url: str, verbosity: str = "concis", user_input: str = ""
) -> Crew:
    """
    Relance UNIQUEMENT l'agent rédacteur, à partir des analyses déjà
    produites (pas besoin de re-router tout le transcript dans les autres
    agents). Utile quand seule l'étape de mise en JSON a échoué, ou pour
    redemander une version plus étoffée (`verbosity="detaille"`).

    `analyses` : dict dont les clés sont un sous-ensemble de AGENT_ORDER
    (seuls les agents activés lors du run initial y figurent).
    """
    llm = build_llm(model_name, base_url)
    redacteur_agent = build_redacteur_agent(llm, user_input)

    sections = []
    for key in AGENT_ORDER:
        if key in analyses:
            sections.append(f"--- {AGENT_META[key]['name']} ---\n{analyses[key]}")

    active_keys = list(analyses.keys())
    description = (
        "Voici les analyses déjà produites par d'autres agents sur le "
        "transcript d'une réunion :\n\n"
        + "\n\n".join(sections)
        + "\n\n"
        + build_redaction_instructions(active_keys, verbosity)
    )

    task_redaction = Task(
        description=description,
        expected_output="Un unique objet JSON valide respectant le schéma donné, sans texte autour.",
        agent=redacteur_agent,
    )

    return Crew(
        agents=[redacteur_agent],
        tasks=[task_redaction],
        process=Process.sequential,
        memory=False,
        verbose=False,
    )


def build_json_fix_crew(broken_json: str, error_report: str, model_name: str, base_url: str) -> Crew:
    """
    Agent dédié à la correction syntaxique d'un JSON cassé. Reçoit le JSON
    fautif ET le diagnostic précis (ligne/colonne/contexte) renvoyé par
    docx_export.diagnose_json_error, pour corriger chirurgicalement l'endroit
    signalé sans réécrire tout le document.
    """
    llm = build_llm(model_name, base_url)

    correcteur_agent = make_agent(
        role="Correcteur JSON",
        goal="Corriger un objet JSON syntaxiquement invalide, sans en changer le contenu",
        backstory=(
            "Tu es un expert du format JSON. On te fournit un JSON presque "
            "valide ainsi que le message d'erreur exact du parseur (ligne, "
            "colonne, caractère fautif, avec le contexte textuel autour). "
            "Tu répares UNIQUEMENT le problème de syntaxe signalé — virgule "
            "manquante, guillemet non échappé ou non fermé, accolade/crochet "
            "manquant, etc. Tu ne modifies ni les clés, ni les valeurs, ni "
            "la structure ailleurs dans le document."
        ),
        llm=llm,
    )

    description = (
        "Voici un JSON invalide produit par un autre agent :\n\n"
        f"----- JSON -----\n{broken_json}\n----- FIN JSON -----\n\n"
        "Voici le diagnostic exact du parseur, avec la position précise de "
        "l'erreur :\n\n"
        f"{error_report}\n\n"
        "Corrige UNIQUEMENT l'erreur de syntaxe signalée, à l'endroit "
        "indiqué. Ne touche à rien d'autre dans le document (ne reformule "
        "aucun texte, ne change aucune clé ni valeur). Renvoie l'objet JSON "
        "complet corrigé, et RIEN D'AUTRE : pas de texte avant/après, pas de "
        "balises markdown ```."
    )

    task = Task(
        description=description,
        expected_output="Le JSON complet, corrigé, strictement valide, sans texte autour.",
        agent=correcteur_agent,
    )

    return Crew(
        agents=[correcteur_agent],
        tasks=[task],
        process=Process.sequential,
        memory=False,
        verbose=False,
    )