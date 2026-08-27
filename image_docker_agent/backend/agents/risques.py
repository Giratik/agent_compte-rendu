"""Définition de l'agent qui relève les risques et questions ouvertes."""

from crewai import Agent, Task, LLM

from .base import make_agent


def build(llm: LLM, common_instructions: str) -> tuple[Agent, Task]:
    """Construit l'agent et la tâche d'analyse des blocages."""
    agent = make_agent(
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