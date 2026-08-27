"""
plugins/wrapper_API.py
────────────────
Wrapper HTTP vers l'API FastAPI RAG.
Chaque fonction reproduit la signature attendue par les modules ui/
afin de rester un drop-in replacement des appels directs à backend.py.
"""

from __future__ import annotations
import re

import requests
from typing import Generator, List, Dict, Any, Optional

# ── URL de base (peut être surchargée via st.secrets ou variable d'env) ───────
import os
BASE_URL = os.getenv("API_URL", os.getenv("RAG_API_URL", os.getenv("BACKEND_URL", "http://backend:8000")))


# ─── helpers ──────────────────────────────────────────────────────────────────
 
def _get(path: str, **kwargs) -> Any:
    """Effectue une lecture HTTP et renvoie directement le JSON de l'API."""
    resp = requests.get(f"{BASE_URL}{path}", **kwargs)
    resp.raise_for_status()
    return resp.json()
 
 
def _post(path: str, payload: dict, **kwargs) -> Any:
    """Effectue une requête JSON et centralise la vérification d'erreur HTTP."""
    resp = requests.post(f"{BASE_URL}{path}", json=payload, **kwargs)
    resp.raise_for_status()
    return resp.json()
 
 
# ─── Collections & modèles ────────────────────────────────────────────────────
 
#def list_collections() -> List[str]:
#    return _get("/rag/collections")["collections"]

def list_collections_qdrant() -> List[str]:
    return _get("/rag/collections")["collections"]

def get_registry_collection():
    """Récupère le registre filtré par rôle exposé par le backend."""
    try:
        registry_entries = _get("/rag/registry_get")
        return registry_entries# => retourne directement la liste des entrées
    except Exception as e:
        print(f"Erreur registry : {e}")
        return []
 
 
def list_generative_models() -> List[str]:
    return _get("/rag/models")["models"]
 
 
#def list_doc_dates(collection_name: str) -> List[str]:
#    try:
#        return _get(f"/rag/collections/{collection_name}/dates")
#    except Exception:
#        return []
 
 
# ─── Réécriture de requête ────────────────────────────────────────────────────
 
def rewrite_query(
    query: str,
    model: str,
    context_size: int,
    chat_history: List[Dict[str, str]],
) -> str:
    data = _post("/rag/rewrite", {
        "query": query,
        "model": model,
        "context_size": context_size,
        "chat_history": chat_history,
    })
    return data["rewritten_query"]
 
 
# ─── Recherche hybride ────────────────────────────────────────────────────────
 
def retrieve_context_hybrid(
    collection_name: str,
    query: str,
    model: str,
    context_size: int,
    n_results: int = 5,
    seuil: float = 0.5,
    alpha: float = 0.5,
    use_hyde: bool = False,
    use_expansion: bool = False,
    doc_date_filter: str = "",
) -> tuple[List[str], List[str], List[Dict[str, Any]]]:
    """Délègue la recherche hybride au moteur RAG via son endpoint HTTP."""
    data = _post("/rag/search", {
        "collection_name": collection_name,
        "query": query,
        "model": model,
        "context_size": context_size,
        "n_results": n_results,
        "seuil": seuil,
        "alpha": alpha,
        "use_hyde": use_hyde,
        "use_expansion": use_expansion,
        "doc_date_filter": doc_date_filter,
    })
    return data["contexts"], data["sources"], data["detailed_chunks"]
 
 
# ─── Streaming de la réponse ──────────────────────────────────────────────────
 
def stream_answer(
    system_prompt: str,
    query: str,
    model: str,
    context_size: int,
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> Generator[str, None, None]:
    """Diffuse progressivement la réponse backend au fur et à mesure des chunks."""
    payload = {
        "system_prompt": system_prompt,
        "query": query,
        "model": model,
        "context_size": context_size,
        "chat_history": chat_history or [],
    }
    with requests.post(
        f"{BASE_URL}/rag/stream_answer",
        json=payload,
        stream=True,
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
            if chunk:
                yield chunk
 
 
# ─── Prompt système avec instructions de citation ─────────────────────────────
 
def build_system_prompt(context_str: str, chunks: List[Dict[str, Any]]) -> str:
    """Construit le prompt système.
 
    Les chunks sont triés par date décroissante (le plus récent en premier)
    afin que le LLM privilégie naturellement les informations les plus à jour.
    """
    # Trier par doc_date décroissant — les plus récents en tête de contexte
    sorted_chunks = sorted(
        chunks,
        key=lambda c: c.get("doc_date", "") or "",
        reverse=True,
    )
 
    labeled_blocks = []
    for chunk in sorted_chunks:
        source = chunk.get("source", "source inconnue")
        doc_date = chunk.get("doc_date", "")
        doc = chunk.get("document", "")
        date_label = f" | date: {doc_date}" if doc_date else ""
        labeled_blocks.append(f"[SOURCE: {source}{date_label}]\n{doc}")
 
    labeled_context = "\n\n---\n\n".join(labeled_blocks) if labeled_blocks else context_str
 
    return (
        "Tu es un assistant expert RH. Réponds uniquement en te basant sur le contexte suivant.\n\n"
        "RÈGLES IMPORTANTES :\n"
        "1. Donne UNIQUEMENT la valeur ou règle actuellement en vigueur (la plus récente). "
        "Ne mentionne PAS les valeurs historiques ou remplacées, sauf si l'utilisateur le demande explicitement.\n"
        "2. En cas de contradiction entre deux sources, la source avec la date la plus récente fait foi.\n"
        "3. Chaque fois que tu utilises une information, cite sa source avec ce format exact : "
        "[source: nom_du_fichier (Page X)]\n"
        "4. Place la citation juste après la phrase qui utilise l'information.\n"
        "5. Si la réponse n'est pas dans le contexte, dis-le clairement sans inventer.\n\n"
        f"Contexte disponible (trié du plus récent au plus ancien) :\n\n{labeled_context}"
    )
 
 
 
# ─── Parsing des citations dans la réponse ────────────────────────────────────
 
def extract_citations(response: str) -> tuple[str, List[str]]:
    """Extrait les [source: ...] de la réponse et retourne (texte_propre, sources_uniques)."""
    pattern = r'\[source:\s*([^\]]+)\]'
    citations = re.findall(pattern, response, flags=re.IGNORECASE)
    # Dédoublonner en conservant l'ordre
    seen = set()
    unique_citations = []
    for c in citations:
        c_clean = c.strip()
        if c_clean not in seen:
            seen.add(c_clean)
            unique_citations.append(c_clean)
    # Texte sans les balises de citation
    clean_text = re.sub(pattern, '', response, flags=re.IGNORECASE).strip()
    return clean_text, unique_citations


# Côté frontend / wrapper_API.py
def get_available_collection_names() -> list[str]:
    """Extrait les noms utilisables par l'interface depuis les entrées du registre."""
    response = get_registry_collection()  # appel HTTP existant vers /rag/registry_get
    return [entry["nom"] for entry in response.get("registry", [])]



def fetch_full_lexicon(collection_name):
    """Charge le texte complet d'un lexique pour enrichir le transcript."""
    # Remplacez par l'URL de votre API
    url = f"{BASE_URL}/rag/lexique/{collection_name}" 

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get("lexique", [])
    else:
        return []


def filter_relevant_definitions(lexique_complet, texte_source):
    """Filtre de manière stricte (sensible à la casse) pour éviter les faux positifs comme 'va'."""
    lexique_utile = []
    
    for definition in lexique_complet:
        if ":" in definition:
            termes_cles_bruts = definition.split(":")[0].strip()
            
            # On ne prend QUE le premier terme (l'acronyme officiel en majuscules, ex: "VA")
            # Cela évite d'utiliser la variante minuscule "va" si elle est présente dans le dico
            termes = termes_cles_bruts.split()
            if not termes:
                continue
            terme_principal = termes[0] 
            
            # Recherche SENSIBLE à la casse (pas de re.IGNORECASE)
            if re.search(rf'\b{re.escape(terme_principal)}\b', texte_source):
                lexique_utile.append(definition)
                
    return lexique_utile