"""Calculette ALARA : dose d'un poste de travail, et effet d'un écran ou d'un recul.

La physique est dans outils/alara.py ; cette page ne fait que l'interface.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

import commun
from commun import fr
from outils import alara

tout = commun.donnees()
postes, plan, criteres = tout["postes"], tout["plan"], tout["criteres"]
contrainte = criteres["contrainte_chantier_mSv"]

st.title("Calculette ALARA")
st.markdown(
    f"Dose prévisionnelle d'un poste de travail, comparée à la contrainte de chantier "
    f"de **{fr(contrainte, 1)} mSv**. Modifiez la distance, l'écran ou la durée pour "
    f"voir l'effet d'une optimisation.")

# --------------------------------------------------------------------------
# Choix du poste
# --------------------------------------------------------------------------

phase = commun.selecteur_phase()
postes_phase = postes.query("phase == @phase").set_index("poste")

id_poste = st.selectbox("Poste de travail", postes_phase.index,
                        format_func=lambda p: f"{p} : {postes_phase.loc[p, 'libelle']}")
poste = postes_phase.loc[id_poste]

point = tout["points"].set_index("point").loc[poste["point"]]
source, distance_reference = alara.source_la_plus_proche(
    plan, point["x_cm"], point["y_cm"], point["z_cm"])

st.caption(f"Point de référence {poste['point']} : {fr(poste['debit_retenu'])} µSv/h, "
           f"à {fr(distance_reference)} m de la source la plus proche "
           f"({source['libelle']}, {source['isotope']}).")

# --------------------------------------------------------------------------
# Paramètres
# --------------------------------------------------------------------------

gauche, droite = st.columns(2)
with gauche:
    # Valeur par défaut exacte, et non arrondie : sinon le débit affiché à l'ouverture
    # différerait déjà du débit de référence, sans que l'utilisateur ait rien changé.
    distance = st.number_input("Distance à la source (m)", min_value=0.3, max_value=10.0,
                               value=float(distance_reference), step=0.1, format="%.2f")
    epaisseur = st.slider("Écran de plomb (cm)", min_value=0.0, max_value=5.0,
                          value=0.0, step=0.5)
with droite:
    duree = st.number_input("Durée totale d'intervention (h)", min_value=0.1,
                            max_value=100.0, value=float(poste["heures"]), step=0.5)
    intervenants = st.number_input("Nombre d'intervenants", min_value=1, max_value=10,
                                   value=int(poste["nb_intervenants"]), step=1)

debit = alara.debit_au_poste(poste["debit_retenu"], distance_reference, distance,
                             source["isotope"], epaisseur)
resultat = alara.bilan(debit, duree, intervenants, contrainte)

# --------------------------------------------------------------------------
# Résultats
# --------------------------------------------------------------------------

indicateurs = st.columns(3)
indicateurs[0].metric("Débit au poste", f"{fr(debit, 1)} µSv/h",
                      delta=f"{fr(debit - poste['debit_retenu'], 1, signe=True)} µSv/h",
                      delta_color="inverse", help="Écart au débit du point de référence")
indicateurs[1].metric("Dose individuelle", f"{fr(resultat['dose_individuelle_msv'], 3)} mSv",
                      delta=f"{fr(-resultat['marge_msv'], 3, signe=True)} mSv / contrainte",
                      delta_color="inverse",
                      help="Écart à la contrainte : négatif, le poste est sous la contrainte")
indicateurs[2].metric("Temps de présence maximal", f"{fr(resultat['temps_max_h'], 1)} h",
                      help="Temps au bout duquel la contrainte est atteinte")

if resultat["conforme"]:
    st.success("Le poste respecte la contrainte de chantier.")
else:
    st.error("Le poste dépasse la contrainte de chantier : une optimisation est nécessaire.")
    minimale = alara.epaisseur_minimale(debit, source["isotope"], duree, contrainte)
    if minimale is not None:
        st.info(f"Un écran de plomb supplémentaire de {fr(minimale, 1)} cm suffirait à "
                f"ramener la dose sous la contrainte.")

st.caption(f"Dose collective : {fr(resultat['dose_collective_hmsv'], 3)} h·mSv "
           f"({intervenants} intervenant(s)).")

with st.expander("Hypothèses du calcul"):
    st.markdown(
        "- Le débit du point de référence est attribué **en entier** à la source la "
        "plus proche : approximation valable quand cette source domine.\n"
        "- S'éloigner de la source réduit le débit en **1/d²**.\n"
        "- L'écran de plomb est traité avec le facteur d'accumulation linéaire "
        "B = 1 + µx, qui **surestime** l'accumulation dans le plomb : le résultat est "
        "majorant.\n"
        "- Chaque intervenant est présent pendant toute la durée indiquée.")

# --------------------------------------------------------------------------
# Comparaison de configurations
# --------------------------------------------------------------------------

st.subheader("Comparer des configurations")

# st.session_state survit aux réexécutions du script : c'est là qu'on garde
# les configurations déjà essayées.
if "configurations" not in st.session_state:
    st.session_state["configurations"] = []

boutons = st.columns([1, 1, 3])
if boutons[0].button("Ajouter à la comparaison", type="primary"):
    st.session_state["configurations"].append({
        "configuration": f"{id_poste} · {fr(distance, 2)} m · {fr(epaisseur, 1)} cm Pb",
        "debit_usv_h": round(float(debit), 2),
        "dose_msv": round(float(resultat["dose_individuelle_msv"]), 3),
        "conforme": bool(resultat["conforme"]),
    })
if boutons[1].button("Vider"):
    st.session_state["configurations"] = []

if st.session_state["configurations"]:
    comparees = pd.DataFrame(st.session_state["configurations"])
    st.dataframe(comparees, hide_index=True, width="stretch", column_config={
        "configuration": "Configuration",
        "debit_usv_h": st.column_config.NumberColumn("Débit (µSv/h)", format="%.2f"),
        "dose_msv": st.column_config.NumberColumn("Dose (mSv)", format="%.3f"),
        "conforme": st.column_config.CheckboxColumn("Conforme"),
    })
    figure = px.bar(comparees, x="configuration", y="dose_msv",
                    color=comparees["conforme"].map({True: "conforme", False: "hors contrainte"}),
                    color_discrete_map={"conforme": "#2E9E5B", "hors contrainte": "#D0342C"},
                    labels={"configuration": "", "dose_msv": "Dose individuelle (mSv)",
                            "color": ""}, template="plotly_white")
    figure.add_hline(y=contrainte, line_dash="dash", line_color="red",
                     annotation_text="contrainte")
    st.plotly_chart(figure, width="stretch", theme=None)
else:
    st.caption("Aucune configuration enregistrée : réglez les paramètres puis cliquez "
               "sur « Ajouter à la comparaison ».")
