"""Salidas explicativas para la interfaz: percentil, clases de pendiente,
texto de coincidencias/diferencias, hillshade y ranking por ventana lunar."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from matplotlib.colors import LightSource  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

from .similarity import METRIC_COLS, compute_distances, select_distinct  # noqa: E402

SLOPE_CLASSES = ["0-5°", "5-15°", ">15°"]

# Lo que un DEM NO permite concluir; se muestra siempre junto a cada candidato.
PENDING_VALIDATION = [
    "Rocas y obstáculos menores a la resolución del DEM (~30 m en el DEM terrestre; LOLA ~90 % interpolado).",
    "Resistencia y composición del suelo, adherencia y hundimiento.",
    "Estabilidad del terreno y pendientes locales a escala de rover.",
    "Accesibilidad, propiedad del terreno, permisos y seguridad física.",
    "Gravedad, vacío, iluminación y polvo lunar: no reproducibles en la Tierra.",
]

_LABELS = {
    "slope_p50_deg": ("pendiente mediana", "°"),
    "slope_p90_deg": ("pendiente P90", "°"),
    "roughness_270m_m": ("rugosidad (270 m)", " m"),
    "relief_p95_p5_m": ("relieve local P95–P5", " m"),
}


def percentile_similarity(all_D: np.ndarray, d: float) -> float:
    """Fracción (0-100) de ventanas del ROI con distancia MAYOR que `d`."""
    return float((np.asarray(all_D) > d).mean() * 100)


def slope_class_fractions(slope, r0, c0, n) -> list[float]:
    sw = slope[r0:r0 + n, c0:c0 + n]
    sw = sw[np.isfinite(sw)]
    if sw.size == 0:
        return []
    return [round(float(x), 4) for x in
            ((sw < 5).mean(), ((sw >= 5) & (sw < 15)).mean(), (sw >= 15).mean())]


def compare_text(moon: dict, cand: dict, scales: dict) -> dict:
    """Coincidencias (|Δ| ≤ 1 escala robusta) y diferencias, con valores reales."""
    matches, diffs = [], []
    for c in METRIC_COLS:
        name, unit = _LABELS[c]
        delta = cand[c] - moon[c]
        line = f"{name}: Luna {moon[c]:.1f}{unit} vs. candidato {cand[c]:.1f}{unit}"
        (matches if abs(delta) / scales[c] <= 1 else diffs).append(line)
    return {"matches": matches, "differences": diffs}


def read_window_native(path, bounds):
    """Lee la ventana a resolución nativa. bounds = (left, bottom, right, top) en el CRS del ráster.

    Devuelve (z, dx_m, dy_m). En lat/lon convierte grados a metros solo para el sombreado.
    """
    with rasterio.open(path) as src:
        win = from_bounds(*bounds, src.transform)
        z = src.read(1, window=win, masked=True).astype("float64")
        z = np.ma.filled(z, np.nan)
        rx, ry = src.res
        if src.crs.is_geographic:
            lat = (bounds[1] + bounds[3]) / 2
            ry_m = ry * 111_320.0
            rx_m = rx * 111_320.0 * np.cos(np.radians(lat))
            # Píxeles cuadrados en metros (a 75° de latitud un píxel mide ~8 m de ancho y ~31 m de alto)
            from scipy.ndimage import zoom

            z = zoom(np.nan_to_num(z, nan=float(np.nanmean(z))), (1.0, rx_m / ry_m), order=1)
            return z, ry_m, ry_m
        return z, rx, ry


def hillshade_png(z, dx, dy, path, display_res_m=30.0, out_px=400) -> str | None:
    """Sombreado de relieve (azimut 315°, altura 45°). Es una vista del DEM, no una foto.

    Para que Luna y Tierra se comparen a la misma escala visual, el DEM se promedia
    a ~`display_res_m` y luego se amplía a `out_px` solo para verlo.
    """
    from scipy.ndimage import zoom

    if z.size == 0 or not np.isfinite(z).any():
        return None
    f = max(int(round(display_res_m / dx)), 1)
    if f > 1:
        h, w = (z.shape[0] // f) * f, (z.shape[1] // f) * f
        z = np.nanmean(z[:h, :w].reshape(h // f, f, w // f, f), axis=(1, 3))
        dx, dy = dx * f, dy * f
    zf = np.where(np.isfinite(z), z, np.nanmean(z))
    hs = LightSource(azdeg=315, altdeg=45).hillshade(zf, vert_exag=1.0, dx=dx, dy=dy)
    hs = np.clip(zoom(hs, out_px / max(hs.shape), order=3), 0, 1)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    plt.imsave(path, hs, cmap="gray", vmin=0, vmax=1)
    return str(path)


def lunar_grid(surface, slope, rough, n, step_px, ldec_path=None):
    """Métricas de ventanas lunares en malla, para elegir/calcular ranking al instante."""
    from .terrain import window_metrics

    h, w = surface.z.shape
    ldec = rasterio.open(ldec_path) if ldec_path else None
    rows = []
    for r0 in range(0, h - n + 1, step_px):
        for c0 in range(0, w - n + 1, step_px):
            m = window_metrics(surface.z, slope, rough, r0, c0, n)
            if "slope_p50_deg" not in m:
                continue
            cx, cy = surface.transform @ (c0 + n / 2, r0 + n / 2)
            obs = None
            if ldec is not None:
                b = (surface.transform @ (c0, r0 + n)) + (surface.transform @ (c0 + n, r0))
                a = ldec.read(1, window=from_bounds(*b, ldec.transform), masked=True)
                obs = float((np.ma.filled(a, 0) > 0).mean()) if a.size else None
            rows.append({"row": r0, "col": c0, "center_x": cx, "center_y": cy,
                         "lola_observed_fraction": obs, **m,
                         "slope_classes": slope_class_fractions(slope, r0, c0, n)})
    if ldec is not None:
        ldec.close()
    return rows


def _entry(r, D_all):
    return {"region": r.region, "row": int(r.row), "col": int(r.col), "D": float(r.D),
            "percentile": percentile_similarity(D_all, float(r.D))}


def rank_lunar_windows(lunar_rows, earth_ok, scales, k=3, min_sep_m=3000.0):
    """Para cada ventana lunar: top-k global (todas las regiones) y top-k de cada región.

    `earth_ok` debe traer las columnas region, center_lat y center_lon. El percentil
    del top global es respecto de todas las ventanas; el de cada región, respecto de las suyas.
    """
    out = []
    for lw in lunar_rows:
        d = compute_distances(earth_ok, lw, scales)
        top = select_distinct(d, k, min_sep_m)
        D_all = d["D"].to_numpy()
        by_region = {}
        for rid, g in d.groupby("region"):
            t = select_distinct(g, k, min_sep_m)
            Dg = g["D"].to_numpy()
            by_region[rid] = [_entry(r, Dg) for _, r in t.iterrows()]
        out.append({**{k_: lw[k_] for k_ in ("row", "col", "center_x", "center_y")},
                    "top": [_entry(r, D_all) for _, r in top.iterrows()], "by_region": by_region})
    return out
