"""Page principale réunissant la saisie du transcript et son analyse."""

import streamlit as st
import requests

from transcriber_bundle.transcriber_page import render_transcriber
from agent_summary.script import render_agent_summary
from utility.session_state_central_cr import SK, get, set as ss_set

st.title("Transcription & Compte Rendu de réunion avec agents")

user_input = st.text_area(label= "écrivez ici des instructions de rédaction pour l'IA")
ss_set(SK.USER_INPUT, user_input)
render_transcriber()

# Le résumé n'est rendu qu'après la présence d'un transcript exploitable.
if get(SK.TRANSCRIPT_TEXT):
    # --- AFFICHAGE ET RÉSUMÉ ---
    render_agent_summary()
    #st.text("hehehehehehe")
