"""Définition de l'agent qui recense participants et absents."""

from crewai import Agent, Task, LLM

from .base import make_agent


def build(llm: LLM, common_instructions: str) -> tuple[Agent, Task]:
    """Construit l'agent et la tâche d'identification des personnes."""
    agent = make_agent(
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