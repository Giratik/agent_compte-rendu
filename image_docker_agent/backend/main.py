"""Point d'entrée de l'API FastAPI du service backend."""

from fastapi import FastAPI

# Importation des routeurs modulaires
from API_routes import rag, agent, transcribe

# L'application assemble les routeurs métier afin de garder chaque domaine isolé.
app = FastAPI(title="API CR")

app.include_router(rag.router)
app.include_router(agent.router)
app.include_router(transcribe.router)