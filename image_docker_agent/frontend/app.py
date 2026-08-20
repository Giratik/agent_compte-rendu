import os
import streamlit as st
import uuid

from utility.session_state_central_cr import SK, get, set as ss_set, init_session_state
# from config.Configuration import set_rag_stats
from ui.ui_sidebar import render_sidebar

LOGO_PATH = "ressource/Eau_de_Paris_bleu.svg.png"
IS_DEV = os.environ.get("IS_DEV", "no")

st.set_page_config(page_title="Analyse de compte-rendu CrewAI", page_icon="📄", layout="wide")


# ─── ROUTAGE ET NAVIGATION ─────────────────────────────────────────────
def main():
    init_session_state()
    

    verbosity, agent_order = render_sidebar()
    ss_set(SK.VERBOSITY, verbosity)
    ss_set(SK.AGENT_ORDER, agent_order)
    # Déclaration des pages
    page_CR = st.Page("pages/main_page.py", title="Rédacteur Compte-rendu", default=True)
    page_changelog = st.Page("pages/test_lien_qdrant.py", title="Changelog", icon="📝")
    #page_config = st.Page("config/Configuration.py", title="Configuration", icon="⚙️")

    # Construction dynamique de la navigation
    pages_visibles = [page_CR]

    # Ajout conditionnel de la page de config
    if IS_DEV == "yes":
        pages_visibles.append(page_changelog)
    #    pages_visibles.append(page_config)
#
    # Exécution de la navigation
    pg = st.navigation(pages_visibles)
    pg.run()

if __name__ == "__main__":
    main()