"""Livrables : générer la note, le classeur et la synthèse, puis les télécharger.

La production vient de outils/livrables.py. La page l'appelle dans un
dossier temporaire, garde les fichiers en mémoire, et propose de les télécharger.
"""

import tempfile
from pathlib import Path

import streamlit as st

import commun
from outils.livrables import produire_livrables

st.title("Livrables de l'étude")
st.markdown(
    "Génère les quatre livrables de la phase choisie et les propose au "
    "téléchargement.")

phase = commun.selecteur_phase()
modele = st.checkbox("Utiliser le modèle Word de l'entité", value=True)

TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".html": "text/html",
}

if st.button("Générer les livrables", type="primary"):
    with st.spinner("Production en cours : figures, classeur, note, synthèse…"):
        with tempfile.TemporaryDirectory() as dossier:
            fichiers = produire_livrables(
                commun.DATA, phase, dossier,
                commun.DATA / "modele_note.docx" if modele else None)
            # Le dossier temporaire disparaît à la sortie du bloc : on lit les
            # fichiers en mémoire avant, et on les garde dans session_state.
            st.session_state["livrables"] = {
                "phase": phase,
                "fichiers": {chemin.name: chemin.read_bytes() for chemin in fichiers.values()},
            }

produits = st.session_state.get("livrables")
if produits and produits["phase"] == phase:
    st.success(f"Livrables de la phase {phase} prêts.")
    for nom, contenu in produits["fichiers"].items():
        st.download_button(f"Télécharger {nom}", data=contenu, file_name=nom,
                           mime=TYPES[Path(nom).suffix], key=f"telecharger_{nom}")
elif produits:
    st.info(f"Les livrables en mémoire concernent la phase {produits['phase']}. "
            f"Cliquez sur « Générer » pour produire ceux de la phase {phase}.")
