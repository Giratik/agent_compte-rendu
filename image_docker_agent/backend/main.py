# backend/main.py

from fastapi import FastAPI

# Importation des routeurs modulaires
from API_routes import rag, agent, transcribe

app = FastAPI(title="API CR")

app.include_router(rag.router)
app.include_router(agent.router)
app.include_router(transcribe.router)