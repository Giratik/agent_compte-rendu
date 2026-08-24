from crewai import Agent, Task, LLM

from .base import make_agent


def build(llm: LLM, common_instructions: str) -> tuple[Agent, Task]:
    agent = make_agent(
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