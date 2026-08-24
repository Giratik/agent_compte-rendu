"""
Agent rédacteur final et helpers de génération du schéma JSON dynamique.
"""

from crewai import Agent, LLM

from .base import make_agent


def build_agent(llm: LLM, user_input = "") -> Agent:
    return make_agent(
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
            "Voici des instructions supplémentaires de l'utilisateur pour orienter la rédaction du compte-rendu :"
            f"{user_input}"
        ),
        llm=llm,
    )


def build_dynamic_json_schema(active_keys: list[str]) -> str:
    """Construit dynamiquement le schéma JSON en fonction des agents activés."""
    schema_parts = [
        '  "titre": "titre court du compte-rendu"',
        '  "date": "date de la réunion si mentionnée, sinon chaîne vide"',
    ]

    if "participants" in active_keys:
        schema_parts.append('  "participants": ["Nom (fonction)", "..."]')
        schema_parts.append('  "absents": ["..."]')
    if "objectif" in active_keys:
        schema_parts.append('  "objectif": "paragraphe résumant le but de la réunion"')
    if "points_cles" in active_keys:
        schema_parts.append('  "points_cles": ["point clé 1", "point clé 2"]')
    if "outils_chiffres" in active_keys:
        schema_parts.append(
            '  "outils_et_chiffres": [\n'
            '    {"outil": "nom de l\'outil/logiciel/technologie", '
            '"chiffres_associes": ["chiffre lié à cet outil, avec son contexte", "..."]}\n'
            "  ]"
        )
        schema_parts.append(
            '  "autres_chiffres": ["chiffre clé non lié à un outil précis, avec son contexte", "..."]'
        )
    if "decisions" in active_keys:
        schema_parts.append('  "decisions": ["décision 1", "décision 2"]')
    if "actions" in active_keys:
        schema_parts.append(
            '  "actions": [\n'
            '    {"action": "...", "responsable": "...", "echeance": "..."}\n'
            "  ]"
        )
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