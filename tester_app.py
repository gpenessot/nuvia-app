"""Teste l'application page par page, avec un utilisateur virtuel.

    python tester_app.py

`AppTest` exécute l'application sans navigateur, permet de régler les widgets et de
cliquer sur les boutons, puis de lire ce que la page affiche. Le clic sur le plan Plotly ne peut pas être simulé (Streamlit
l'interdit) : c'est la fonction `point_du_clic` qui est testée à la place.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import commun  # noqa: E402

APP = str(ICI / "app.py")


def ouvrir(page: str | None = None) -> AppTest:
    """Lance l'application, et va sur une page si elle est indiquée."""
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["utilisateur"] = "test"
    at.run()
    if page:
        at.switch_page(f"pages/{page}.py").run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def tester_connexion() -> None:
    at = AppTest.from_file(APP, default_timeout=120)
    at.secrets["comptes"] = {"nuvia": "secret"}
    at.run()
    assert not at.title, "page visible sans connexion"
    at.text_input[0].input("nuvia")
    at.text_input[1].input("faux")
    at.button[0].click().run()
    assert at.error and not at.title
    at.text_input[1].input("secret")
    at.button[0].click().run()
    assert at.session_state["utilisateur"] == "nuvia" and at.title


def valeurs(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def tester_fonctions() -> None:
    evenement = {"selection": {"points": [{"curve_number": 0}, {"customdata": ["P14", 3.1]}]}}
    assert commun.point_du_clic(evenement) == "P14"
    assert commun.point_du_clic({"selection": {"points": [{"x": 1}]}}) is None
    assert commun.point_du_clic(None) is None

    criteres = commun.donnees.__wrapped__()["criteres"]
    zone, facteur = commun.marge_au_seuil(5.0, criteres)
    assert zone == "Contrôlée verte" and abs(facteur - 1.5) < 1e-9, (zone, facteur)
    assert commun.marge_au_seuil(1e6, criteres) == (None, None)
    assert commun.fr(0.3, 1) == "0,3" and commun.fr(2, 1, signe=True) == "+2,0"


def tester_accueil() -> None:
    at = ouvrir()
    v = valeurs(at)
    assert v["Points de mesure"] == "32", v
    assert v["Points en zone jaune, phase 2"] == "0", v


def tester_calculette() -> None:
    at = ouvrir("calculette")
    assert at.selectbox[0].value == "PT01"
    # À l'ouverture, sans rien toucher, le débit affiché est celui du point de référence.
    assert valeurs(at)["Débit au poste"] == "68,9 µSv/h", valeurs(at)
    assert at.error and not at.success, "PT01 en phase 0 doit dépasser la contrainte"

    at.slider[0].set_value(1.0).run()
    assert at.success and not at.error, "1 cm de plomb doit suffire"

    at.button[0].click().run()
    at.slider[0].set_value(2.0).run()
    at.button[0].click().run()
    assert len(at.session_state["configurations"]) == 2

    at.sidebar.radio[0].set_value(2).run()
    assert at.success, "en phase 2, le poste découpe de cuve est conforme"


def tester_tableau_de_bord() -> None:
    at = ouvrir("tableau_de_bord")
    assert valeurs(at)["Lignes sélectionnées"] == "96"

    at.sidebar.multiselect[0].set_value([2]).run()
    assert valeurs(at)["Lignes sélectionnées"] == "32"

    at.sidebar.multiselect[2].set_value([]).run()
    assert at.warning, "sans zone sélectionnée, la page doit prévenir"


def tester_plan() -> None:
    at = ouvrir("plan")
    at.selectbox[0].set_value("P14").run()
    v = valeurs(at)
    assert v["Zone"] == "Contrôlée jaune", v
    assert v["Débit retenu, phase 0"].startswith("275"), v

    at.selectbox[0].set_value("P29").run()
    assert at.error, "P29 est le point de référence de PT01, non conforme en phase 0"


def tester_rapport() -> None:
    at = ouvrir("rapport")
    at.sidebar.radio[0].set_value(0).run()
    at.button[0].click().run()
    assert not at.exception, [e.message for e in at.exception]
    fichiers = at.session_state["livrables"]["fichiers"]
    assert len(fichiers) == 4 and all(len(c) > 1000 for c in fichiers.values()), fichiers.keys()


def tester_lecture_classeur() -> None:
    sys.path.insert(0, str(commun.RACINE))
    from outils.livrables import ecrire_xlsx

    with tempfile.TemporaryDirectory() as dossier:
        chemin = Path(dossier) / "c.xlsx"
        ecrire_xlsx(commun.donnees.__wrapped__(), chemin)
        assert len(commun.lire_classeur(chemin)) == 96
        faux = Path(dossier) / "faux.xlsx"
        import pandas as pd
        pd.DataFrame({"a": [1]}).to_excel(faux, sheet_name="Autre")
        try:
            commun.lire_classeur(faux)
        except ValueError as erreur:
            assert "Comparaison" in str(erreur)
        else:
            raise AssertionError("un classeur sans feuille Comparaison doit être refusé")


if __name__ == "__main__":
    tests = [tester_connexion, tester_fonctions, tester_lecture_classeur, tester_accueil, tester_calculette,
             tester_tableau_de_bord, tester_plan, tester_rapport]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} tests de l'application réussis")
