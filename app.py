"""Application de la casemate C2 : point d'entrée.

Depuis la racine du dépôt :

    streamlit run app.py

Ce fichier ne fait que déclarer les pages. Chaque page est un script à part,
dans le dossier pages/, que Streamlit exécute quand on la choisit dans le menu.
"""

import hmac
import sys
from pathlib import Path

import streamlit as st

# Les pages importent `commun`, qui est dans ce dossier.
sys.path.insert(0, str(Path(__file__).parent))

st.set_page_config(page_title="Casemate C2", page_icon="☢️", layout="wide")


def connexion() -> None:
    """Arrête l'application tant qu'un compte de la section [comptes] des secrets
    n'a pas été saisi. Sans secrets, personne n'entre."""
    if st.session_state.get("utilisateur"):
        return
    try:
        comptes = dict(st.secrets["comptes"])
    except Exception:
        comptes = {}
    with st.form("connexion"):
        nom = st.text_input("Utilisateur")
        mdp = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Se connecter"):
            attendu = str(comptes.get(nom, ""))
            if attendu and hmac.compare_digest(mdp.encode(), attendu.encode()):
                st.session_state["utilisateur"] = nom
                st.rerun()
            st.error("Identifiants incorrects.")
    st.stop()


connexion()

navigation = st.navigation([
    st.Page("pages/accueil.py", title="Accueil", icon=":material/home:", default=True),
    st.Page("pages/calculette.py", title="Calculette ALARA", icon=":material/calculate:"),
    st.Page("pages/tableau_de_bord.py", title="Tableau de bord", icon=":material/dashboard:"),
    st.Page("pages/plan.py", title="Plan interactif", icon=":material/map:"),
    st.Page("pages/rapport.py", title="Livrables", icon=":material/description:"),
])
navigation.run()
