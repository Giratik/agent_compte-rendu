"""
Définition de la "crew" d'agents chargés d'analyser un transcript de réunion.

Chaque agent est spécialisé sur UN point précis :
  - Participants
  - Objectif de la réunion
  - Points clés abordés
  - Décisions prises
  - Actions à faire (next steps)
  - Points de blocage / désaccords

Les agents sont indépendants les uns des autres (aucun ne dépend de la sortie
d'un autre), ce qui permet de les lire séparément dans l'UI Streamlit.
"""

from crewai import Agent, Task, Crew, Process, LLM

# Agent configuration - allows enabling/disabling individual agents
DEFAULT_AGENT_CONFIG = {
    "participants": True,
    "objectif": True,
    "points_cles": True,
    "decisions": True,
    "actions": True,
    "risques": True,
    "redacteur": True
}


def build_llm(model_name: str, base_url: str, temperature: float = 0.1) -> LLM:
    """
    Construit l'objet LLM CrewAI pointant vers une instance Ollama.
    model_name attendu SANS le préfixe 'ollama/' (ex: 'gemma2:9b'), il est
    ajouté automatiquement.
    """
    if not model_name.startswith("ollama/"):
        model_name = f"ollama/{model_name}"
    return LLM(model=model_name, base_url=base_url, temperature=temperature)


def _make_agent(role: str, goal: str, backstory: str, llm: LLM) -> Agent:
    return Agent(
        role=role,
        goal=goal,
        backstory=backstory,
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )


REDACTION_JSON_SCHEMA = (
    "{\n"
    '  "titre": "titre court du compte-rendu",\n'
    '  "date": "date de la réunion si mentionnée, sinon chaîne vide",\n'
    '  "participants": ["Nom (fonction)", "..."],\n'
    '  "absents": ["..."],\n'
    '  "objectif": "paragraphe résumant le but de la réunion",\n'
    '  "points_cles": ["point clé 1", "point clé 2"],\n'
    '  "decisions": ["décision 1", "décision 2"],\n'
    '  "actions": [\n'
    '    {"action": "...", "responsable": "...", "echeance": "..."}\n'
    "  ],\n"
    '  "points_de_blocage": ["..."]\n'
    "}"
)

REDACTION_INSTRUCTIONS = (
    "Consolide ces analyses en UN SEUL objet JSON, et RIEN D'AUTRE (pas de "
    "texte avant/après, pas de balises markdown ```). Respecte EXACTEMENT "
    "ce schéma, avec des guillemets doubles et sans virgule finale superflue "
    "(JSON strictement valide) :\n\n"
    f"{REDACTION_JSON_SCHEMA}\n\n"
    "Si une information est absente, utilise une chaîne vide ou une liste "
    "vide plutôt que d'inventer. N'écris strictement rien en dehors de ce JSON."
)


def _make_redacteur_agent(llm: LLM) -> Agent:
    return _make_agent(
        role="Rédacteur final",
        goal=(
            "Consolider les analyses des autres agents en un compte-rendu "
            "structuré, propre, prêt à être converti en document Word"
        ),
        backstory=(
            "Tu es rédacteur professionnel de comptes-rendus. Tu ne réanalyses "
            "pas le transcript brut : tu reprends les analyses déjà produites "
            "par tes collègues (participants, objectif, points clés, décisions, "
            "actions, points de blocage), tu corriges le style et la cohérence, "
            "et tu restitues le tout dans un format STRICTEMENT structuré."
        ),
        llm=llm,
    )


def build_redaction_retry_crew(analyses: dict, model_name: str, base_url: str) -> Crew:
    """
    Relance UNIQUEMENT l'agent rédacteur, à partir des analyses déjà
    produites (pas besoin de re-router tout le transcript dans les autres
    agents). Utile quand seule l'étape de mise en JSON a échoué.

    `analyses` attend les clés : participants, objectif, points_cles, decisions, actions, risques
    """
    llm = build_llm(model_name, base_url)
    redacteur_agent = _make_redacteur_agent(llm)

    description = (
        "Voici les analyses déjà produites par d'autres agents sur le "
        "transcript d'une réunion :\n\n"
        f"--- Participants ---\n{analyses.get('participants', '')}\n\n"
        f"--- Objectif ---\n{analyses.get('objectif', '')}\n\n"
        f"--- Points clés abordés ---\n{analyses.get('points_cles', '')}\n\n"
        f"--- Décisions ---\n{analyses.get('decisions', '')}\n\n"
        f"--- Actions ---\n{analyses.get('actions', '')}\n\n"
        f"--- Points de blocage ---\n{analyses.get('risques', '')}\n\n"
        + REDACTION_INSTRUCTIONS
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

    correcteur_agent = _make_agent(
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

    return Crew(agents=[correcteur_agent], tasks=[task], process=Process.sequential, verbose=False)


def build_crew(transcript: str, model_name: str, base_url: str, agent_config: dict = None) -> Crew:
    """Build the crew with optional agent configuration to enable/disable specific agents."""
    if agent_config is None:
        agent_config = DEFAULT_AGENT_CONFIG
    llm = build_llm(model_name, base_url)

    participants_agent = _make_agent(
        role="Analyste des participants",
        goal="Identifier avec précision toutes les personnes présentes à la réunion",
        backstory=(
            "Tu es spécialisé dans la lecture de comptes-rendus de réunion en "
            "français. Tu repères les noms propres, fonctions et éventuels "
            "absents/excusés mentionnés dans le texte."
        ),
        llm=llm,
    )

    objectif_agent = _make_agent(
        role="Analyste de l'objectif",
        goal="Déterminer le but et le contexte de la réunion",
        backstory=(
            "Tu es expert pour synthétiser en 2-3 phrases pourquoi une réunion "
            "a eu lieu et quel était son ordre du jour, à partir d'un transcript "
            "souvent informel et en français."
        ),
        llm=llm,
    )

    points_cles_agent = _make_agent(
        role="Analyste des points clés",
        goal="Identifier les principaux sujets et points abordés pendant la réunion",
        backstory=(
            "Tu fais une synthèse des thèmes et sujets réellement discutés "
            "pendant la réunion, qu'ils aient débouché ou non sur une décision. "
            "Tu te concentres sur le CONTENU des échanges (de quoi a-t-on "
            "parlé), à ne pas confondre avec les décisions actées ou les "
            "actions à faire, qui sont traitées par d'autres agents."
        ),
        llm=llm,
    )

    decisions_agent = _make_agent(
        role="Analyste des décisions",
        goal="Extraire toutes les décisions actées pendant la réunion",
        backstory=(
            "Tu distingues rigoureusement ce qui a été DÉCIDÉ de ce qui a "
            "simplement été discuté ou proposé sans validation finale."
        ),
        llm=llm,
    )

    actions_agent = _make_agent(
        role="Analyste des actions",
        goal="Lister les actions à faire (tâches), avec responsable et échéance si mentionnés",
        backstory=(
            "Tu identifies les 'next steps' d'une réunion : qui doit faire "
            "quoi, et pour quand, même si l'information est implicite dans "
            "le texte."
        ),
        llm=llm,
    )

    risques_agent = _make_agent(
        role="Analyste des points de blocage",
        goal="Repérer les désaccords, risques ou questions restées en suspens",
        backstory=(
            "Tu es attentif aux tensions, désaccords non résolus, risques "
            "évoqués ou questions ouvertes qui n'ont pas trouvé de réponse "
            "pendant la réunion."
        ),
        llm=llm,
    )

    common_instructions = (
        "Voici le transcript de la réunion à analyser :\n\n"
        f"----- DEBUT TRANSCRIPT -----\n{transcript}\n----- FIN TRANSCRIPT -----\n\n"
    )

    task_participants = Task(
        description=(
            common_instructions
            + "Liste toutes les personnes présentes (et si mentionné, les "
            "absents/excusés). Réponds sous forme de liste à puces avec, si "
            "possible, le nom et la fonction. Si l'information n'est pas "
            "dans le texte, dis-le explicitement plutôt que d'inventer."
        ),
        expected_output="Une liste à puces des participants (et absents éventuels).",
        agent=participants_agent,
    )

    task_objectif = Task(
        description=(
            common_instructions
            + "Rédige en 2 à 4 phrases le but principal de cette réunion et "
            "son contexte."
        ),
        expected_output="Un court paragraphe décrivant l'objectif de la réunion.",
        agent=objectif_agent,
    )

    task_points_cles = Task(
        description=(
            common_instructions
            + "Liste, sous forme de puces, les principaux sujets et points "
            "abordés pendant la réunion — le contenu des échanges, pas "
            "seulement les décisions ou actions qui en découlent. Vise entre "
            "3 et 8 points, formulés en une phrase courte chacun."
        ),
        expected_output="Une liste à puces des points clés / sujets abordés pendant la réunion.",
        agent=points_cles_agent,
    )

    task_decisions = Task(
        description=(
            common_instructions
            + "Liste, sous forme de puces, toutes les décisions clairement "
            "actées pendant la réunion. N'inclus pas les sujets simplement "
            "discutés sans décision finale."
        ),
        expected_output="Une liste à puces des décisions prises.",
        agent=decisions_agent,
    )

    task_actions = Task(
        description=(
            common_instructions
            + "Liste les actions à faire sous la forme : "
            "'- [Action] — Responsable: [nom ou \"non précisé\"] — "
            "Échéance: [date ou \"non précisée\"]'."
        ),
        expected_output="Une liste à puces des actions avec responsable et échéance.",
        agent=actions_agent,
    )

    task_risques = Task(
        description=(
            common_instructions
            + "Liste les désaccords non résolus, risques évoqués ou "
            "questions restées ouvertes. Si aucun n'est identifiable, "
            "réponds simplement 'Aucun point de blocage identifié'."
        ),
        expected_output="Une liste à puces des points de blocage, ou une phrase indiquant qu'il n'y en a pas.",
        agent=risques_agent,
    )

    redacteur_agent = _make_redacteur_agent(llm)

    # Build lists of agents and tasks based on configuration
    agents_list = []
    tasks_list = []
    context_tasks = []

    if agent_config["participants"]:
        agents_list.append(participants_agent)
        tasks_list.append(task_participants)
        context_tasks.append(task_participants)

    if agent_config["objectif"]:
        agents_list.append(objectif_agent)
        tasks_list.append(task_objectif)
        context_tasks.append(task_objectif)

    if agent_config["points_cles"]:
        agents_list.append(points_cles_agent)
        tasks_list.append(task_points_cles)
        context_tasks.append(task_points_cles)

    if agent_config["decisions"]:
        agents_list.append(decisions_agent)
        tasks_list.append(task_decisions)
        context_tasks.append(task_decisions)

    if agent_config["actions"]:
        agents_list.append(actions_agent)
        tasks_list.append(task_actions)
        context_tasks.append(task_actions)

    if agent_config["risques"]:
        agents_list.append(risques_agent)
        tasks_list.append(task_risques)
        context_tasks.append(task_risques)

    if agent_config["redacteur"]:
        agents_list.append(redacteur_agent)

        task_redaction = Task(
            description=(
                "Voici les analyses produites par les autres agents sur le "
                "transcript de la réunion.\n\n" + REDACTION_INSTRUCTIONS
            ),
            expected_output="Un unique objet JSON valide respectant le schéma donné, sans texte autour.",
            agent=redacteur_agent,
            context=context_tasks,
        )
        tasks_list.append(task_redaction)

    crew = Crew(
        agents=agents_list,
        tasks=tasks_list,
        process=Process.sequential,
        verbose=False,
    )
    return crew


# Labels affichés dans l'UI, dans le même ordre que les tasks ci-dessus
TASK_LABELS = [
    "👥 Participants",
    "🎯 Objectif de la réunion",
    "🔑 Points clés abordés",
    "✅ Décisions prises",
    "📋 Actions à faire",
    "⚠️ Points de blocage",
    "📝 Compte-rendu formaté (JSON)",
]