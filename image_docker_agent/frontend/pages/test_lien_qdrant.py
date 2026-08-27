"""Page de diagnostic développeur pour vérifier le registre et le lexique Qdrant."""

import streamlit as st
import requests
import json


# Assurez-vous d'importer votre fonction client
from plugins.wrapper_API import get_available_collection_names, fetch_full_lexicon
from utility.session_state_central_cr import SK, get, set as ss_set, init_session_state, set_rag_config, set_rag_collections, get_rag_collections


st.set_page_config(page_title="Test Tool Calling", page_icon="🕵️‍♂️", layout="wide")

st.title("🕵️‍♂️ Débogueur de Tool Calling (Connecté au vrai Backend)")
st.markdown("Cette page teste le comportement du LLM et interroge **votre véritable base Qdrant** via votre route API `/rag/search`.")

# Définition de l'outil par défaut
default_tools = get_available_collection_names()

set_rag_collections(default_tools)
st.write(default_tools)

for element in default_tools:
    if element == "lexique":
        st.write(fetch_full_lexicon(element))
