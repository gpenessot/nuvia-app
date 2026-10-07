"""Physique de la calculette ALARA, importée par la page « Calculette ALARA ».

Le modèle est volontairement simple, et ses limites doivent être affichées avec le
résultat :

- le débit connu au point de référence du poste est attribué **en entier** à la
  source la plus proche. C'est une bonne approximation quand cette source domine,
  moins bonne sinon ;
- s'éloigner de la source réduit le débit en 1/d² ;
- un écran de plomb le réduit d'un facteur (1 + µx)·exp(−µx). Le facteur
  d'accumulation linéaire de Berger surestime l'accumulation dans le plomb : le
  résultat est donc majorant, ce qui va dans le sens de la sécurité.
"""

from __future__ import annotations

import math

# Plomb : masse volumique et coefficients d'atténuation MASSIQUES (cm²/g) à l'énergie
# moyenne des photons de chaque isotope. Le coefficient linéique est µ/ρ × ρ.
RHO_PLOMB = 11.35
MU_SUR_RHO_PLOMB = {"Co-60": 0.0588, "Cs-137": 0.1101, "Eu-152": 0.105}


def mu_plomb(isotope: str) -> float:
    """Coefficient d'atténuation linéique du plomb, en cm⁻¹."""
    return MU_SUR_RHO_PLOMB[isotope] * RHO_PLOMB


def transmission_plomb(isotope: str, epaisseur_cm: float) -> float:
    """Fraction du débit qui traverse un écran de plomb, accumulation comprise."""
    mux = mu_plomb(isotope) * epaisseur_cm
    return (1.0 + mux) * math.exp(-mux)


def source_la_plus_proche(plan: dict, x_cm: float, y_cm: float,
                          z_cm: float) -> tuple[dict, float]:
    """La source du plan la plus proche d'un point, et sa distance en mètres."""
    distances = [(math.dist((x_cm, y_cm, z_cm), (s["x"], s["y"], s["z"])) / 100.0, s)
                 for s in plan["sources"]]
    distance_m, source = min(distances, key=lambda paire: paire[0])
    return source, distance_m


def debit_au_poste(debit_reference: float, distance_reference_m: float,
                   distance_m: float, isotope: str, epaisseur_plomb_cm: float = 0.0) -> float:
    """Débit en µSv/h à `distance_m` de la source, derrière un écran de plomb.

    Le débit de référence est celui mesuré ou calculé au point de référence du
    poste, situé à `distance_reference_m` de la source.
    """
    if distance_m <= 0:
        raise ValueError("la distance à la source doit être positive")
    if epaisseur_plomb_cm < 0:
        raise ValueError("l'épaisseur d'écran ne peut pas être négative")
    geometrie = (distance_reference_m / distance_m) ** 2
    return debit_reference * geometrie * transmission_plomb(isotope, epaisseur_plomb_cm)


def bilan(debit_usv_h: float, duree_h: float, nb_intervenants: int,
          contrainte_msv: float) -> dict:
    """Dose individuelle et collective, temps de présence maximal, conformité."""
    dose_individuelle = debit_usv_h * duree_h / 1000.0
    return {
        "debit_usv_h": debit_usv_h,
        "dose_individuelle_msv": dose_individuelle,
        "dose_collective_hmsv": dose_individuelle * nb_intervenants,
        "temps_max_h": contrainte_msv * 1000.0 / debit_usv_h,
        "marge_msv": contrainte_msv - dose_individuelle,
        "conforme": dose_individuelle <= contrainte_msv,
    }


def epaisseur_minimale(debit_reference: float, isotope: str, duree_h: float,
                       contrainte_msv: float, pas_cm: float = 0.1,
                       maximum_cm: float = 20.0) -> float | None:
    """Plus petite épaisseur de plomb qui ramène la dose sous la contrainte.

    Recherche par pas successifs, sans résoudre d'équation : lisible, et largement
    assez précis pour un écran qu'on commande au demi-centimètre. Renvoie None si
    `maximum_cm` ne suffit pas.
    """
    epaisseur = 0.0
    while epaisseur <= maximum_cm:
        debit = debit_reference * transmission_plomb(isotope, epaisseur)
        if debit * duree_h / 1000.0 <= contrainte_msv:
            return round(epaisseur, 2)
        epaisseur += pas_cm
    return None


def _autotest() -> None:
    # Sans écran et à la distance de référence, on retrouve le débit de référence.
    assert math.isclose(debit_au_poste(50.0, 1.5, 1.5, "Co-60", 0.0), 50.0)
    # Deux fois plus loin : quatre fois moins.
    assert math.isclose(debit_au_poste(40.0, 1.0, 2.0, "Cs-137"), 10.0)
    # Le plomb atténue davantage le Cs-137 (662 keV) que le Co-60 (1,25 MeV).
    assert transmission_plomb("Cs-137", 2.0) < transmission_plomb("Co-60", 2.0)

    # Le cas PT01 : 68,9 µSv/h pendant 4,5 h dépasse 0,30 mSv ; 1 cm de plomb suffit.
    sans = bilan(68.9, 4.5, 2, 0.30)
    avec = bilan(debit_au_poste(68.9, 1.5, 1.5, "Co-60", 1.0), 4.5, 2, 0.30)
    assert not sans["conforme"] and avec["conforme"], (sans, avec)
    e = epaisseur_minimale(68.9, "Co-60", 4.5, 0.30)
    assert e is not None and 0 < e <= 1.0, e

    for fonction, argument in ((debit_au_poste, (10, 1, 0, "Co-60")),
                               (debit_au_poste, (10, 1, 1, "Co-60", -1))):
        try:
            fonction(*argument)
        except ValueError:
            continue
        raise AssertionError(f"{argument} aurait dû être refusé")

    print(f"autotest : ok : PT01 {sans['dose_individuelle_msv']:.3f} mSv sans écran, "
          f"{avec['dose_individuelle_msv']:.3f} mSv avec 1 cm de plomb, "
          f"épaisseur minimale {e} cm")


if __name__ == "__main__":
    _autotest()
