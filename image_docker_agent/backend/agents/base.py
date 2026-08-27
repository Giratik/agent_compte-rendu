"""
Utilitaires partagés entre tous les agents :
  - Configuration de l'environnement (garde-fous OpenAI / telemetry)
  - Constructeur LLM Ollama
  - Fabrique d'Agent générique
  - Constantes de registre (AGENT_ORDER, AGENT_META, labels, config par défaut)
"""

import os

from crewai import Agent, LLM

# --- Garde-fou : empêcher tout appel implicite vers OpenAI ---
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


def make_agent(role: str, goal: str, backstory: str, llm: LLM) -> Agent:
    """Applique les réglages communs aux agents spécialisés de la crew."""
    return Agent(
        role=role,
        goal=goal,
        backstory=backstory,
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )


# ---------------------------------------------------------------------------
# Registre des 7 agents d'analyse
# Source de vérité unique pour l'ordre, les labels UI et les descriptions.
# ---------------------------------------------------------------------------

# L'ordre détermine à la fois l'exécution séquentielle et l'affichage frontend.
AGENT_ORDER = [
    "participants",
    "objectif",
    "points_cles",
    "outils_chiffres",
    "decisions",
    "actions",
    "risques",
]

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