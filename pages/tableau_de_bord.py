"""Tableau de bord : explorer les résultats de l'étude, filtrer, comparer.

Les données viennent soit de l'étude de référence, soit d'un classeur produit par
la page Livrables et déposé par l'utilisateur.
"""

import streamlit as st

import commun
from commun import fr
from outils import figures as F

tout = commun.donnees()
criteres = tout["criteres"]

st.title("Tableau de bord")

# --------------------------------------------------------------------------
# Source des données
# --------------------------------------------------------------------------

depot = st.sidebar.file_uploader("Classeur d'une autre étude (facultatif)", type="xlsx",
                                 help="Un cartographie.xlsx produit par la page Livrables")
if depot is None:
    comparaison = tout["comparaison"]
    st.caption("Données : étude de référence de la casemate C2.")
else:
    try:
        comparaison = commun.lire_classeur(depot)
    except ValueError as erreur:
        st.error(f"Classeur illisible : {erreur}.")
        st.stop()
    st.caption(f"Données : {depot.name}.")

# --------------------------------------------------------------------------
# Filtres
# --------------------------------------------------------------------------

st.sidebar.header("Filtres")
phases = st.sidebar.multiselect("Phases", options=sorted(comparaison["phase"].unique()),
                                default=sorted(comparaison["phase"].unique()),
                                format_func=commun.LIBELLES_PHASES.get)
locaux = st.sidebar.multiselect("Locaux", options=sorted(comparaison["local"].unique()),
                                default=sorted(comparaison["local"].unique()))
ordre_zones = [z["zone"] for z in criteres["zonage"]]
zones = st.sidebar.multiselect("Zones", options=[z for z in ordre_zones
                                                 if z in set(comparaison["zone"])],
                               default=[z for z in ordre_zones if z in set(comparaison["zone"])])
exploitables = st.sidebar.checkbox("Calculs exploitables seulement", value=False)

filtre = (comparaison["phase"].isin(phases) & comparaison["local"].isin(locaux)
          & comparaison["zone"].isin(zones))
if exploitables:
    filtre &= comparaison["exploitable"]
selection = comparaison[filtre]

if selection.empty:
    st.warning("Aucun point ne correspond aux filtres choisis.")
    st.stop()

# --------------------------------------------------------------------------
# Indicateurs
# --------------------------------------------------------------------------

ecart = selection["ecart_relatif"].dropna()
indicateurs = st.columns(4)
indicateurs[0].metric("Lignes sélectionnées", len(selection))
indicateurs[1].metric("Débit retenu maximal", f"{fr(selection['debit_retenu'].max(), 1)} µSv/h")
indicateurs[2].metric("Écart calcul / mesure médian",
                      f"{ecart.median():+.0%}".replace("%", " %") if len(ecart) else "-")
indicateurs[3].metric("Points à ±30 %",
                      f"{(ecart.abs() <= 0.30).mean():.0%}".replace("%", " %")
                      if len(ecart) else "-")

# --------------------------------------------------------------------------
# Onglets
# --------------------------------------------------------------------------

tableau, evolution, qualification, zonage = st.tabs(
    ["Tableau", "Évolution", "Calcul / mesure", "Zonage"])

with tableau:
    colonnes = ["phase", "point", "local", "description", "debit_calcule", "debit_mesure",
                "ecart_relatif", "debit_retenu", "zone", "exploitable"]
    st.dataframe(selection[colonnes], hide_index=True, width="stretch", column_config={
        "phase": st.column_config.NumberColumn("Phase", format="%d"),
        "point": "Point",
        "local": "Local",
        "description": "Description",
        "debit_calcule": st.column_config.NumberColumn("Calcul (µSv/h)", format="%.2f"),
        "debit_mesure": st.column_config.NumberColumn("Mesure (µSv/h)", format="%.2f"),
        "ecart_relatif": st.column_config.NumberColumn(
            "Écart calcul / mesure", format="percent",
            help="(calcul - mesure) / mesure ; 0 % = concordance"),
        "debit_retenu": st.column_config.NumberColumn("Retenu (µSv/h)", format="%.2f"),
        "zone": "Zone",
        "exploitable": st.column_config.CheckboxColumn("Exploitable"),
    })
    st.download_button("Télécharger la sélection (CSV)",
                       data=selection[colonnes].to_csv(sep=";", decimal=",", index=False)
                                                .encode("utf-8-sig"),
                       file_name="selection_casemate_c2.csv", mime="text/csv")

with evolution:
    st.plotly_chart(F.fig_evolution(selection, criteres), width="stretch", theme=None)

with qualification:
    if selection["debit_mesure"].notna().any():
        st.plotly_chart(F.fig_calcul_mesure(selection), width="stretch", theme=None)
    else:
        st.info("Aucune mesure dans la sélection.")

with zonage:
    st.plotly_chart(F.fig_zonage(selection, criteres), width="stretch", theme=None)
