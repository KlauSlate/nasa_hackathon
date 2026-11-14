"""Métricas topográficas a partir de un DEM, en metros y a escala común.

Cada superficie (Luna, Tierra) se procesa en SU propio sistema métrico:
- Luna: proyección polar estereográfica (metros), sin EPSG terrestre.
- Tierra: UTM (p. ej. EPSG:32616) tras reproyectar el DEM en lat/lon.

Nunca se comparan coordenadas ni elevaciones absolutas entre cuerpos; solo
magnitudes derivadas (pendiente, rugosidad, relieve local).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import calculate_default_transform
from scipy.ndimage import uniform_filter


@dataclass
class Surface:
    """DEM en metros, ya a la escala de análisis."""

    z: np.ndarray          # elevación (m), NaN donde no hay dato
    res_m: float           # tamaño de píxel (m), cuadrado
    transform: Affine      # transformación píxel -> CRS (en metros)
    crs: object            # CRS del ráster procesado
    source_res_m: float    # resolución nativa aproximada (m), solo metadata


def load_surface(path, target_res_m: float, dst_crs=None) -> Surface:
    """Lee un DEM, lo reproyecta (si `dst_crs`) y lo promedia a `target_res_m`.

    - Tierra: pasar `dst_crs="EPSG:32616"` (UTM 16N, Haughton) para pasar de grados a metros.
    - Luna: dejar `dst_crs=None`; el ráster ya viene en proyección polar (metros).
    El ráster original en disco no se modifica.
    """
    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(f"{path}: el ráster no tiene CRS.")
        if dst_crs is None and src.crs.is_geographic:
            raise ValueError(
                f"{path}: está en lat/lon; indica dst_crs (p. ej. EPSG:32616) para trabajar en metros."
            )
        nodata = src.nodata
        source_res_m = float(np.mean(src.res)) if not src.crs.is_geographic else float("nan")
        crs = dst_crs or src.crs
        transform, width, height = calculate_default_transform(
            src.crs, crs, src.width, src.height, *src.bounds, resolution=target_res_m)
        with WarpedVRT(
            src,
            crs=crs,
            transform=transform,
            width=width,
            height=height,
            resampling=Resampling.average,
            nodata=nodata if nodata is not None else -32768.0,
        ) as vrt:
            data = vrt.read(1, masked=True).astype("float64")
            z = np.ma.filled(data, np.nan)
            return Surface(z=z, res_m=float(target_res_m), transform=vrt.transform,
                           crs=vrt.crs, source_res_m=source_res_m)


def slope_degrees(z: np.ndarray, res_m: float) -> np.ndarray:
    """Pendiente en grados (diferencias finitas centradas). NaN se propaga."""
    dz_dy, dz_dx = np.gradient(z, res_m)
    return np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))


def _odd_pixels(window_m: float, res_m: float) -> int:
    n = max(int(round(window_m / res_m)), 3)
    return n if n % 2 == 1 else n + 1


def roughness_residual(z: np.ndarray, res_m: float, window_m: float = 270.0) -> np.ndarray:
    """Rugosidad: desviación estándar (m) del residuo respecto de un plano local.

    En cada ventana de `window_m` se ajusta un plano por mínimos cuadrados y se
    mide la dispersión de lo que el plano no explica. Un plano inclinado da 0:
    la pendiente NO cuenta como rugosidad. Se calcula con momentos (filtros
    uniformes), equivalente al ajuste explícito en una ventana cuadrada.
    Pixeles con <50 % de datos válidos en su ventana quedan NaN.
    """
    n = _odd_pixels(window_m, res_m)
    valid = np.isfinite(z)
    w = uniform_filter(valid.astype("float64"), size=n, mode="nearest")
    zf = np.where(valid, z, 0.0)
    yy, xx = np.mgrid[0:z.shape[0], 0:z.shape[1]].astype("float64")
    xx *= res_m
    yy *= res_m

    def mean(a):  # media ponderada por validez dentro de la ventana
        return uniform_filter(np.where(valid, a, 0.0), size=n, mode="nearest") / np.maximum(w, 1e-12)

    m_z, m_zz = mean(zf), mean(zf * zf)
    m_x, m_y = mean(xx), mean(yy)
    var_z = np.clip(m_zz - m_z**2, 0, None)
    var_x = np.clip(mean(xx * xx) - m_x**2, 1e-12, None)
    var_y = np.clip(mean(yy * yy) - m_y**2, 1e-12, None)
    cov_zx = mean(zf * xx) - m_z * m_x
    cov_zy = mean(zf * yy) - m_z * m_y
    resid_var = np.clip(var_z - cov_zx**2 / var_x - cov_zy**2 / var_y, 0, None)
    rough = np.sqrt(resid_var)
    rough[(w < 0.5) | ~valid] = np.nan
    return rough


def window_metrics(z, slope, rough, r0, c0, n) -> dict:
    """Métricas de la ventana [r0:r0+n, c0:c0+n] (índices de píxel)."""
    zw = z[r0:r0 + n, c0:c0 + n]
    sw = slope[r0:r0 + n, c0:c0 + n]
    rw = rough[r0:r0 + n, c0:c0 + n]
    usable = np.isfinite(zw) & np.isfinite(sw) & np.isfinite(rw)
    cov = float(usable.mean())
    if usable.sum() < 10:
        return {"valid_coverage_fraction": cov}
    s, r, e = sw[usable], rw[usable], zw[usable]
    return {
        "slope_p50_deg": float(np.percentile(s, 50)),
        "slope_p90_deg": float(np.percentile(s, 90)),
        "roughness_270m_m": float(np.median(r)),
        "relief_p95_p5_m": float(np.percentile(e, 95) - np.percentile(e, 5)),
        "valid_coverage_fraction": cov,
    }


SLOPE_BINS_DEG = [0, 2, 5, 10, 15, 20, 30, 90]


def slope_histogram(slope, r0, c0, n) -> list[float]:
    """Fracción de píxeles por clase de pendiente (bins fijos y documentados)."""
    sw = slope[r0:r0 + n, c0:c0 + n]
    sw = sw[np.isfinite(sw)]
    if sw.size == 0:
        return []
    h, _ = np.histogram(sw, bins=SLOPE_BINS_DEG)
    return (h / sw.size).round(4).tolist()
