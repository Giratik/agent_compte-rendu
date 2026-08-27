
import streamlit as st
import re

# Configuration de la page
st.set_page_config(
    page_title="Changelog",
    page_icon="📜",
    layout="centered"
)

# Style CSS personnalisé pour ajouter une touche "Tech" (bordure gauche colorée)
st.markdown("""
    <style>
    /* Donne un style d'alerte discret aux blocs de citation dans le markdown */
    blockquote {
        border-left: 4px solid #FF4B4B !important;
        background-color: rgba(255, 75, 75, 0.05);
        padding: 5px 15px;
        border-radius: 4px;
    }
    </style>
""", unsafe_allow_html=True)

# En-tête de la page
st.title("📜 Journal des modifications")
#st.write("Retrouvez ici l'historique des déploiements, les nouvelles fonctionnalités et les correctifs.")
st.markdown("---")

try:
    with open("changelog.md", "r", encoding="utf-8") as f:
        content = f.read()

    # Découpage du fichier Markdown par version (repère les lignes commençant par ##)
    # Le regex gère les sauts de ligne pour isoler proprement chaque bloc
    versions = re.split(r'(?=\n##\s)', '\n' + content.strip())

    for idx, version_block in enumerate(versions):
        if not version_block.strip():
            continue
            
        lines = version_block.strip().split('\n')
        # On extrait le titre de la version (en enlevant les '##')
        version_title = lines[0].replace("##", "").strip()
        # Le reste devient le corps du texte
        version_body = "\n".join(lines[1:])

        # Affichage sous forme de carte (Container avec bordure)
        # La version la plus récente (la première) se démarque subtilement
        if idx == 1: # idx == 1 car le split peut générer un premier élément vide ou d'en-tête
            with st.container(border=True):
                st.subheader(f"{version_title}")
                st.caption("Dernière mise à jour")
                st.markdown(version_body)
        else:
            with st.container(border=True):
                st.subheader(f"{version_title}")
                st.markdown(version_body)
                
        st.write("") # Espace entre les cartes

except FileNotFoundError:
    st.error("Le fichier `CHANGELOG.md` n'a pas été trouvé à la racine du projet.")