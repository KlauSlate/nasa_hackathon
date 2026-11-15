"""Iluminación, visibilidad de la Tierra y sombra permanente por ventana lunar.

Fuente: mapas polares de LOLA (Mazarico et al.), PGDA "Lunar Polar Illumination",
85°S–90°S a 60 m/px, promedios horarios sobre ~18,6 años. Están en la misma proyección
polar estereográfica que los DEM de sitio, así que se muestrean por coordenadas X/Y.
Valor = DN * escala + desfase (los GeoTIFF traen la escala; aquí se aplica explícitamente).

No son condiciones en un instante dado, ni consideran la altura de un hábitat o antena sobre
el suelo. La visibilidad de la Tierra marca "visible" si se ve cualquier parte del disco.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds

LAYERS = {
    "illumination": "data/raw/AVGVISIB_85S_060M_201608.TIF",
    "earth_visibility": "data/raw/AVGVISIB_85S_060M_201608_EARTH.TIF",
    "psr": "data/raw/LPSR_85S_060M_201608.TIF",
}
SOURCE_URL = "https://pgda.gsfc.nasa.gov/products/69"


def available() -> bool:
    return all(Path(p).exists() for p in LAYERS.values())


def load_site_layers(bounds: tuple[float, float, float, float], pad_m: float = 120.0) -> dict | None:
    """Recorta cada mapa a las cotas del sitio (con holgura). Devuelve None si el sitio queda fuera."""
    l, b, r, t = bounds
    out = {}
    for name, path in LAYERS.items():
        with rasterio.open(path) as src:
            sb = src.bounds
            if l - pad_m < sb.left or r + pad_m > sb.right or b - pad_m < sb.bottom or t + pad_m > sb.top:
                return None
            win = from_bounds(l - pad_m, b - pad_m, r + pad_m, t + pad_m, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=win).astype("float64")
            tr = src.window_transform(win)
            nodata = src.nodata
            scale, offset = src.scales[0], src.offsets[0]
        a = np.where(a == nodata, np.nan, a * scale + offset)
        out[name] = (a, tr)
    return out


def window_illumination(layers: dict, cx: float, cy: float, window_m: float) -> dict:
    """Media de iluminación y de visibilidad de la Tierra, y fracción en sombra permanente, de una ventana."""
    half = window_m / 2
    res = {}
    for name, (a, tr) in layers.items():
        inv = ~tr
        c0, r0 = inv * (cx - half, cy + half)  # esquina superior izquierda
        c1, r1 = inv * (cx + half, cy - half)  # esquina inferior derecha
        sub = a[max(int(round(r0)), 0):int(round(r1)), max(int(round(c0)), 0):int(round(c1))]
        valid = sub[np.isfinite(sub)]
        if valid.size == 0:
            res[name] = (None, 0.0)
        elif name == "psr":
            res[name] = (float((valid > 0.5).mean()), float(valid.size / sub.size))
        else:
            res[name] = (float(valid.mean()), float(valid.size / sub.size))
    return {"illumination_mean": res["illumination"][0], "earth_visibility_mean": res["earth_visibility"][0],
            "psr_fraction": res["psr"][0], "coverage": min(v[1] for v in res.values())}
