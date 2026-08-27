"""Point d'entrée Streamlit : initialise l'état puis lance la navigation."""

import os
import streamlit as st
import uuid

from utility.session_state_central_cr import SK, get, set as ss_set, init_session_state, set_rag_config, set_rag_collections
# from config.Configuration import set_rag_stats
from plugins.wrapper_API import get_available_collection_names
from ui.ui_sidebar import render_sidebar

LOGO_PATH = "ressources/logo_EDP/Eau_de_Paris_bleu.svg.png"
IS_DEV = os.environ.get("IS_DEV", "no")

st.set_page_config(page_title="Analyse de compte-rendu CrewAI", page_icon=":material/robot_2:", layout="wide")
if os.path.exists(LOGO_PATH):
    st.logo(LOGO_PATH)

# ─── ROUTAGE ET NAVIGATION ─────────────────────────────────────────────
def main():
    """Prépare la session et exécute la page sélectionnée par l'utilisateur."""
    init_session_state()
    u = get_available_collection_names()
    set_rag_collections(u)
    

    verbosity, agent_order = render_sidebar()
    ss_set(SK.VERBOSITY, verbosity)
    ss_set(SK.AGENT_ORDER, agent_order)
    # Déclaration des pages
    page_CR = st.Page("pages/main_page.py", title="Rédacteur Compte-rendu", default=True, icon=":material/smart_toy:")
    page_changelog = st.Page("pages/changelog.py", title="Changelog", icon=":material/description:")
    page_test_lien_qdrant = st.Page("pages/test_lien_qdrant.py", title="test lien qdrant", icon=":material/manufacturing:")
    #page_config = st.Page("config/Configuration.py", title="Configuration", icon="⚙️")

    # Construction dynamique de la navigation
    pages_visibles = [page_CR]
    pages_visibles.append(page_changelog)

    # Ajout conditionnel de la page de config
    if IS_DEV == "yes":
        pages_visibles.append(page_test_lien_qdrant)
    #    pages_visibles.append(page_config)
#
    # Exécution de la navigation
    pg = st.navigation(pages_visibles)
    pg.run()

if __name__ == "__main__":
    main()