"""
Définition de la "crew" d'agents chargés d'analyser un transcript de réunion.

Chaque agent est spécialisé sur UN point précis :
  - Participants
  - Objectif de la réunion
  - Points clés abordés
  - Outils & chiffres mentionnés
  - Décisions prises
  - Actions à faire (next steps)
  - Points de blocage / désaccords

Les agents sont indépendants les uns des autres (aucun ne dépend de la sortie
d'un autre), ce qui permet de les lire séparément dans l'UI Streamlit et de
les activer/désactiver individuellement.

Un 7e agent, le Rédacteur final, consolide les analyses activées en un JSON
structuré prêt pour l'export Word.
"""

import functools
import os

from crewai import Agent, Task, Crew, Process, LLM

# --- Garde-fou : empêcher tout appel implicite vers OpenAI ---
# CrewAI initialise par défaut certaines fonctionnalités (mémoire, embedder,
# tracking de coût côté litellm) qui pointent vers OpenAI, même quand on ne
# passe QUE des LLM Ollama aux agents. En environnement sans accès internet
# (conteneur Docker isolé), ça se traduit par l'erreur "Failed to connect to
# OpenAI API: Connection error." dès qu'un de ces composants est sollicité.
# On neutralise ça à deux niveaux :
#   1. Une clé API OpenAI factice, pour satisfaire les validations qui ne
#      vérifient que la PRÉSENCE de la variable, sans jamais réellement
#      appeler OpenAI si tout le reste est bien configuré en local.
#   2. memory=False explicite sur chaque Crew (voir plus bas), pour éviter
#      que CrewAI instancie un embedder OpenAI par défaut pour la mémoire
#      court-terme/entité.
os.environ.setdefault("OPENAI_API_KEY", "sk-not-used-everything-is-local")
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")


def build_llm(model_name: str, base_url: str, temperature: float = 0.1) -> LLM:
    """
    Construit l'objet LLM CrewAI pointant vers une instance Ollama.
    model_name attendu SANS le préfixe 'ollama/' (ex: 'gemma2:9b'), il est
    ajouté automatiquement.

    api_key="ollama" : valeur factice mais non vide. Ollama n'exige pas de
    clé, mais certains chemins internes de crewai/litellm supposent la
    présence d'une clé API et basculent sur des comportements par défaut
    (souvent orientés OpenAI) quand elle est absente.
    """
    if not model_name.startswith("ollama/"):
        model_name = f"ollama/{model_name}"
    return LLM(model=model_name, base_url=base_url, api_key="ollama", temperature=temperature)


def _make_agent(role: str, goal: str, backstory: str, llm: LLM) -> Agent:
    return Agent(
        role=role,
        goal=goal,
        backstory=backstory,
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )


# --- Registre des 7 agents d'analyse (source de vérité unique pour l'ordre,
#     les labels UI et les descriptions affichées dans la config) ---

AGENT_ORDER = ["participants", "objectif", "points_cles", "outils_chiffres", "decisions", "actions", "risques"]

AGENT_META = {
    "participants": {
        "label": "👥 Participants",
        "name": "Participants",
        "description": "Identifie les personnes présentes (et absentes/excusées).",
    },
    "objectif": {
        "label": "🎯 Objectif de la réunion",
        "name": "Objectif",
        "description": "Résume en quelques phrases le but et le contexte de la réunion.",
    },
    "points_cles": {
        "label": "🔑 Points clés abordés",
        "name": "Points clés",
        "description": "Liste les principaux sujets discutés, décidés ou non.",
    },
    "outils_chiffres": {
        "label": "🛠️ Outils & chiffres",
        "name": "Outils & chiffres",
        "description": "Relève les outils cités et relie chaque chiffre pertinent à l'outil concerné.",
    },
    "decisions": {
        "label": "✅ Décisions prises",
        "name": "Décisions",
        "description": "Extrait les décisions clairement actées pendant la réunion.",
    },
    "actions": {
        "label": "📋 Actions à faire",
        "name": "Actions",
        "description": "Liste les tâches à faire, avec responsable et échéance si précisés.",
    },
    "risques": {
        "label": "⚠️ Points de blocage",
        "name": "Points de blocage",
        "description": "Repère désaccords non résolus, risques et questions ouvertes.",
    },
}

REDACTION_LABEL = "📝 Compte-rendu formaté (JSON)"

# Config par défaut : tous les agents activés, y compris le rédacteur
DEFAULT_AGENT_CONFIG = {**{k: True for k in AGENT_ORDER}, "redacteur": True}

# Labels indexés par clé (utile pour app.py, y compris pour les callbacks de progression)
TASK_LABELS = {**{k: v["label"] for k, v in AGENT_META.items()}, "redacteur": REDACTION_LABEL}


#REDACTION_JSON_SCHEMA = (
#    "{\n"
#    '  "titre": "titre court du compte-rendu",\n'
#    '  "date": "date de la réunion si mentionnée, sinon chaîne vide",\n'
#    '  "participants": ["Nom (fonction)", "..."],\n'
#    '  "absents": ["..."],\n'
#    '  "objectif": "paragraphe résumant le but de la réunion",\n'
#    '  "points_cles": ["point clé 1", "point clé 2"],\n'
#    '  "outils_et_chiffres": [\n'
#    '    {"outil": "nom de l\'outil/logiciel/technologie", '
#    '"chiffres_associes": ["chiffre lié à cet outil, avec son contexte", "..."]}\n'
#    "  ],\n"
#    '  "autres_chiffres": ["chiffre clé non lié à un outil précis, avec son contexte", "..."],\n'
#    '  "decisions": ["décision 1", "décision 2"],\n'
#    '  "actions": [\n'
#    '    {"action": "...", "responsable": "...", "echeance": "..."}\n'
#    "  ],\n"
#    '  "points_de_blocage": ["..."]\n'
#    "}"
#)

#def build_redaction_instructions(verbosity: str = "concis") -> str:
#    """
#    `verbosity` : "concis" (défaut) ou "detaille". Contrôle le niveau de
#    détail demandé au rédacteur lors de la consolidation en JSON.
#    """
#    base = (
#        "Consolide ces analyses en UN SEUL objet JSON, et RIEN D'AUTRE (pas de "
#        "texte avant/après, pas de balises markdown ```). Respecte EXACTEMENT "
#        "ce schéma, avec des guillemets doubles et sans virgule finale superflue "
#        "(JSON strictement valide) :\n\n"
#        f"{REDACTION_JSON_SCHEMA}\n\n"
#    )
#
#    if verbosity == "detaille":
#        style = (
#            "IMPORTANT — niveau de détail attendu : NE COMPRESSE PAS excessivement "
#            "le contenu des analyses fournies. Pour chaque élément (point clé, "
#            "décision, action, point de blocage...), reformule en 1 à 2 phrases "
#            "complètes qui conservent le contexte et les nuances de l'analyse "
#            "source, plutôt qu'en fragment télégraphique de quelques mots. Ne "
#            "fusionne JAMAIS deux idées distinctes de l'analyse source en un seul "
#            "point du JSON — un point source doit donner un point JSON, pas un "
#            "résumé qui en absorbe plusieurs. Si une analyse source contient un "
#            "exemple concret, un nom propre ou un chiffre, conserve-le dans le "
#            "JSON plutôt que de le généraliser. L'objectif est de restructurer "
#            "l'information, pas de la condenser.\n\n"
#        )
#    else:
#        style = (
#            "Niveau de détail attendu : reste synthétique — une phrase courte et "
#            "claire par élément suffit, sans détails superflus.\n\n"
#        )
#
#    tail = (
#        "Si une information est absente ou qu'aucune analyse ne la couvre, "
#        "utilise une chaîne vide ou une liste vide plutôt que d'inventer. "
#        "N'écris strictement rien en dehors de ce JSON."
#    )
#
#    return base + style + tail

# nouvelle fct rédaction dynamique
def build_dynamic_json_schema(active_keys: list[str]) -> str:
    """Construit dynamiquement le schéma JSON en fonction des agents activés."""
    schema_parts = [
        '  "titre": "titre court du compte-rendu"',
        '  "date": "date de la réunion si mentionnée, sinon chaîne vide"'
    ]
    
    if "participants" in active_keys:
        schema_parts.append('  "participants": ["Nom (fonction)", "..."]')
        schema_parts.append('  "absents": ["..."]')
    if "objectif" in active_keys:
        schema_parts.append('  "objectif": "paragraphe résumant le but de la réunion"')
    if "points_cles" in active_keys:
        schema_parts.append('  "points_cles": ["point clé 1", "point clé 2"]')
    if "outils_chiffres" in active_keys:
        schema_parts.append('  "outils_et_chiffres": [\n    {"outil": "nom de l\'outil/logiciel/technologie", "chiffres_associes": ["chiffre lié à cet outil, avec son contexte", "..."]}\n  ]')
        schema_parts.append('  "autres_chiffres": ["chiffre clé non lié à un outil précis, avec son contexte", "..."]')
    if "decisions" in active_keys:
        schema_parts.append('  "decisions": ["décision 1", "décision 2"]')
    if "actions" in active_keys:
        schema_parts.append('  "actions": [\n    {"action": "...", "responsable": "...", "echeance": "..."}\n  ]')
    if "risques" in active_keys:
        schema_parts.append('  "points_de_blocage": ["..."]')

    return "{\n" + ",\n".join(schema_parts) + "\n}"


def build_redaction_instructions(active_keys: list[str], verbosity: str = "concis") -> str:
    """
    Construit les instructions du rédacteur en lui passant uniquement
    le schéma correspondant aux agents actifs.
    """
    dynamic_schema = build_dynamic_json_schema(active_keys)
    
    base = (
        "Consolide ces analyses en UN SEUL objet JSON, et RIEN D'AUTRE (pas de "
        "texte avant/après, pas de balises markdown ```). Respecte EXACTEMENT "
        "ce schéma, avec des guillemets doubles et sans virgule finale superflue "
        "(JSON strictement valide) :\n\n"
        f"{dynamic_schema}\n\n"
    )
    if verbosity == "detaille":
        style = (
            "IMPORTANT — niveau de détail attendu : NE COMPRESSE PAS excessivement "
            "le contenu des analyses fournies. Pour chaque élément (point clé, "
            "décision, action, point de blocage...), reformule en 1 à 2 phrases "
            "complètes qui conservent le contexte et les nuances de l'analyse "
            "source, plutôt qu'en fragment télégraphique de quelques mots. Ne "
            "fusionne JAMAIS deux idées distinctes de l'analyse source en un seul "
            "point du JSON — un point source doit donner un point JSON, pas un "
            "résumé qui en absorbe plusieurs. Si une analyse source contient un "
            "exemple concret, un nom propre ou un chiffre, conserve-le dans le "
            "JSON plutôt que de le généraliser. L'objectif est de restructurer "
            "l'information, pas de la condenser.\n\n"
        )
    else:
        style = (
            "Niveau de détail attendu : reste synthétique — une phrase courte et "
            "claire par élément suffit, sans détails superflus.\n\n"
        )
    tail = (
        "Si une information est absente ou qu'aucune analyse ne la couvre, "
        "utilise une chaîne vide ou une liste vide plutôt que d'inventer. "
        "N'écris strictement rien en dehors de ce JSON."
    )
    return base + style + tail



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
            "par tes collègues (celles qui sont disponibles — certaines "
            "peuvent être absentes si l'utilisateur les a désactivées), tu "
            "corriges le style et la cohérence, et tu restitues le tout dans "
            "un format STRICTEMENT structuré."
        ),
        llm=llm,
    )


def build_redaction_retry_crew(
    analyses: dict, model_name: str, base_url: str, verbosity: str = "concis"
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
    redacteur_agent = _make_redacteur_agent(llm)

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

    return Crew(agents=[correcteur_agent], tasks=[task], process=Process.sequential, memory=False, verbose=False)


def _build_agent_and_task(key: str, llm: LLM, common_instructions: str) -> tuple[Agent, Task]:
    """Construit l'agent et la task pour UNE clé de AGENT_ORDER."""

    if key == "participants":
        agent = _make_agent(
            role="Analyste des participants",
            goal="Identifier avec précision toutes les personnes présentes à la réunion",
            backstory=(
                "Tu es spécialisé dans la lecture de comptes-rendus de réunion en "
                "français. Tu repères les noms propres, fonctions et éventuels "
                "absents/excusés mentionnés dans le texte."
            ),
            llm=llm,
        )
        task = Task(
            description=(
                common_instructions
                + "Liste toutes les personnes présentes (et si mentionné, les "
                "absents/excusés). Réponds sous forme de liste à puces avec, si "
                "possible, le nom et la fonction. Si l'information n'est pas "
                "dans le texte, dis-le explicitement plutôt que d'inventer."
            ),
            expected_output="Une liste à puces des participants (et absents éventuels).",
            agent=agent,
        )
        return agent, task

    if key == "objectif":
        agent = _make_agent(
            role="Analyste de l'objectif",
            goal="Déterminer le but et le contexte de la réunion",
            backstory=(
                "Tu es expert pour synthétiser en 2-3 phrases pourquoi une réunion "
                "a eu lieu et quel était son ordre du jour, à partir d'un transcript "
                "souvent informel et en français."
            ),
            llm=llm,
        )
        task = Task(
            description=(
                common_instructions
                + "Rédige en 2 à 4 phrases le but principal de cette réunion et "
                "son contexte."
            ),
            expected_output="Un court paragraphe décrivant l'objectif de la réunion.",
            agent=agent,
        )
        return agent, task

    if key == "points_cles":
        agent = _make_agent(
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
        task = Task(
            description=(
                common_instructions
                + "Liste, sous forme de puces, les principaux sujets et points "
                "abordés pendant la réunion — le contenu des échanges, pas "
                "seulement les décisions ou actions qui en découlent. Vise entre "
                "3 et 8 points, formulés en une phrase courte chacun."
            ),
            expected_output="Une liste à puces des points clés / sujets abordés pendant la réunion.",
            agent=agent,
        )
        return agent, task

    if key == "outils_chiffres":
        agent = _make_agent(
            role="Analyste des outils et chiffres",
            goal=(
                "Relever les outils/technologies cités et RELIER chaque chiffre "
                "pertinent à l'outil auquel il se rapporte"
            ),
            backstory=(
                "Tu es attentif aux outils, logiciels, plateformes ou "
                "technologies nommés dans une réunion, et surtout à leur mettre "
                "en relation avec les chiffres qui les concernent directement "
                "(coût, durée d'usage, nombre d'utilisateurs, performance, "
                "volume de données...). Tu ne listes JAMAIS un chiffre isolé "
                "d'un outil sans préciser à quoi il se rapporte. Tu es aussi "
                "sélectif : tu ignores les chiffres sans intérêt métier "
                "(horodatages, numéros de slide, décomptes de tours de parole) "
                "et ne gardes que ceux qui aident à comprendre une décision ou "
                "un enjeu réel."
            ),
            llm=llm,
        )
        task = Task(
            description=(
                common_instructions
                + "Identifie les outils/logiciels/technologies mentionnés, et "
                "pour CHACUN, relie-le explicitement aux chiffres qui le "
                "concernent (coût, durée d'utilisation, nombre d'utilisateurs, "
                "taux d'adoption, performance...). Ne retiens que des chiffres "
                "pertinents pour comprendre un enjeu ou une décision — ignore "
                "les chiffres sans intérêt (heures de réunion, numérotation, "
                "décomptes anecdotiques).\n\n"
                "Réponds avec ces deux titres exacts :\n\n"
                "Outils et chiffres associés :\n"
                "- [Nom de l'outil] : [chiffre(s) qui s'y rapportent, avec leur "
                "contexte — ou 'aucun chiffre associé' si l'outil est mentionné "
                "sans donnée chiffrée]\n\n"
                "Autres chiffres clés (non liés à un outil) :\n"
                "- [chiffre pertinent avec son contexte]\n\n"
                "Si aucun outil n'est mentionné, écris 'Aucun outil mentionné' "
                "sous le premier titre. Si aucun autre chiffre pertinent n'est "
                "identifiable, écris 'Aucun' sous le second."
            ),
            expected_output=(
                "Deux listes sous les titres 'Outils et chiffres associés' (un "
                "outil par ligne avec ses chiffres liés) et 'Autres chiffres "
                "clés' (chiffres pertinents non rattachés à un outil)."
            ),
            agent=agent,
        )
        return agent, task

    if key == "decisions":
        agent = _make_agent(
            role="Analyste des décisions",
            goal="Extraire toutes les décisions actées pendant la réunion",
            backstory=(
                "Tu distingues rigoureusement ce qui a été DÉCIDÉ de ce qui a "
                "simplement été discuté ou proposé sans validation finale."
            ),
            llm=llm,
        )
        task = Task(
            description=(
                common_instructions
                + "Liste, sous forme de puces, toutes les décisions clairement "
                "actées pendant la réunion. N'inclus pas les sujets simplement "
                "discutés sans décision finale."
            ),
            expected_output="Une liste à puces des décisions prises.",
            agent=agent,
        )
        return agent, task

    if key == "actions":
        agent = _make_agent(
            role="Analyste des actions",
            goal="Lister les actions à faire (tâches), avec responsable et échéance si mentionnés",
            backstory=(
                "Tu identifies les 'next steps' d'une réunion : qui doit faire "
                "quoi, et pour quand, même si l'information est implicite dans "
                "le texte."
            ),
            llm=llm,
        )
        task = Task(
            description=(
                common_instructions
                + "Liste les actions à faire sous la forme : "
                "'- [Action] — Responsable: [nom ou \"non précisé\"] — "
                "Échéance: [date ou \"non précisée\"]'."
            ),
            expected_output="Une liste à puces des actions avec responsable et échéance.",
            agent=agent,
        )
        return agent, task

    if key == "risques":
        agent = _make_agent(
            role="Analyste des points de blocage",
            goal="Repérer les désaccords, risques ou questions restées en suspens",
            backstory=(
                "Tu es attentif aux tensions, désaccords non résolus, risques "
                "évoqués ou questions ouvertes qui n'ont pas trouvé de réponse "
                "pendant la réunion."
            ),
            llm=llm,
        )
        task = Task(
            description=(
                common_instructions
                + "Liste les désaccords non résolus, risques évoqués ou "
                "questions restées ouvertes. Si aucun n'est identifiable, "
                "réponds simplement 'Aucun point de blocage identifié'."
            ),
            expected_output="Une liste à puces des points de blocage, ou une phrase indiquant qu'il n'y en a pas.",
            agent=agent,
        )
        return agent, task

    raise ValueError(f"Clé d'agent inconnue : {key}")


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

    agent = _make_agent(
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


def build_crew(
    transcript: str,
    model_name: str,
    base_url: str,
    agent_config=None,
    on_task_complete=None,
    verbosity: str = "concis",
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
        agent, task = _build_agent_and_task(key, llm, common_instructions)
        if on_task_complete is not None:
            task.callback = functools.partial(on_task_complete, key)
        agents_list.append(agent)
        tasks_list.append(task)

    include_redacteur = agent_config.get("redacteur", True)
    if include_redacteur:
        redacteur_agent = _make_redacteur_agent(llm)
        task_redaction = Task(
            description=(
                "Voici les analyses produites par les autres agents sur le "
                "transcript de la réunion.\n\n" + build_redaction_instructions(used_keys, verbosity)
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