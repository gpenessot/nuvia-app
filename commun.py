"""Ce que toutes les pages de l'application partagent.

Chemins, chargement des données mis en cache, sélecteur de phase, et les petites
fonctions de logique pure (sans Streamlit) que les pages appellent. Ces fonctions
se testent sans lancer l'application.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from outils import figures as F                      # noqa: E402
from outils.chargement import charger_tout           # noqa: E402

LIBELLES_PHASES = F.LIBELLES_PHASES


# --------------------------------------------------------------------------
# Données
# --------------------------------------------------------------------------

@st.cache_data(show_spinner="Chargement des données de l'étude…")
def donnees() -> dict:
    """Toutes les données de l'étude, chargées une seule fois par session serveur."""
    return charger_tout(DATA)


def selecteur_phase(cle: str = "phase") -> int:
    """Choix de la phase dans la barre latérale, commun à plusieurs pages."""
    return st.sidebar.radio("Phase du chantier", options=list(LIBELLES_PHASES),
                            format_func=LIBELLES_PHASES.get, key=cle)


# --------------------------------------------------------------------------
# Logique pure, testable sans Streamlit
# --------------------------------------------------------------------------

def fr(valeur: float, decimales: int = 2, signe: bool = False) -> str:
    """Nombre à la française : `fr(0.3, 1)` donne « 0,3 », `fr(2, 1, signe=True)` « +2,0 »."""
    texte = f"{valeur:+.{decimales}f}" if signe else f"{valeur:.{decimales}f}"
    return texte.replace(".", ",")


def point_du_clic(evenement) -> str | None:
    """Identifiant du point cliqué sur le plan, ou None.

    Chaque point du plan porte son identifiant en premier élément de `customdata`
    (voir `figures.fig_plan`). Un clic sur la carte, un mur ou un équipement ne
    porte pas de `customdata` : on l'ignore.
    """
    if not evenement:
        return None
    for point in evenement.get("selection", {}).get("points", []):
        donnees_point = point.get("customdata")
        if donnees_point:
            return donnees_point[0]
    return None


def marge_au_seuil(debit: float, criteres: dict) -> tuple[str | None, float | None]:
    """Zone immédiatement supérieure, et facteur qui sépare le débit de son seuil.

    Un facteur de 3 signifie que le débit devrait tripler pour changer de zone.
    Exprimé en facteur plutôt qu'en écart : c'est ainsi qu'évolue un débit.
    """
    for zone in criteres["zonage"]:
        if zone["min"] > debit:
            return zone["zone"], zone["min"] / debit
    return None, None


COLONNES_CLASSEUR = ["phase", "point", "local", "description", "debit_calcule",
                     "debit_mesure", "ecart_relatif", "debit_retenu", "zone",
                     "exploitable"]


def lire_classeur(fichier) -> pd.DataFrame:
    """Lit la feuille Comparaison d'un classeur produit par la page Livrables.

    Lève ValueError avec un message lisible si le classeur n'a pas la forme
    attendue : c'est ce message que la page affiche à l'utilisateur.
    """
    try:
        table = pd.read_excel(fichier, sheet_name="Comparaison")
    except ValueError as erreur:
        raise ValueError("le classeur n'a pas de feuille « Comparaison »") from erreur
    manquantes = [c for c in COLONNES_CLASSEUR if c not in table.columns]
    if manquantes:
        raise ValueError(f"colonnes manquantes : {', '.join(manquantes)}")
    return table
