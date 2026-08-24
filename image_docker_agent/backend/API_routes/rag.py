

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from engines.rag_engine import list_registry, registry_for_tool_calling, retrieve_context_hybrid
import os
CHATBOT_ROLE = os.environ.get("CHATBOT_ROLE", "CR")

from engines.rag_engine import (
    make_qdrant_client,
    #list_doc_dates,
)

router = APIRouter(prefix="/rag", tags=["RAG Engine"])



@router.get("/registry_get",
    summary="Special route to expose to the app which collection from qdrant it can access",
    description="Return entries from _registry collection which are all the collections this app has access to based on its role.",
    response_description="List of filtered registry entries",
    responses={
        200: {
            "description": "Successfully returned entries from _registry",
            "content": {
                "application/json": {
                    "example": {
                        "registry": [
                            {"nom": "collection_1", "description": "In this collection you'll find ..."},
                            {"nom": "collection_2", "description": "In this collection you'll find ..."}
                        ]
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Error retrieving collections"}
                }
            }
        }
    })
def get_registry_endpoint_evolve():
    client = make_qdrant_client()
    try:
        all_entries = list_registry(client)
        registry_entries = registry_for_tool_calling(client, role=CHATBOT_ROLE)
        return {"registry": registry_entries}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



class SearchRequest(BaseModel):
    collection_name: str = Query(..., description="Name of the collection to search in")
    query: str = Query(..., description="Search query text")
    model: str = Query(..., description="Generative model to use for search")
    n_results: int = Query(5, description="Number of results to return", ge=1, le=50)
    seuil: float = Query(0.5, description="Similarity threshold for results", ge=0.0, le=1.0)
    alpha: float = Query(0.5, description="Hybrid search weight parameter", ge=0.0, le=1.0)
    use_hyde: bool = Query(False, description="Whether to use Hypothetical Document Embeddings")
    use_expansion: bool = Query(False, description="Whether to use query expansion")
    doc_date_filter: str = Query("", description="Optional date filter for documents")

    class Config:
        json_schema_extra = {
            "example": {
                "collection_name": "my_collection",
                "query": "What is the capital of France?",
                "model": "gemma4:e4b",
                "n_results": 5,
                "seuil": 0.5,
                "alpha": 0.5,
                "use_hyde": False,
                "use_expansion": False,
                "doc_date_filter": "2023-01-01"
            }
        }


@router.post("/search",
    summary="Search in a collection",
    description="Perform a hybrid search in the specified collection using the given query and parameters",
    response_description="Search results with contexts, sources, and detailed chunks",
    responses={
        200: {
            "description": "Successfully performed search",
            "content": {
                "application/json": {
                    "example": {
                        "contexts": ["context1", "context2"],
                        "sources": ["source1", "source2"],
                        "detailed_chunks": [{"text": "chunk1", "score": 0.95}]
                    }
                }
            }
        },
        404: {
            "description": "Collection not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Collection not found"}
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Error during search"}
                }
            }
        }
    })
def search_endpoint(req: SearchRequest):
    qdrant_client = make_qdrant_client()
    try:
        # ⬅️ Changement ici : plus d'objet "collection", on utilise le client et la string
        contexts, sources, detailed_chunks = retrieve_context_hybrid(
            qdrant_client,
            req.collection_name,
            req.query,
            make_ollama_client(),
            req.model,
            req.n_results,
            req.seuil,
            req.alpha,
            req.use_hyde,
            req.use_expansion,
            doc_date_filter=req.doc_date_filter,
        )
        return {
            "contexts": contexts,
            "sources": sources,
            "detailed_chunks": detailed_chunks,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from fastapi import APIRouter, HTTPException
from qdrant_client.models import Record

# Assurez-vous d'utiliser votre instance existante de FastAPI ou APIRouter
# app = FastAPI() 

@router.get("/lexique/{collection_name}")
def get_full_lexicon(collection_name: str):
    """
    Parcourt (scroll) l'intégralité d'une collection Qdrant pour récupérer 
    tout son contenu (payload), sans récupérer les vecteurs pour économiser la bande passante.
    """
    client = make_qdrant_client()
    try:
        all_records = []
        next_offset = None
        
        # Boucle de pagination pour récupérer tous les documents
        while True:
            records, next_offset = client.scroll(
                collection_name=collection_name,
                limit=100,           # Taille du lot (batch)
                offset=next_offset,  # Curseur de pagination
                with_payload=True,   # On veut les métadonnées (document, acronyme, etc.)
                with_vectors=False   # Pas besoin des vecteurs pour afficher un lexique
            )
            
            all_records.extend(records)
            
            # Si next_offset est None, on a atteint la fin de la collection
            if next_offset is None:
                break
                
        # Formatage de la réponse
        #lexique_formate = []
        #for record in all_records:
        #    payload = record.payload or {}
        #    lexique_formate.append({
        #        "id": record.id,
        #        "document": payload.get("document", ""),
        #        "metadata": payload
        #    })
        #    
        #return {
        #    "collection": collection_name,
        #    "total_items": len(lexique_formate),
        #    "lexique": lexique_formate
        #}
        # Formatage de la réponse : on ne garde que le texte du document
        lexique_formate = []
        for record in all_records:
            payload = record.payload or {}
            texte_document = payload.get("document", "").strip()
            
            # On ajoute uniquement si le document n'est pas vide
            if texte_document:
                lexique_formate.append(texte_document)
            
        return {
            "collection": collection_name,
            "total_items": len(lexique_formate),
            "lexique": lexique_formate # Ceci est maintenant une simple liste de chaînes de caractères
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération du lexique: {str(e)}")