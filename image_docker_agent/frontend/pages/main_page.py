import streamlit as st
import requests

from transcriber_bundle.transcriber_page import render_transcriber
from agent_summary.script import render_agent_summary
from utility.session_state_central_cr import SK, get

st.title("Transcription & Compte Rendu de réunion avec agents")

render_transcriber()

if get(SK.TRANSCRIPT_TEXT):
    # --- AFFICHAGE ET RÉSUMÉ ---
    render_agent_summary()
    #st.text("hehehehehehe")
