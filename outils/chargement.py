"""Chargement du jeu de données fil rouge : listings MCNP, mesures, référentiels.

    from outils.chargement import charger_tout
    donnees = charger_tout()
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
DATA = RACINE / "data"

# --------------------------------------------------------------------------
# Listings MCNP
# --------------------------------------------------------------------------

RE_TALLY = re.compile(r"^1tally\s+(?P<numero>\d+)\s+nps\s*=\s*(?P<nps>\d+)", re.M)
RE_DETECTEUR = re.compile(
    r"detector located at x,y,z\s*=\s*"
    r"(?P<x>[-\d.]+E[+-]\d+)\s+(?P<y>[-\d.]+E[+-]\d+)\s+(?P<z>[-\d.]+E[+-]\d+)"
)
RE_TOTAL = re.compile(
    r"^\s+total\s+(?P<valeur>[-\d.]+E[+-]\d+)\s+(?P<erreur>[\d.]+)\s*$", re.M
)
RE_NOM_FICHIER = re.compile(r"C2_phase(?P<phase>\d+)_(?P<hypothese>\w+)\.outp$")


def _lire_texte(chemin: Path) -> str:
    """Lit le listing quel que soit son encodage.

    Les codes de calcul n'écrivent pas tous en UTF-8 : on retombe sur latin-1,
    qui accepte n'importe quel octet, plutôt que de perdre le fichier.
    """
    try:
        return chemin.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return chemin.read_text(encoding="latin-1")


def lire_outp(chemin: str | Path) -> list[dict]:
    """Extrait un enregistrement par détecteur ponctuel d'un listing MCNP.

    Renvoie une liste de dictionnaires. Les blocs incomplets : fichier tronqué
    par l'ordonnanceur, tally sans ligne `total` : sont ignorés silencieusement :
    c'est au niveau du DataFrame qu'on constatera les cas manquants.
    """
    chemin = Path(chemin)
    texte = _lire_texte(chemin)

    correspondance = RE_NOM_FICHIER.search(chemin.name)
    if correspondance is None:
        raise ValueError(f"Nom de fichier inattendu : {chemin.name}")
    phase = int(correspondance["phase"])
    hypothese = correspondance["hypothese"]

    enregistrements = []
    # Chaque bloc va d'un « 1tally » au suivant, et contient l'analyse statistique
    # qui suit immédiatement le tally.
    debuts = [m.start() for m in RE_TALLY.finditer(texte)] + [len(texte)]
    for debut, fin in zip(debuts, debuts[1:]):
        bloc = texte[debut:fin]

        entete = RE_TALLY.search(bloc)
        detecteur = RE_DETECTEUR.search(bloc)
        total = RE_TOTAL.search(bloc)
        if not (entete and detecteur and total):
            continue  # bloc tronqué

        enregistrements.append({
            "fichier": chemin.name,
            "phase": phase,
            "hypothese": hypothese,
            "tally": int(entete["numero"]),
            "nps": int(entete["nps"]),
            "x_cm": float(detecteur["x"]),
            "y_cm": float(detecteur["y"]),
            "z_cm": float(detecteur["z"]),
            "debit_calcule": float(total["valeur"]),
            "erreur_relative": float(total["erreur"]),
            "tests_statistiques_ok": "does not pass" not in bloc,
        })

    return enregistrements


def charger_calculs(dossier: str | Path | None = None,
                    erreur_max: float = 0.10) -> pd.DataFrame:
    """Agrège tous les listings d'un dossier en une table, points de mesure rattachés.

    La colonne `exploitable` marque les enregistrements retenus : tests statistiques
    MCNP passés et erreur relative sous `erreur_max`. On marque, on ne supprime pas.
    """
    dossier = Path(dossier) if dossier else DATA / "calculs"

    lignes = []
    for chemin in sorted(dossier.glob("*.outp")):
        lignes.extend(lire_outp(chemin))

    calculs = pd.DataFrame(lignes)
    points = charger_points(dossier.parent / "points_mesure.csv")

    # Rattachement par coordonnées : les listings ne portent pas l'identifiant du point.
    for table in (calculs, points):
        for axe in ("x_cm", "y_cm", "z_cm"):
            table[axe] = table[axe].round(1)

    calculs = calculs.merge(points, on=["x_cm", "y_cm", "z_cm"], how="left")
    calculs["exploitable"] = (calculs["tests_statistiques_ok"]
                              & (calculs["erreur_relative"] <= erreur_max))
    return calculs


# --------------------------------------------------------------------------
# Campagnes de mesure
# --------------------------------------------------------------------------

LIGNES_ENTETE_APPAREIL = 5  # les 5 lignes « # … » de l'export radiamètre


def lire_mesures(chemin: str | Path) -> pd.DataFrame:
    """Lit un export de radiamètre : cp1252, séparateur `;`, décimale `,`, dates FR."""
    chemin = Path(chemin)
    mesures = pd.read_csv(
        chemin,
        sep=";",
        decimal=",",
        encoding="cp1252",
        skiprows=LIGNES_ENTETE_APPAREIL,
        dtype={"Débit de dose (µSv/h)": "string"},
    )
    mesures.columns = [
        "point", "horodatage", "debit_mesure", "incertitude_pct",
        "hauteur_m", "commentaire",
    ]

    # « < LD » n'est pas un nombre : on garde l'information dans sa propre colonne.
    mesures["sous_limite_detection"] = (
        mesures["debit_mesure"].str.strip().str.startswith("<").fillna(False)
    )
    mesures["debit_mesure"] = pd.to_numeric(
        mesures["debit_mesure"].str.replace(",", ".", regex=False), errors="coerce"
    )

    mesures["horodatage"] = pd.to_datetime(
        mesures["horodatage"], format="%d/%m/%Y %H:%M"
    )
    mesures["campagne"] = mesures["horodatage"].dt.date.min()

    # Un point remesuré le même jour : on garde la dernière mesure.
    mesures = mesures.sort_values("horodatage").drop_duplicates("point", keep="last")

    return mesures.reset_index(drop=True)


def charger_mesures(dossier: str | Path | None = None) -> pd.DataFrame:
    """Concatène les campagnes et leur attribue le numéro de phase du chantier."""
    dossier = Path(dossier) if dossier else DATA / "mesures"

    campagnes = [lire_mesures(chemin) for chemin in sorted(dossier.glob("*.csv"))]
    mesures = pd.concat(campagnes, ignore_index=True)

    # Les campagnes sont chronologiques et correspondent aux phases 0, 1, 2.
    ordre = {date: phase for phase, date in enumerate(sorted(mesures["campagne"].unique()))}
    mesures["phase"] = mesures["campagne"].map(ordre)

    return mesures


# --------------------------------------------------------------------------
# Référentiels
# --------------------------------------------------------------------------

def charger_points(chemin: str | Path | None = None) -> pd.DataFrame:
    return pd.read_csv(chemin or DATA / "points_mesure.csv")


def charger_criteres(chemin: str | Path | None = None) -> dict:
    chemin = Path(chemin) if chemin else DATA / "criteres.json"
    return json.loads(chemin.read_text(encoding="utf-8"))


def charger_plan(chemin: str | Path | None = None) -> dict:
    chemin = Path(chemin) if chemin else DATA / "plan_casemate.json"
    return json.loads(chemin.read_text(encoding="utf-8"))


def charger_postes(chemin: str | Path | None = None) -> pd.DataFrame:
    return pd.read_excel(chemin or DATA / "chantier.xlsx", sheet_name="Postes")


def appliquer_zonage(debits: pd.Series, criteres: dict | None = None) -> pd.Series:
    """Classe des débits de dose en zones réglementaires.

    `pd.cut` fait tout le travail : il suffit de dérouler les bornes du référentiel.
    """
    criteres = criteres or charger_criteres()
    zonage = criteres["zonage"]

    bornes = [zone["min"] for zone in zonage] + [float("inf")]
    etiquettes = [zone["zone"] for zone in zonage]

    return pd.cut(debits, bins=bornes, labels=etiquettes, right=False)


def couleurs_zones(criteres: dict | None = None) -> dict[str, str]:
    criteres = criteres or charger_criteres()
    return {zone["zone"]: zone["couleur"] for zone in criteres["zonage"]}


# --------------------------------------------------------------------------

COLONNES_POSTES = {
    "Id poste": "poste",
    "Phase": "phase",
    "Libellé du poste": "libelle",
    "Point de référence": "point",
    "Durée unitaire (min)": "duree_min",
    "Nb d'interventions": "nb_interventions",
    "Nb d'intervenants": "nb_intervenants",
}


def comparer(calculs: pd.DataFrame, mesures: pd.DataFrame,
             criteres: dict) -> pd.DataFrame:
    """Une ligne par point et par phase : calcul nominal, mesure, débit retenu, zone.

    Le débit retenu pour le zonage est l'enveloppe max(calcul, mesure). C'est un
    choix d'étude conservatif, à documenter dans la note. `max(axis=1)` ignore les
    NaN : quand la mesure est « < LD », c'est le calcul qui est retenu.
    """
    # Seule l'hypothèse nominale est comparable aux mesures terrain.
    nominal = calculs.query("hypothese == 'nominal'")
    comparaison = nominal.merge(
        mesures[["point", "phase", "debit_mesure", "sous_limite_detection"]],
        on=["point", "phase"], how="left",
    )
    # Écart relatif du calcul à la mesure : 0 = concordance, +0,10 = le calcul majore de 10 %.
    comparaison["ecart_relatif"] = (
        (comparaison["debit_calcule"] - comparaison["debit_mesure"]) / comparaison["debit_mesure"]
    )
    comparaison["debit_retenu"] = comparaison[["debit_calcule", "debit_mesure"]].max(axis=1)
    comparaison["zone"] = appliquer_zonage(comparaison["debit_retenu"], criteres)
    return comparaison.sort_values(["phase", "point"]).reset_index(drop=True)


def doses_postes(comparaison: pd.DataFrame, postes: pd.DataFrame,
                 criteres: dict) -> pd.DataFrame:
    """Dose prévisionnelle par poste de travail, et temps de présence maximal.

    La dose individuelle suppose que chaque intervenant est présent pendant toute
    la durée du poste, au débit retenu du point de référence : c'est majorant.
    """
    postes = postes.rename(columns=COLONNES_POSTES)
    postes = postes.merge(comparaison[["point", "phase", "debit_retenu", "zone"]],
                          on=["point", "phase"], how="left")

    contrainte_msv = criteres["contrainte_chantier_mSv"]
    postes["heures"] = postes["duree_min"] * postes["nb_interventions"] / 60
    postes["dose_individuelle_msv"] = postes["debit_retenu"] * postes["heures"] / 1000
    postes["dose_collective_hmsv"] = (postes["dose_individuelle_msv"]
                                      * postes["nb_intervenants"])
    postes["temps_max_h"] = contrainte_msv * 1000 / postes["debit_retenu"]
    postes["conforme"] = postes["dose_individuelle_msv"] <= contrainte_msv
    return postes


def charger_tout(racine: str | Path | None = None) -> dict:
    """Le jeu complet, prêt à l'analyse.

    `racine` est le dossier de données (par défaut `data/`).
    """
    racine = Path(racine) if racine else DATA
    criteres = charger_criteres(racine / "criteres.json")
    calculs = charger_calculs(racine / "calculs",
                              erreur_max=criteres["erreur_relative_max_acceptee"])
    mesures = charger_mesures(racine / "mesures")
    comparaison = comparer(calculs, mesures, criteres)
    postes = charger_postes(racine / "chantier.xlsx")

    return {
        "calculs": calculs,
        "mesures": mesures,
        "comparaison": comparaison,
        "postes": doses_postes(comparaison, postes, criteres),
        "criteres": criteres,
        "plan": charger_plan(racine / "plan_casemate.json"),
        "points": charger_points(racine / "points_mesure.csv"),
    }


def _autotest() -> None:
    calculs = charger_calculs()
    points = charger_points()

    # 12 listings × 32 détecteurs, moins ceux perdus dans le fichier tronqué.
    complets = calculs.groupby("fichier").size()
    assert (complets[complets == len(points)].count()) == 11, complets.to_dict()
    assert complets["C2_phase1_minorant.outp"] < len(points), "le tronqué doit être court"

    # Tous les détecteurs se rattachent à un point du référentiel.
    assert calculs["point"].notna().all(), calculs[calculs["point"].isna()].head()

    # Le fichier latin-1 est lu sans perte de tally.
    assert complets["C2_phase0_majorant.outp"] == len(points)

    # Les tests statistiques ratés sont détectés, et uniquement là où ils ont été injectés.
    rates = calculs[~calculs["tests_statistiques_ok"]]
    assert set(rates["fichier"]) == {"C2_phase2_nominal.outp"}, set(rates["fichier"])
    assert len(rates) == 3, len(rates)

    mesures = charger_mesures()
    assert len(mesures) == 3 * len(points), len(mesures)  # doublon bien éliminé
    assert mesures["sous_limite_detection"].any(), "aucun « < LD » détecté"
    assert mesures.loc[mesures["sous_limite_detection"], "debit_mesure"].isna().all()

    tout = charger_tout()
    comparaison = tout["comparaison"]
    assert comparaison["zone"].notna().all()
    # Le zonage doit couvrir plusieurs zones, sinon l'exercice n'a pas d'objet.
    assert comparaison["zone"].nunique() >= 3, comparaison["zone"].value_counts()
    # Calcul et mesure doivent rester du même ordre de grandeur.
    ecart = comparaison["ecart_relatif"].median()
    assert -0.3 < ecart < 0.5, ecart

    # L'enveloppe ne descend jamais sous le calcul, et reprend le calcul sur les « < LD ».
    assert (comparaison["debit_retenu"] >= comparaison["debit_calcule"]).all()
    ld = comparaison["sous_limite_detection"].fillna(False).astype(bool)
    assert (comparaison.loc[ld, "debit_retenu"] == comparaison.loc[ld, "debit_calcule"]).all()

    # L'arc pédagogique : zone jaune présente en phase 0, disparue en phase 2.
    jaune = comparaison["zone"] == "Contrôlée jaune"
    assert jaune[comparaison["phase"] == 0].any()
    assert not jaune[comparaison["phase"] == 2].any()

    postes = tout["postes"]
    assert len(postes) == 12 and postes["debit_retenu"].notna().all(), postes
    # Il faut au moins un poste non conforme en phase 0, sinon la calculette ALARA
    # n'a rien à montrer.
    assert (~postes.query("phase == 0")["conforme"]).any(), postes

    print(f"autotest : ok : {len(calculs)} enregistrements de calcul, "
          f"{len(mesures)} mesures, écart calcul/mesure médian {ecart:+.0%}, "
          f"{int((~postes['conforme']).sum())} postes non conformes")


if __name__ == "__main__":
    _autotest()
