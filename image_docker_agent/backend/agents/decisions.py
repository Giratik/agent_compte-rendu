"""Définition de l'agent chargé d'identifier les décisions actées."""

from crewai import Agent, Task, LLM

from .base import make_agent


def build(llm: LLM, common_instructions: str) -> tuple[Agent, Task]:
    """Construit l'agent et sa tâche d'extraction des décisions."""
    agent = make_agent(
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