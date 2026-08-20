#backend/engines/rag_engine.py

import re
import httpx

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
from qdrant_client.http.models import VectorParams, Distance, PayloadSchemaType
from qdrant_client.http.models import PointStruct
import uuid
from datetime import datetime, timezone

from typing import Any

import os
CONTEXT_SIZE = int(os.environ.get("CONTEXT_SIZE", 22000))
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", 6333))
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "embeddinggemma:latest")
# ─── CLIENTS ──────────────────────────────────────────────────────────────────

def make_qdrant_client() -> QdrantClient:
    return QdrantClient(host=QDRANT_HOST, port=int(QDRANT_PORT))



#def list_collections(qdrant_client: QdrantClient) -> list[str]:
#    return sorted(c.name for c in qdrant_client.get_collections().collections)

# ─── REGISTRY DES COLLECTIONS ────────────────────────────────────────────────
REGISTRY_COLLECTION = "_registry"

def ensure_registry(qdrant_client: QdrantClient) -> None:
    """Crée la collection _registry si elle n'existe pas."""
    existing = [c.name for c in qdrant_client.get_collections().collections]
    if REGISTRY_COLLECTION not in existing:
        qdrant_client.create_collection(
            collection_name=REGISTRY_COLLECTION,
            # Vecteurs factices de dimension 1 — le registry n'est pas requêté
            # par similarité, uniquement par scroll/filtre.
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )
        qdrant_client.create_payload_index(
            collection_name=REGISTRY_COLLECTION,
            field_name="collection_name",
            field_schema=PayloadSchemaType.KEYWORD,
        )

def list_registry(qdrant_client: QdrantClient) -> list[dict]:
    """Retourne toutes les entrées du registry triées par nom de collection."""
    ensure_registry(qdrant_client)
    records = []
    offset = None
    while True:
        batch, offset = qdrant_client.scroll(
            collection_name=REGISTRY_COLLECTION,
            limit=200,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        records.extend(batch)
        if offset is None:
            break
    return sorted(
        [r.payload for r in records if r.payload],
        key=lambda x: x.get("collection_name", ""),
    )


def registry_for_tool_calling(client, role: str = "") -> list[dict]: #accès basé sur les rôles (RBAC)
    entries = list_registry(client)
    result = []
    for e in entries:
        if not e.get("active", True):
            continue
        allowed = e.get("allowed_roles", [])
        # Accessible si : pas de restriction, ou le rôle est dans la liste
        if not allowed or role in allowed or role == "admin":
            result.append({"nom": e["collection_name"], "description": e["description"]})
    return result

def list_doc_dates(qdrant_client: QdrantClient, collection_name: str) -> list[str]:
    """Parcourt la collection Qdrant pour extraire les dates uniques."""
    dates = set()
    offset = None
    while True:
        records, offset = qdrant_client.scroll(
            collection_name=collection_name,
            limit=200,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for r in records:
            if r.payload and r.payload.get("doc_date"):
                dates.add(r.payload["doc_date"])
        if offset is None:
            break
    return sorted(list(dates))

# backend/engines/rag_engine.py
def list_available_collections(client: QdrantClient, role: str = "") -> list[dict]:
    """
    Retourne les collections accessibles pour un rôle donné.
    Chaque entrée : {"nom": str, "description": str}
    """
    return registry_for_tool_calling(client, role=role)

