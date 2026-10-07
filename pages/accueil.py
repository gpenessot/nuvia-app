"""Page d'accueil : le chantier en quelques chiffres."""

import pandas as pd
import streamlit as st

import commun

tout = commun.donnees()
comparaison, calculs = tout["comparaison"], tout["calculs"]

st.title("Casemate C2 : cartographie radiologique")
st.markdown(
    "Chantier de démantèlement de la **casemate C2**, suivi sur trois phases. "
    "Chaque phase croise des **calculs MCNP** et une **campagne de mesure** au "
    "radiamètre, sur les mêmes 32 points.")

jaune = comparaison[comparaison["zone"] == "Contrôlée jaune"].groupby("phase").size()

colonnes = st.columns(4)
colonnes[0].metric("Points de mesure", comparaison["point"].nunique())
colonnes[1].metric("Calculs exploitables",
                   f"{int(calculs['exploitable'].sum())} / {len(calculs)}")
colonnes[2].metric("Écart calcul / mesure médian",
                   f"{comparaison['ecart_relatif'].median():+.0%}".replace("%", "\u00a0%"))
colonnes[3].metric("Points en zone jaune, phase 2", int(jaune.get(2, 0)),
                   delta=int(jaune.get(2, 0) - jaune.get(0, 0)), delta_color="inverse",
                   help="Variation par rapport à la phase 0")

st.subheader("Les phases du chantier")
st.dataframe(pd.DataFrame({"Phase": list(commun.LIBELLES_PHASES.values()),
                           "Points en zone jaune": [int(jaune.get(p, 0)) for p in range(3)]}),
             hide_index=True)

st.subheader("Ce que propose l'application")
st.markdown("""
| Page | À quoi elle sert |
|---|---|
| **Calculette ALARA** | dose prévisionnelle d'un poste, effet d'un écran de plomb ou d'un éloignement |
| **Tableau de bord** | explorer les résultats, filtrer, comparer calcul et mesure |
| **Plan interactif** | cliquer sur un point du local pour voir son historique |
| **Livrables** | générer et télécharger la note, le classeur et la synthèse |
""")
st.caption("Données fictives : formation Python NUVIA 2026.")
