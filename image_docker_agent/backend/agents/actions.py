from crewai import Agent, Task, LLM

from .base import make_agent


def build(llm: LLM, common_instructions: str) -> tuple[Agent, Task]:
    agent = make_agent(
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