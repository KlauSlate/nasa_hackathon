"""Pruebas de métricas con terrenos SINTÉTICOS de respuesta conocida.

Solo validan el cálculo (unidades, escala, filtros). Nunca se usan como
resultados del experimento.
"""
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.similarity import derive_layers, select_distinct, sweep_windows, usable  # noqa: E402
from src.terrain import load_surface, roughness_residual, slope_degrees  # noqa: E402

UTM = "EPSG:32719"


def write_plane(path, angle_deg, res=30.0, n=400, noise=0.0, seed=0):
    """Plano inclinado `angle_deg` hacia el este, en UTM (metros)."""
    x = np.arange(n) * res
    z = np.tile(x * np.tan(np.radians(angle_deg)), (n, 1))
    if noise:
        z = z + np.random.default_rng(seed).normal(0, noise, z.shape)
    with rasterio.open(path, "w", driver="GTiff", height=n, width=n, count=1, dtype="float32",
                       crs=UTM, transform=from_origin(500000, 7500000, res, res), nodata=-9999) as d:
        d.write(z.astype("float32"), 1)


def test_slope_of_known_plane():
    z = np.tile(np.arange(100) * 90 * np.tan(np.radians(15)), (100, 1))
    s = slope_degrees(z, 90.0)
    assert np.allclose(s[5:-5, 5:-5], 15.0, atol=1e-6)


def test_plane_has_zero_roughness_noise_has_positive():
    x = np.arange(100) * 90.0
    plane = np.tile(x * 0.3, (100, 1))
    assert np.nanmax(roughness_residual(plane, 90.0)[5:-5, 5:-5]) < 1e-3
    noisy = plane + np.random.default_rng(1).normal(0, 5, plane.shape)
    assert np.nanmedian(roughness_residual(noisy, 90.0)) > 1.0


def test_load_surface_resamples_to_target_resolution(tmp_path):
    p = tmp_path / "p.tif"
    write_plane(p, 10.0, res=30.0, n=300)
    s = load_surface(p, 90.0, dst_crs=UTM)
    assert s.res_m == 90.0 and s.z.shape == (100, 100)
    slope = slope_degrees(s.z, s.res_m)
    assert abs(np.nanmedian(slope) - 10.0) < 0.5


def test_sweep_counts_and_distinct_selection(tmp_path):
    p = tmp_path / "p.tif"
    write_plane(p, 8.0, res=30.0, n=1200, noise=3.0)  # 36 km x 36 km
    s = load_surface(p, 90.0, dst_crs=UTM)
    slope, rough = derive_layers(s)
    sw = sweep_windows(s, slope, rough, 3000, 1500)
    # 400 px; ventana 33 px (2970 m), paso 17 px (1530 m): (400-33)//17 + 1 = 22
    assert len(sw) == 22 * 22
    ok = usable(sw)
    assert len(ok) > 0 and (ok.valid_coverage_fraction >= 0.95).all()
    ok = ok.assign(D=np.arange(len(ok), dtype=float))
    top = select_distinct(ok, 3, 3000)
    cx, cy = top.center_x.to_numpy(), top.center_y.to_numpy()
    for i in range(3):
        for j in range(i + 1, 3):
            assert max(abs(cx[i] - cx[j]), abs(cy[i] - cy[j])) >= 3000
