"""Barrido de ventanas terrestres, distancia a la ventana lunar y ranking.

D = w_slope*d(pendiente) + w_rough*d(rugosidad) + w_relief*d(relieve)

Cada d es |valor_ventana - valor_luna| / escala robusta, con la escala (MAD
escalada) calculada sobre el conjunto de ventanas terrestres válidas para que
ninguna variable domine por sus unidades. Menor D = mayor similitud RELATIVA.
Los pesos son hipótesis de ingeniería, no coeficientes calibrados.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .terrain import Surface, roughness_residual, slope_degrees, slope_histogram, window_metrics

WEIGHTS = {"slope": 0.45, "rough": 0.35, "relief": 0.20}
ALT_WEIGHTS = {
    "equal": {"slope": 1 / 3, "rough": 1 / 3, "relief": 1 / 3},
    "slope_heavy": {"slope": 0.60, "rough": 0.25, "relief": 0.15},
    "rough_heavy": {"slope": 0.25, "rough": 0.55, "relief": 0.20},
    "relief_heavy": {"slope": 0.25, "rough": 0.25, "relief": 0.50},
}
METRIC_COLS = ["slope_p50_deg", "slope_p90_deg", "roughness_270m_m", "relief_p95_p5_m"]
MIN_COVERAGE = 0.95  # umbral provisional de ingeniería, no una norma de NASA


def derive_layers(surface: Surface, rough_window_m: float = 270.0):
    """Pendiente y rugosidad de toda la superficie (se calculan una sola vez)."""
    slope = slope_degrees(surface.z, surface.res_m)
    rough = roughness_residual(surface.z, surface.res_m, rough_window_m)
    return slope, rough


def window_pixels(window_m: float, res_m: float) -> int:
    return int(round(window_m / res_m))


def sweep_windows(surface: Surface, slope, rough, window_m=3000.0, step_m=1500.0) -> pd.DataFrame:
    """Métricas de cada ventana cuadrada, barriendo el ROI con paso `step_m`.

    Devuelve una fila por ventana (incluidas las de baja cobertura; el filtro
    se aplica después para poder reportar cuántas se descartaron).
    """
    n = window_pixels(window_m, surface.res_m)
    step = max(int(round(step_m / surface.res_m)), 1)
    h, w = surface.z.shape
    rows = []
    for r0 in range(0, h - n + 1, step):
        for c0 in range(0, w - n + 1, step):
            m = window_metrics(surface.z, slope, rough, r0, c0, n)
            cx, cy = surface.transform @ (c0 + n / 2, r0 + n / 2)
            rows.append({"row": r0, "col": c0, "center_x": cx, "center_y": cy, **m})
    return pd.DataFrame(rows)


def robust_scales(earth: pd.DataFrame) -> dict:
    """Escala = 1.4826*MAD por métrica, sobre ventanas terrestres válidas."""
    scales = {}
    for c in METRIC_COLS:
        x = earth[c].dropna().to_numpy()
        mad = 1.4826 * np.median(np.abs(x - np.median(x))) if x.size else np.nan
        scales[c] = float(mad) if mad and mad > 0 else float(np.nanstd(x) or 1.0)
    return scales


def compute_distances(earth: pd.DataFrame, moon: dict, scales: dict, weights=WEIGHTS) -> pd.DataFrame:
    """Añade distancias por dimensión y D total (menor = más parecida)."""
    df = earth.copy()
    d = {c: (df[c] - moon[c]).abs() / scales[c] for c in METRIC_COLS}
    df["d_slope"] = 0.5 * (d["slope_p50_deg"] + d["slope_p90_deg"])  # 2 resúmenes de la misma dimensión
    df["d_rough"] = d["roughness_270m_m"]
    df["d_relief"] = d["relief_p95_p5_m"]
    df["D"] = (weights["slope"] * df["d_slope"] + weights["rough"] * df["d_rough"]
               + weights["relief"] * df["d_relief"])
    return df


def usable(df: pd.DataFrame, min_cov: float = MIN_COVERAGE) -> pd.DataFrame:
    return df[(df["valid_coverage_fraction"] >= min_cov) & df[METRIC_COLS].notna().all(axis=1)].copy()


def _sep_m(a, b) -> float:
    """Separación entre centros (m, norma del máximo). Con lat/lon sirve entre regiones distintas."""
    if "center_lat" in a.index:
        dy = (a.center_lat - b.center_lat) * 110540.0
        dx = (a.center_lon - b.center_lon) * 111320.0 * np.cos(np.radians((a.center_lat + b.center_lat) / 2))
        return float(max(abs(dx), abs(dy)))
    return float(max(abs(a.center_x - b.center_x), abs(a.center_y - b.center_y)))


def select_distinct(df: pd.DataFrame, k: int = 3, min_sep_m: float = 3000.0) -> pd.DataFrame:
    """Top-k por D, sin ventanas que se solapen (centros separados >= min_sep_m)."""
    chosen = []
    for _, r in df.sort_values("D").iterrows():
        if all(_sep_m(r, c) >= min_sep_m for c in chosen):
            chosen.append(r)
        if len(chosen) == k:
            break
    return pd.DataFrame(chosen)


def pick_controls(df: pd.DataFrame, top: pd.DataFrame, n=10, min_sep_m=6000.0, seed=0) -> pd.DataFrame:
    """Ventanas de control aleatorias, alejadas de los ganadores (seed fija)."""
    rng = np.random.default_rng(seed)
    pool = df.drop(index=top.index, errors="ignore")
    for _, t in top.iterrows():
        far = np.maximum(abs(pool.center_x - t.center_x), abs(pool.center_y - t.center_y)) >= min_sep_m
        pool = pool[far]
    if pool.empty:
        return pool
    return pool.iloc[rng.permutation(len(pool))[:n]]


def weight_sensitivity(df: pd.DataFrame, k=3, min_sep_m=3000.0) -> dict:
    """Repite el top-k con pesos alternativos y reporta cuánto cambia."""
    base = select_distinct(df, k, min_sep_m)
    base_ids = set(zip(base.row, base.col))
    out = {}
    for name, w in ALT_WEIGHTS.items():
        alt = df.copy()
        alt["D"] = w["slope"] * alt.d_slope + w["rough"] * alt.d_rough + w["relief"] * alt.d_relief
        top = select_distinct(alt, k, min_sep_m)
        ids = set(zip(top.row, top.col))
        out[name] = {"weights": w, "top_windows": sorted(map(list, ids)),
                     "overlap_with_base": len(ids & base_ids), "k": k}
    out["stable"] = all(v["overlap_with_base"] == k for v in out.values() if isinstance(v, dict))
    return out
