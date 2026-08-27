"""Accès Qdrant et recherche hybride utilisée par les routes RAG."""

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
    """Construit un client configuré avec les paramètres du conteneur."""
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
    """Filtre le registre selon l'état actif et le rôle du chatbot."""
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

#def list_doc_dates(qdrant_client: QdrantClient, collection_name: str) -> list[str]:
#    """Parcourt la collection Qdrant pour extraire les dates uniques."""
#    dates = set()
#    offset = None
#    while True:
#        records, offset = qdrant_client.scroll(
#            collection_name=collection_name,
#            limit=200,
#            offset=offset,
#            with_payload=True,
#            with_vectors=False,
#        )
#        for r in records:
#            if r.payload and r.payload.get("doc_date"):
#                dates.add(r.payload["doc_date"])
#        if offset is None:
#            break
#    return sorted(list(dates))

# backend/engines/rag_engine.py
def list_available_collections(client: QdrantClient, role: str = "") -> list[dict]:
    """
    Retourne les collections accessibles pour un rôle donné.
    Chaque entrée : {"nom": str, "description": str}
    """
    return registry_for_tool_calling(client, role=role)



def retrieve_context_hybrid(
    qdrant_client: QdrantClient,
    collection_name: str,
    query: str,
    ollama_client: Any,
    model: str,
    n_results: int,
    seuil: float,
    alpha: float,
    use_hyde: bool,
    use_expansion: bool,
    doc_date_filter: str = "",
) -> tuple[list[str], list[tuple], list[dict]]:
    """Combine recherche vectorielle et BM25, puis prépare les sources citées."""
    queries = [query]
    if use_expansion:
        queries = expand_query(ollama_client, model, query)
    if use_hyde:
        queries.append(hyde_query(ollama_client, model, query))

    per_query = max(5, n_results // len(queries))

    # ── Récupération vectorielle Qdrant ───────────────────────────────────────
    candidates: dict[str, dict] = {}
    
    qdrant_filter = None
    if doc_date_filter:
        qdrant_filter = Filter(must=[FieldCondition(key="doc_date", match=MatchValue(value=doc_date_filter))])

    for q in queries:
        try:
            q_vector = embed([q], OLLAMA_HOST, EMBEDDING_MODEL)[0]
            result = qdrant_client.query_points(
                collection_name=collection_name,
                query=q_vector,
                query_filter=qdrant_filter,
                limit=per_query,
                with_payload=True
            )
            
            for hit in result.points:
                dist = max(0.0, 1.0 - hit.score)
                if dist <= seuil and hit.id not in candidates:
                    candidates[hit.id] = {
                        "document": hit.payload.get("document", ""),
                        "metadata": hit.payload,
                        "vecto_distance": dist,
                    }
        except Exception as e:
            import logging
            logging.warning(f"Erreur sur la query '{q}': {e}")
            continue

    if not candidates:
        return [], [], []

    ids = list(candidates.keys())
    docs = [candidates[i]["document"] for i in ids]
    metas = [candidates[i]["metadata"] for i in ids]
    vecto_distances = [candidates[i]["vecto_distance"] for i in ids]

    # ── Scores normalisés ─────────────────────────────────────────────────────
    vecto_scores = [1 - d / 2 for d in vecto_distances]
    max_v = max(vecto_scores) or 1
    vecto_scores_norm = [s / max_v for s in vecto_scores]

    corpus_tokens = [tokenize(d) for d in docs]
    bm25 = BM25Okapi(corpus_tokens)
    bm25_scores = bm25.get_scores(tokenize(query))
    max_b = max(bm25_scores) or 1
    bm25_scores_norm = [s / max_b for s in bm25_scores]

    hybrid_scores = [
        alpha * vecto_scores_norm[i] + (1 - alpha) * bm25_scores_norm[i]
        for i in range(len(ids))
    ]

    # ── Hybrid ranking initial ────────────────────────────────────────────────
    ranked = sorted(
        zip(hybrid_scores, vecto_distances, bm25_scores, docs, metas),
        key=lambda x: x[0],
        reverse=True,
    )[:n_results]

    ranked_with_rerank = [(*item, 0.0) for item in ranked]

    # ── Construction des résultats ────────────────────────────────────────────
    contexts: list[str] = []
    sources: list[tuple] = []
    detailed_chunks: list[dict] = []
    seen_sources: set[str] = set()

    for hybrid_score, vecto_dist, bm25_score, doc, meta, rerank_score in ranked_with_rerank:
        if "source" in meta and "page" in meta:
            source_name = f"📄 {meta['source']} (Page {meta['page']})"
            source_url = meta.get("source_url", "").strip()
            if source_url:
                source_name += f" — [Ouvrir le lien]({source_url})"
            chunk_type = "pdf"
            doc_date = meta.get("doc_date", "")
        elif "acronyme" in meta:
            source_name = f"📚 Lexique : {meta['acronyme']}"
            chunk_type = "lexique"
            doc_date = ""
        else:
            source_name = "Document inconnu"
            chunk_type = "unknown"
            doc_date = ""

        context_line = f"Extrait de {source_name}"
        if doc_date:
            context_line += f" [Document du {doc_date}]"
        context_line += f" :\n{doc}"
        contexts.append(context_line)

        if source_name not in seen_sources:
            sources.append((source_name, hybrid_score, vecto_dist, doc_date))
            seen_sources.add(source_name)

        detailed_chunks.append({
            "source": source_name,
            "type": chunk_type,
            "document": doc,
            "metadata": meta,
            "hybrid_score": hybrid_score,
            "vecto_distance": vecto_dist,
            "bm25_score": bm25_score,
            "doc_date": doc_date,
            "rerank_score": rerank_score,
            "source_url": meta.get("source_url", ""),
        })

    return contexts, sources, detailed_chunks
