"""Aptitud de una ventana lunar para funciones de una base humana.

Combina las clases de pendiente (topografía) con iluminación, visibilidad de la Tierra y
sombra permanente (mapas LOLA de 60 m, ver illum.py). Los umbrales son hipótesis de
ingeniería del equipo, NO requisitos de NASA. Limitaciones:
- La fracción de pendiente baja no garantiza terreno plano contiguo.
- Los mapas son promedios de ~18,6 años a nivel del suelo, no una temporada ni la altura de una antena.
- Sombra permanente indica una zona fría candidata a hielo, no que haya hielo (la composición no se evaluó).
- Falta temperatura (Diviner).
"""
from __future__ import annotations

# Cada criterio: (clave de origen, etiqueta, mínimo, tipo). "slope" usa las clases [<5°, 5-15°, >15°].
CRITERIA = {
    "flat5": ("slope", (0,), "Pendiente < 5°", 0.30),
    "flat15": ("slope", (0, 1), "Pendiente < 15°", 0.60),
    "illum": ("illum", "illumination_mean", "Iluminación media", 0.30),
    "earth": ("illum", "earth_visibility_mean", "Visibilidad de la Tierra", 0.50),
    "psr": ("illum", "psr_fraction", "Sombra permanente (área)", 0.05),
}

PROFILES = {
    "landing_habitat": {"label": "Aterrizaje / hábitat (topografía)", "criteria": ["flat5"]},
    "rover_traverse": {"label": "Traverse de rover", "criteria": ["flat15"]},
    "power_comms": {"label": "Energía solar y comunicaciones", "criteria": ["illum", "earth"]},
    "isru_ice": {"label": "Zona fría candidata a hielo (ISRU)", "criteria": ["psr"]},
    "habitat_full": {"label": "Hábitat completo", "criteria": ["flat5", "illum", "earth"]},
}


def _value(key: str, slope_classes: list[float], illum: dict | None):
    kind, src, _, _ = CRITERIA[key]
    if kind == "slope":
        return round(float(sum(slope_classes[i] for i in src)), 4) if len(slope_classes) == 3 else None
    v = None if not illum else illum.get(src)
    return None if v is None else round(float(v), 4)


def base_suitability(slope_classes: list[float], illum: dict | None = None) -> dict:
    """Por perfil: valor de cada criterio, mínimo exigido y si cumple (None si falta algún dato)."""
    out = {}
    for pid, p in PROFILES.items():
        parts = []
        for ck in p["criteria"]:
            _, _, label, minimum = CRITERIA[ck]
            parts.append({"label": label, "value": _value(ck, slope_classes, illum), "min": minimum})
        known = all(x["value"] is not None for x in parts)
        out[pid] = {"label": p["label"], "parts": parts,
                    "meets": all(x["value"] >= x["min"] for x in parts) if known else None}
    return out
