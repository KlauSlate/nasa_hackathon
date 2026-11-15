"""Aptitud de una ventana lunar para funciones de una base humana (solo topografía).

Se deriva de las clases de pendiente ya calculadas por ventana ([<5°, 5-15°, >15°]).
Los umbrales son hipótesis de ingeniería del equipo, NO requisitos de NASA, y la
fracción de área con pendiente baja no garantiza que el terreno plano sea contiguo.
Iluminación, temperatura y visibilidad de la Tierra aún no están incorporadas.
"""
from __future__ import annotations

# Provisional. Cada perfil: fracción mínima del área ventana que debe cumplir el criterio.
PROFILES = {
    "landing_habitat": {
        "label": "Aterrizaje / hábitat",
        "criterion": "fracción de la ventana con pendiente < 5°",
        "class_idx": (0,),
        "min_fraction": 0.30,
    },
    "rover_traverse": {
        "label": "Traverse de rover",
        "criterion": "fracción de la ventana con pendiente < 15°",
        "class_idx": (0, 1),
        "min_fraction": 0.60,
    },
}


def base_suitability(slope_classes: list[float]) -> dict:
    """Por perfil: fracción que cumple, y si supera el umbral provisional."""
    out = {}
    for pid, p in PROFILES.items():
        if len(slope_classes) != 3:
            out[pid] = {"label": p["label"], "fraction": None, "meets": None, "criterion": p["criterion"]}
            continue
        frac = round(float(sum(slope_classes[i] for i in p["class_idx"])), 4)
        out[pid] = {"label": p["label"], "criterion": p["criterion"], "fraction": frac,
                    "min_fraction": p["min_fraction"], "meets": frac >= p["min_fraction"]}
    return out
