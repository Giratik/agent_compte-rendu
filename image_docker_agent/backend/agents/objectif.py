"""Définition de l'agent qui résume le but de la réunion."""

from crewai import Agent, Task, LLM

from .base import make_agent


def build(llm: LLM, common_instructions: str) -> tuple[Agent, Task]:
    """Construit l'agent et la tâche de synthèse de l'objectif."""
    agent = make_agent(
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