"""
Store de jobs en mémoire (process unique).

Remplace le mécanisme de callback synchrone utilisé côté Streamlit
monolithique : ici, l'exécution de la crew tourne dans un thread à part
(POST /analyze démarre le job et rend la main tout de suite), et le frontend
récupère la progression en pollant GET /jobs/{id}. Chaque agent qui termine
met à jour ce store via le callback CrewAI, exactement comme avant — sauf
que la mise à jour va dans un dict partagé au lieu d'un widget Streamlit.

Suffisant pour un prototype / usage mono-utilisateur ou petite équipe. Pour
un vrai déploiement multi-utilisateurs avec plusieurs workers, remplacer par
Redis (ou toute file de jobs partagée entre processus).
"""

import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Job:
    """Représente la progression et les résultats d'une analyse en cours."""

    job_id: str
    total_steps: int
    status: str = "running"  # running | done | error
    steps: list[dict] = field(default_factory=list)  # [{"key":.., "label":.., "status":..}]
    results: Optional[list[dict]] = None
    analyses: Optional[dict] = None
    redaction_raw: Optional[str] = None
    docx_ok: Optional[bool] = None
    docx_error: Optional[str] = None
    error: Optional[str] = None

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s["status"] == "done")


class JobStore:
    """Stocke les jobs et synchronise les accès entre threads du backend."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, total_steps: int, planned_steps: list[dict]) -> Job:
        # Le job est publié sous verrou avant que le thread d'analyse ne démarre.
        job_id = str(uuid.uuid4())
        job = Job(job_id=job_id, total_steps=total_steps, steps=planned_steps)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def mark_step_done(self, job_id: str, key: str):
        # Le callback CrewAI ne modifie que l'étape correspondante.
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for step in job.steps:
                if step["key"] == key:
                    step["status"] = "done"
                    break

    def finish(self, job_id: str, **fields):
        # Les résultats sont regroupés avant de basculer l'état final du job.
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for k, v in fields.items():
                setattr(job, k, v)
            job.status = "error" if job.error else "done"

    def fail(self, job_id: str, error: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.error = error
            job.status = "error"


# Instance unique partagée par toute l'app (process unique — voir note ci-dessus)
job_store = JobStore()