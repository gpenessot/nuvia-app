"""Figures Plotly de l'étude de la casemate C2.

Toutes les fonctions renvoient une `plotly.graph_objects.Figure` : on l'exporte en HTML ou en PNG, ou on la passe à Streamlit.
"""

from __future__ import annotations

import threading
import warnings
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

GABARIT = "plotly_white"
LIBELLES_PHASES = {0: "Phase 0 : état initial",
                   1: "Phase 1 : équipements retirés",
                   2: "Phase 2 : surfaces assainies"}


def _seuils(criteres: dict) -> list[tuple[float, str]]:
    """Les bornes basses des zones réglementaires, hors zone non réglementée."""
    return [(zone["min"], zone["zone"]) for zone in criteres["zonage"] if zone["min"] > 0]


def _ordre_zones(criteres: dict) -> list[str]:
    return [zone["zone"] for zone in criteres["zonage"]]


def _couleurs(criteres: dict) -> dict[str, str]:
    return {zone["zone"]: zone["couleur"] for zone in criteres["zonage"]}


# --------------------------------------------------------------------------
# Figures d'analyse
# --------------------------------------------------------------------------

def fig_evolution(comparaison: pd.DataFrame, criteres: dict) -> go.Figure:
    """Débit retenu de chaque point, phase par phase, sur fond de seuils de zonage."""
    donnees = comparaison.assign(etape=comparaison["phase"].map(LIBELLES_PHASES))
    fig = px.strip(
        donnees, x="etape", y="debit_retenu", color="zone",
        category_orders={"zone": _ordre_zones(criteres),
                         "etape": list(LIBELLES_PHASES.values())},
        color_discrete_map=_couleurs(criteres),
        hover_data={"point": True, "description": True, "etape": False,
                    "debit_retenu": ":.2f"},
        log_y=True, template=GABARIT, stripmode="overlay",
        labels={"debit_retenu": "Débit de dose retenu (µSv/h)", "etape": "", "zone": "Zone"},
    )
    visibles = [(v, n) for v, n in _seuils(criteres) if v <= donnees["debit_retenu"].max() * 3]
    for valeur, nom in visibles:
        # Sur un axe log, annotation_text de add_hline place le texte à 10**valeur :
        # on pose donc l'annotation à part, en coordonnée log10.
        fig.add_hline(y=valeur, line_dash="dot", line_color="grey")
        fig.add_annotation(x=1, xref="paper", xanchor="left", y=np.log10(valeur), yref="y",
                           text=f"{nom}<br>≥ {valeur:g} µSv/h", showarrow=False,
                           font=dict(size=10, color="grey"), align="left")
    fig.update_traces(marker_size=9, jitter=0.5)
    fig.update_layout(title="Évolution du débit de dose au fil du chantier",
                      margin=dict(r=150),
                      legend=dict(title_text="Zone", orientation="h", y=-0.12))
    return fig


def fig_calcul_mesure(comparaison: pd.DataFrame, tolerance: float = 0.30) -> go.Figure:
    """Nuage calcul contre mesure, en log-log, avec la bissectrice et une bande de tolérance.

    Un point sur la bissectrice : calcul et mesure concordent. Au-dessus, le calcul
    majore. La bande grise matérialise l'écart jugé acceptable (±30 % par défaut).
    """
    donnees = comparaison.dropna(subset=["debit_mesure"]).assign(
        etape=lambda d: d["phase"].map(LIBELLES_PHASES))

    bornes = [donnees[["debit_calcule", "debit_mesure"]].min().min() / 1.5,
              donnees[["debit_calcule", "debit_mesure"]].max().max() * 1.5]
    x = np.geomspace(*bornes, 50)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=np.r_[x, x[::-1]],
                             y=np.r_[x * (1 + tolerance), (x * (1 - tolerance))[::-1]],
                             fill="toself", fillcolor="rgba(128,128,128,0.15)",
                             line_width=0, hoverinfo="skip",
                             name=f"±{tolerance:.0%}"))
    fig.add_trace(go.Scatter(x=bornes, y=bornes, mode="lines", hoverinfo="skip",
                             line=dict(color="black", dash="dash", width=1),
                             name="calcul = mesure"))

    for phase, groupe in donnees.groupby("phase"):
        fig.add_trace(go.Scatter(
            x=groupe["debit_mesure"], y=groupe["debit_calcule"], mode="markers",
            name=LIBELLES_PHASES[phase], marker_size=9,
            customdata=groupe[["point", "ecart_relatif"]],
            hovertemplate="%{customdata[0]}<br>mesure %{x:.2f} µSv/h<br>"
                          "calcul %{y:.2f} µSv/h<br>écart %{customdata[1]:+.0%}<extra></extra>",
        ))

    fig.update_xaxes(type="log", title="Débit mesuré (µSv/h)")
    fig.update_yaxes(type="log", title="Débit calculé, hypothèse nominale (µSv/h)",
                     scaleanchor="x")
    fig.update_layout(template=GABARIT, title="Qualification du modèle : calcul contre mesure")
    return fig


def fig_zonage(comparaison: pd.DataFrame, criteres: dict) -> go.Figure:
    """Nombre de points par zone réglementaire, phase par phase."""
    libelles = {k: v.replace(" : ", "<br>") for k, v in LIBELLES_PHASES.items()}
    comptes = (comparaison.assign(etape=comparaison["phase"].map(libelles))
               .groupby(["etape", "zone"], observed=True).size()
               .reset_index(name="points"))
    fig = px.bar(comptes, x="etape", y="points", color="zone",
                 category_orders={"zone": _ordre_zones(criteres),
                                  "etape": list(libelles.values())},
                 color_discrete_map=_couleurs(criteres), template=GABARIT,
                 labels={"etape": "", "points": "Nombre de points", "zone": "Zone"},
                 text_auto=True)
    fig.update_layout(title="Zonage réglementaire par phase", xaxis_tickangle=0)
    return fig


# --------------------------------------------------------------------------
# Carte et plan
# --------------------------------------------------------------------------

def interpoler_idw(x: np.ndarray, y: np.ndarray, valeurs: np.ndarray,
                   grille_x: np.ndarray, grille_y: np.ndarray,
                   puissance: float = 2.0) -> np.ndarray:
    """Interpolation par pondération inverse de la distance (IDW).

    Chaque nœud reçoit la moyenne des valeurs mesurées, pondérée par 1/d^puissance.
    On interpole le LOGARITHME du débit : le débit varie sur trois ordres de
    grandeur, et une moyenne arithmétique serait écrasée par les points chauds.
    """
    dx = grille_x.ravel()[:, None] - x[None, :]
    dy = grille_y.ravel()[:, None] - y[None, :]
    distances = np.maximum(np.hypot(dx, dy), 1e-6)
    poids = 1.0 / distances ** puissance

    log_valeurs = np.log10(valeurs)
    interpole = (poids * log_valeurs).sum(axis=1) / poids.sum(axis=1)
    return (10 ** interpole).reshape(grille_x.shape)


def carte_dose(plan: dict, comparaison: pd.DataFrame, phase: int,
               pas_cm: float = 20.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Carte de débit interpolée sur tout le plan, local par local.

    Chaque local est interpolé avec ses seuls points : une interpolation qui
    traverserait le mur du sas inventerait une continuité de dose qui n'existe pas.
    Hors des locaux, la carte vaut NaN, ce que Plotly affiche en transparent.
    """
    emprises = {local["libelle"]: local["emprise"] for local in plan["locaux"]}
    xmax = max(e[2] for e in emprises.values())
    ymax = max(e[3] for e in emprises.values())
    gx, gy = np.meshgrid(np.arange(0, xmax + pas_cm, pas_cm),
                         np.arange(0, ymax + pas_cm, pas_cm))
    carte = np.full(gx.shape, np.nan)

    donnees = comparaison.query("phase == @phase")
    for libelle, (x0, y0, x1, y1) in emprises.items():
        points = donnees[donnees["local"] == libelle]
        if points.empty:
            continue
        dedans = (gx >= x0) & (gx <= x1) & (gy >= y0) & (gy <= y1)
        valeurs = interpoler_idw(points["x_cm"].to_numpy(), points["y_cm"].to_numpy(),
                                 points["debit_retenu"].to_numpy(), gx, gy)
        carte[dedans] = valeurs[dedans]

    return gx, gy, carte


def _dessiner_plan(fig: go.Figure, plan: dict) -> None:
    """Murs, équipements et ouvertures, en traits sur la figure."""
    for mur in plan["murs"]:
        xs, ys = zip(*mur["points"])
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip",
                                 line=dict(color="#444", width=4), showlegend=False))

    for ouverture in plan.get("ouvertures", []):
        xs, ys = zip(*ouverture["points"])
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip",
                                 line=dict(color="white", width=6), showlegend=False))

    for eq in plan["equipements"]:
        style = dict(line=dict(color="#555", width=1.5), fillcolor="rgba(120,120,120,0.25)")
        if eq["forme"] == "cercle":
            fig.add_shape(type="circle", x0=eq["x"] - eq["r"], y0=eq["y"] - eq["r"],
                          x1=eq["x"] + eq["r"], y1=eq["y"] + eq["r"], **style)
            position = (eq["x"], eq["y"])
        elif eq["forme"] == "rectangle":
            fig.add_shape(type="rect", x0=eq["x"], y0=eq["y"],
                          x1=eq["x"] + eq["l"], y1=eq["y"] + eq["h"], **style)
            position = (eq["x"] + eq["l"] / 2, eq["y"] + eq["h"] / 2)
        else:
            xs, ys = zip(*eq["points"])
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip",
                                     line=dict(color="#555", width=6), showlegend=False))
            position = eq["points"][len(eq["points"]) // 2]
        fig.add_annotation(x=position[0], y=position[1], text=eq["id"], showarrow=False,
                           font=dict(size=11, color="#222"))


def fig_plan(plan: dict, comparaison: pd.DataFrame, phase: int, criteres: dict,
             avec_carte: bool = True) -> go.Figure:
    """Plan de la casemate : carte de dose interpolée, points colorés par zone.

    Chaque point porte son identifiant dans `customdata` : c'est ce qui permet de
    savoir sur quel point l'utilisateur a cliqué.
    """
    fig = go.Figure()

    if avec_carte:
        gx, gy, carte = carte_dose(plan, comparaison, phase)
        seuils = [0.1, 0.5, 2.5, 7.5, 25, 100, 500, 2000]
        fig.add_trace(go.Contour(
            x=gx[0], y=gy[:, 0], z=np.log10(carte), colorscale="YlOrRd",
            zmin=np.log10(0.1), zmax=np.log10(500), hoverinfo="skip",
            contours=dict(showlines=False), opacity=0.85,
            colorbar=dict(title="µSv/h", tickvals=np.log10(seuils),
                          ticktext=[f"{s:g}" for s in seuils], len=0.8),
        ))

    _dessiner_plan(fig, plan)

    donnees = comparaison.query("phase == @phase")
    couleurs = _couleurs(criteres)
    for zone in _ordre_zones(criteres):
        groupe = donnees[donnees["zone"] == zone]
        if groupe.empty:
            continue
        fig.add_trace(go.Scatter(
            x=groupe["x_cm"], y=groupe["y_cm"], mode="markers+text", name=zone,
            text=groupe["point"], textposition="top center", textfont_size=9,
            marker=dict(size=13, color=couleurs[zone], line=dict(color="black", width=1)),
            customdata=groupe[["point", "debit_retenu", "description"]],
            hovertemplate="<b>%{customdata[0]}</b> : %{customdata[2]}<br>"
                          "%{customdata[1]:.2f} µSv/h<extra></extra>",
        ))

    fig.update_xaxes(title="x (cm)", range=[-60, 1660], showgrid=False, zeroline=False)
    fig.update_yaxes(title="y (cm)", range=[-60, 860], showgrid=False, zeroline=False,
                     scaleanchor="x")
    fig.update_layout(template=GABARIT, title=f"Casemate C2 : {LIBELLES_PHASES[phase]}",
                      legend=dict(orientation="h", y=-0.15), height=560)
    return fig


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------

@contextmanager
def serveur_export():
    """Garde un seul navigateur ouvert pour toute une série d'exports PNG.

    Sans lui, kaleido lance et tue un navigateur à chaque figure : lent, et
    constaté bloquant sous Windows dès la deuxième figure. Avec lui, cinq figures
    s'exportent en quelques secondes.

        with serveur_export():
            exporter_png(fig1, "a.png")
            exporter_png(fig2, "b.png")
    """
    try:
        # Déploiement Streamlit Cloud : kaleido non installé, pas d'export PNG ;
        # les documents portent une mention à la place des figures.
        import kaleido
        kaleido.start_sync_server(silence_warnings=True)
    except Exception as erreur:
        print(f"serveur d'export indisponible ({type(erreur).__name__}), export au cas par cas")
        yield
        return
    # Sous Windows, kaleido échoue parfois à fermer son navigateur alors que tous les
    # exports ont réussi. L'erreur est levée dans un fil d'exécution interne, hors de
    # portée d'un try/except : on la filtre au niveau du gestionnaire des fils, pour ce
    # seul message, le temps de l'arrêt.
    precedent = threading.excepthook

    def filtre(arguments):
        if "close or kill browser" not in str(arguments.exc_value):
            precedent(arguments)

    try:
        yield
    finally:
        threading.excepthook = filtre
        try:
            kaleido.stop_sync_server(silence_warnings=True)
        except Exception as erreur:
            print(f"arrêt du navigateur d'export incomplet ({type(erreur).__name__})")
        finally:
            threading.excepthook = precedent


def exporter_png(fig: go.Figure, chemin: str | Path,
                 largeur: int = 1000, hauteur: int = 560) -> bool:
    """Exporte une figure en PNG. Renvoie False au lieu d'échouer.

    L'export PNG passe par kaleido, qui pilote un navigateur Chromium. Sur un poste
    verrouillé il peut manquer : un rapport sans une figure vaut mieux que pas de
    rapport du tout. L'appelant décide quoi faire d'un échec.
    """
    try:
        with warnings.catch_warnings():
            # Avertissement bénin de plotly quand le serveur d'export est actif.
            warnings.filterwarnings("ignore", message="The kopts argument is ignored")
            fig.write_image(str(chemin), width=largeur, height=hauteur, scale=2)
        return True
    except Exception as erreur:
        print(f"export PNG impossible ({type(erreur).__name__}) : {chemin}")
        return False


def _autotest() -> None:
    import tempfile
    from chargement import charger_tout

    tout = charger_tout()
    comparaison, criteres, plan = tout["comparaison"], tout["criteres"], tout["plan"]

    # L'IDW reproduit exactement les valeurs aux points de mesure.
    x, y, v = np.array([0.0, 100.0]), np.array([0.0, 0.0]), np.array([1.0, 100.0])
    gx, gy = np.meshgrid(np.array([0.0, 50.0, 100.0]), np.array([0.0]))
    res = interpoler_idw(x, y, v, gx, gy)
    assert np.isclose(res[0, 0], 1.0, rtol=1e-6) and np.isclose(res[0, 2], 100.0, rtol=1e-6)
    assert np.isclose(res[0, 1], 10.0), res   # milieu : moyenne géométrique en log

    # La carte est vide hors des locaux, pleine dedans.
    gx, gy, carte = carte_dose(plan, comparaison, phase=0)
    assert np.isnan(carte[(gx > 1250) & (gy < 150)]).all()   # sous le sas, hors local
    assert not np.isnan(carte[(gx < 1100) & (gy < 700)]).any()

    figures = {
        "evolution": fig_evolution(comparaison, criteres),
        "calcul_mesure": fig_calcul_mesure(comparaison),
        "zonage": fig_zonage(comparaison, criteres),
        "plan": fig_plan(plan, comparaison, 0, criteres),
    }
    # Chaque point du plan porte bien son identifiant pour le clic.
    ids = [c[0] for trace in figures["plan"].data
           if trace.customdata is not None for c in trace.customdata]
    assert len(ids) == 32, len(ids)

    with tempfile.TemporaryDirectory() as dossier, serveur_export():
        ok = all(exporter_png(fig, Path(dossier) / f"{nom}.png")
                 for nom, fig in figures.items())
    print(f"autotest : ok : {len(figures)} figures, export PNG {'ok' if ok else 'INDISPONIBLE'}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    _autotest()
