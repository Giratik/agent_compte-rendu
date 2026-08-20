

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from engines.rag_engine import list_registry, registry_for_tool_calling
import os
CHATBOT_ROLE = os.environ.get("CHATBOT_ROLE", "CR")

from engines.rag_engine import (
    make_qdrant_client,
    list_doc_dates,
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