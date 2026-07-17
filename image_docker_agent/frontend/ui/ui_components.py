import json
import re
import ast
import streamlit as st

def render_preview(raw_json: str):
    """Génère l'aperçu du compte-rendu final à partir du JSON brut."""
    if not raw_json:
        return
        
    text = raw_json.strip()
    
    # 1. Nettoyage des balises markdown potentielles
    text = re.sub(r"^```(json)?\n?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\n?```$", "", text, flags=re.MULTILINE)
    
    # 2. Isolement du dictionnaire principal
    start_idx = text.find('{')
    if start_idx != -1:
        depth = 0
        end_idx = -1
        for i in range(start_idx, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break  # On s'arrête net dès que le premier bloc est fermé
        
        if end_idx != -1:
            text = text[start_idx:end_idx + 1]
        
    # 3. Correction des virgules traînantes (trailing commas) - erreur classique des LLM
    text = re.sub(r',\s*([\]}])', r'\1', text)
        
    data = None
    try:
        # strict=False permet d'ignorer certaines erreurs mineures de formatage (ex: sauts de ligne)
        data = json.loads(text, strict=False)
    except json.JSONDecodeError:
        # 4. Fallback : ast.literal_eval pour tolérer les guillemets simples ou clés sans guillemets
        try:
            # Remplacements pour que la syntaxe JSON corresponde à la syntaxe Python
            text_ast = re.sub(r'\btrue\b', 'True', text)
            text_ast = re.sub(r'\bfalse\b', 'False', text_ast)
            text_ast = re.sub(r'\bnull\b', 'None', text_ast)
            data = ast.literal_eval(text_ast)
        except Exception:
            st.error("Impossible d'afficher l'aperçu : le JSON ne peut pas être lu par l'interface.")
            with st.expander("Voir le texte brut reçu (Debug)"):
                st.code(raw_json, language="text")
            return

    if not isinstance(data, dict):
        st.error("L'aperçu n'est pas disponible (les données extraites ne sont pas un dictionnaire valide).")
        return

    st.markdown(f"<h2 style='text-align: center;'>{data.get('titre', 'Compte-rendu')}</h2>", unsafe_allow_html=True)
    if data.get("date"):
        st.markdown(f"<p style='text-align: center; font-style: italic;'>{data['date']}</p>", unsafe_allow_html=True)

    st.markdown("### Participants")
    if data.get("participants"):
        for p in data["participants"]: st.markdown(f"- {p}")
    else:
        st.markdown("Non précisé.")

    if data.get("absents"):
        st.markdown("#### Absents / excusés")
        for a in data["absents"]: st.markdown(f"- {a}")

    st.markdown("### Objectif de la réunion")
    st.markdown(data.get("objectif") or "Non précisé.")

    st.markdown("### Points clés abordés")
    if data.get("points_cles"):
        for pc in data["points_cles"]: st.markdown(f"- {pc}")
    else:
        st.markdown("Non précisé.")

    st.markdown("### Outils & chiffres associés")
    if data.get("outils_et_chiffres"):
        for item in data["outils_et_chiffres"]:
            outil = item.get("outil", "") if isinstance(item, dict) else str(item)
            chiffres = item.get("chiffres_associes", []) if isinstance(item, dict) else []
            st.markdown(f"**{outil}**")
            if chiffres:
                for c in chiffres: st.markdown(f"- {c}")
            else:
                st.markdown("- Aucun chiffre associé.")
    else:
        st.markdown("Aucun outil mentionné.")

    if data.get("autres_chiffres"):
        st.markdown("#### Autres chiffres clés")
        for c in data["autres_chiffres"]: st.markdown(f"- {c}")

    st.markdown("### Décisions prises")
    if data.get("decisions"):
        for d in data["decisions"]: st.markdown(f"- {d}")
    else:
        st.markdown("Aucune décision actée.")

    st.markdown("### Actions à faire")
    if data.get("actions"):
        st.markdown("| Action | Responsable | Échéance |\n|---|---|---|")
        for a in data["actions"]:
            action = str(a.get("action", "")).replace('\n', ' ')
            resp = str(a.get("responsable", "") or "Non précisé").replace('\n', ' ')
            ech = str(a.get("echeance", "") or "Non précisée").replace('\n', ' ')
            st.markdown(f"| {action} | {resp} | {ech} |")
    else:
        st.markdown("Aucune action identifiée.")

    st.markdown("### Points de blocage / questions ouvertes")
    if data.get("points_de_blocage"):
        for pt in data["points_de_blocage"]: st.markdown(f"- {pt}")
    else:
        st.markdown("Aucun point de blocage identifié.")