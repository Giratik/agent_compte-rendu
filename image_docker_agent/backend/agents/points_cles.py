"""Définition de l'agent qui synthétise les sujets abordés."""

from crewai import Agent, Task, LLM

from .base import make_agent


def build(llm: LLM, common_instructions: str) -> tuple[Agent, Task]:
    """Construit l'agent et la tâche de synthèse des points clés."""
    agent = make_agent(
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