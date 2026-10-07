"""Plan interactif : cliquer sur un point de la casemate pour voir son historique.

Le clic sur le plan et la liste déroulante désignent le même point : le clic
renseigne la liste. La liste reste utile quand deux points sont trop proches pour
être cliqués séparément, et c'est elle que pilotent les tests automatiques.
"""

import plotly.express as px
import streamlit as st

import commun
from commun import fr
from outils import figures as F

tout = commun.donnees()
comparaison, plan, criteres, postes = (tout["comparaison"], tout["plan"],
                                       tout["criteres"], tout["postes"])

st.title("Plan interactif")

phase = commun.selecteur_phase()
avec_carte = st.sidebar.toggle("Carte interpolée", value=True)

# --------------------------------------------------------------------------
# Le plan, et le point cliqué
# --------------------------------------------------------------------------

figure = F.fig_plan(plan, comparaison, phase, criteres, avec_carte=avec_carte)
evenement = st.plotly_chart(figure, key=f"plan_phase_{phase}", on_select="rerun",
                            selection_mode="points", width="stretch", theme=None)

# Le clic est lu AVANT de créer la liste déroulante : on a le droit d'écrire la
# valeur d'un widget dans session_state tant que ce widget n'a pas encore été
# créé dans l'exécution en cours.
clique = commun.point_du_clic(evenement)
if clique:
    st.session_state["point_choisi"] = clique

identifiants = sorted(comparaison["point"].unique())
if st.session_state.get("point_choisi") not in identifiants:
    st.session_state["point_choisi"] = identifiants[0]

id_point = st.selectbox("Point", identifiants, key="point_choisi",
                        help="Cliquez sur un point du plan, ou choisissez-le ici.")

# --------------------------------------------------------------------------
# La fiche du point
# --------------------------------------------------------------------------

historique = comparaison[comparaison["point"] == id_point].sort_values("phase")
courant = historique[historique["phase"] == phase].iloc[0]

st.subheader(f"{id_point} : {courant['description']} ({courant['local']})")

zone_suivante, facteur = commun.marge_au_seuil(courant["debit_retenu"], criteres)
fiche = st.columns(3)
fiche[0].metric(f"Débit retenu, phase {phase}", f"{fr(courant['debit_retenu'])} µSv/h")
fiche[1].metric("Zone", str(courant["zone"]))
fiche[2].metric("Marge avant la zone supérieure",
                f"× {fr(facteur, 1)}" if facteur else "-",
                help=f"Facteur d'augmentation du débit qui ferait passer en "
                     f"{zone_suivante}" if zone_suivante else None)

gauche, droite = st.columns([3, 2])
with gauche:
    evolution = px.line(historique.assign(etape=historique["phase"].map(commun.LIBELLES_PHASES)),
                        x="etape", y=["debit_calcule", "debit_mesure", "debit_retenu"],
                        markers=True, log_y=True, template="plotly_white",
                        labels={"etape": "", "value": "µSv/h", "variable": ""})
    noms = {"debit_calcule": "calcul", "debit_mesure": "mesure", "debit_retenu": "retenu"}
    evolution.for_each_trace(lambda trace: trace.update(name=noms[trace.name]))
    evolution.update_layout(height=320, margin=dict(t=20))
    st.plotly_chart(evolution, width="stretch", theme=None)

with droite:
    st.dataframe(historique[["phase", "debit_calcule", "debit_mesure",
                             "ecart_relatif", "zone"]],
                 hide_index=True, width="stretch", column_config={
                     "phase": "Phase",
                     "debit_calcule": st.column_config.NumberColumn("Calcul", format="%.2f"),
                     "debit_mesure": st.column_config.NumberColumn("Mesure", format="%.2f"),
                     "ecart_relatif": st.column_config.NumberColumn("Écart", format="percent"),
                     "zone": "Zone"})

rattaches = postes[(postes["point"] == id_point) & (postes["phase"] == phase)]
if not rattaches.empty:
    for _, poste in rattaches.iterrows():
        message = (f"Point de référence du poste {poste['poste']} ({poste['libelle']}) : "
                   f"{fr(poste['dose_individuelle_msv'], 3)} mSv prévus.")
        (st.success if poste["conforme"] else st.error)(message)
