import streamlit as st
import requests
import json


# Assurez-vous d'importer votre fonction client
from plugins.wrapper_API import get_registry_collection, get_available_collection_names

def obtenir_description_collections_dynamique() -> str:
    """
    Récupère dynamiquement les noms et descriptions des collections
    depuis la collection '_registry' de Qdrant via l'API backend.
    """
    try:
        response = get_registry_collection()
        registry_entries = response.get("registry", [])
        collections_dispos = []
        for entry in registry_entries:
            if entry.get("nom") and entry.get("description"):
                collections_dispos.append({
                    "nom": entry["nom"],
                    "description": entry["description"]
                })

        # Si le registre est vide, utiliser des valeurs par défaut
        if not collections_dispos:
            return "Nom de la collection dans laquelle chercher. (Attention: aucune collection disponible dans le registre)."

        # Construction de la chaîne de texte détaillée pour le LLM
        texte_description = "Nom de la collection dans laquelle chercher. Voici les choix obligatoires :\n"
        for col in collections_dispos:
            texte_description += f"- '{col['nom']}' : à utiliser pour des recherches concernant {col['description']}.\n"

        return texte_description

    except Exception as e:
        print(f"Erreur lors de la récupération du registre: {str(e)}")
        # Fallback de sécurité générique en cas d'erreur de connexion à Qdrant
        return (
            "Erreur. qdrant est injoinable"
        )

def build_qdrant_tools():
    # On génère la description dynamique
    description_dynamique = obtenir_description_collections_dynamique()
    
    # On insère cette description dans le schéma
    outils = [
        {
            "type": "function",
            "function": {
                "name": "rechercher_dans_qdrant",
                "description": "Recherche des informations dans la base de données de l'entreprise.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "collection_name": {
                            "type": "string",
                            "description": description_dynamique # ⬅️ INJECTION ICI
                        },
                        "query": {
                            "type": "string",
                            "description": "La requête ou les mots-clés optimisés pour la recherche."
                        }
                    },
                    "required": ["collection_name", "query"]
                }
            }
        }
    ]
    return outils


st.set_page_config(page_title="Test Tool Calling", page_icon="🕵️‍♂️", layout="wide")

st.title("🕵️‍♂️ Débogueur de Tool Calling (Connecté au vrai Backend)")
st.markdown("Cette page teste le comportement du LLM et interroge **votre véritable base Qdrant** via votre route API `/rag/search`.")

with st.sidebar:
    st.header("⚙️ Configuration")
    ollama_url = st.text_input("URL Ollama", value="http://10.75.12.5:11434", help="L'adresse de votre serveur Ollama.")
    backend_url = st.text_input("URL Backend API", value="http://10.75.12.5:8000", help="L'adresse de votre backend FastAPI.")
    modele = st.text_input("Modèle", value="gemma4:e4b")

# Définition de l'outil par défaut
default_tools = get_available_collection_names()
#st.write("DEBUG tools:", default_tools)

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Le schéma de l'outil (Tools)")
    tools_str = st.text_area("Modifiez la description pour tester comment le LLM réagit :", 
                             value=json.dumps(default_tools, indent=4, ensure_ascii=False), 
                             height=350)
    
