import streamlit as st
import requests

from transcriber_bundle.transcriber_page import render_transcriber
from agent_summary.script import render_agent_summary

st.title("Transcription & Compte Rendu de réunion avec agents")

render_transcriber()

if st.session_state.transcript_text:
    # --- AFFICHAGE ET RÉSUMÉ ---
    render_agent_summary()
    #st.text("hehehehehehe")
