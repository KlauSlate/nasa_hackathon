"""Pipeline del Experimento 01 (Lunar Rover Terrain Analog).

Uso (con los GeoTIFF reales ya descargados en data/raw/):

    python run_pipeline.py --lunar-dem data/raw/Site01_final_adj_5mpp_surf.tif \
        --lunar-ldec data/raw/Site01_final_adj_5mpp_ldec.tif \
        --lunar-toterr data/raw/Site01_final_adj_5mpp_toterr.tif \
        --earth-dem data/raw/atacama_nasadem.tif

Opcional: --lunar-center X Y (metros, CRS polar lunar del ráster) para fijar la
ventana lunar después de inspeccionarla. Sin eso se elige automáticamente la
ventana de mayor cobertura/observación y se avisa de que es provisional.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import rasterio.transform
from rasterio.warp import transform as warp_transform
from rasterio.windows import from_bounds

from src.enrich import (PENDING_VALIDATION, SLOPE_CLASSES, compare_text, hillshade_png, lunar_grid,
                        percentile_similarity, rank_lunar_windows, read_window_native, slope_class_fractions)
from src.manifest import describe_raster
from src.similarity import (MIN_COVERAGE, WEIGHTS, compute_distances, derive_layers, pick_controls,
                            robust_scales, select_distinct, sweep_windows, usable, weight_sensitivity,
                            window_pixels)
from src.terrain import load_surface, slope_histogram, window_metrics

VERSION = "v1-experimental"
EXPERIMENT_ID = "lunar-rover-terrain-analog-v1"
LUNAR_URL = "https://pgda.gsfc.nasa.gov/products/78"
EARTH_URL = "https://doi.org/10.5270/ESA-c5d3d65"  # Copernicus DEM GLO-30 (ESA)
EARTH_NAME = "Cráter Haughton (isla Devon, Nunavut, Canadá)"
EARTH_DATASET = "Copernicus DEM GLO-30 (ESA, ~30 m)"


def lunar_quality(path_ldec, path_toterr, bounds):
    """Fracción de píxeles realmente observados (LDEC>0) e incertidumbre mediana en la ventana."""
    q = {"lola_observed_fraction": None, "lola_toterr_median_m": None}
    if path_ldec:
        with rasterio.open(path_ldec) as s:
            a = s.read(1, window=from_bounds(*bounds, s.transform), masked=True)
            if a.size:
                q["lola_observed_fraction"] = float((np.ma.filled(a, 0) > 0).mean())
    if path_toterr:
        with rasterio.open(path_toterr) as s:
            a = s.read(1, window=from_bounds(*bounds, s.transform), masked=True)
            if a.count():
                q["lola_toterr_median_m"] = float(np.ma.median(a))
    return q


def window_polygon(surface, r0, c0, n):
    corners = [(c0, r0), (c0 + n, r0), (c0 + n, r0 + n), (c0, r0 + n), (c0, r0)]
    xy = [surface.transform @ c for c in corners]
    lon, lat = warp_transform(surface.crs, "EPSG:4326", [p[0] for p in xy], [p[1] for p in xy])
    return [[float(a), float(b)] for a, b in zip(lon, lat)]


def pick_lunar_window(surf, slope, rough, n, args):
    if args.lunar_center:
        x, y = args.lunar_center
        col, row = ~surf.transform @ (x, y)
        return int(round(row - n / 2)), int(round(col - n / 2)), "user"
    sw = sweep_windows(surf, slope, rough, args.window_m, args.window_m / 2)
    sw = usable(sw, MIN_COVERAGE)
    if sw.empty:
        raise SystemExit("Ninguna ventana lunar de 3x3 km cumple la cobertura mínima. "
                         "Revisa el DEM o baja el umbral y documéntalo.")
    best = None
    for _, r in sw.iterrows():
        b = rasterio.transform.array_bounds(n, n, surf.transform * rasterio.Affine.translation(r.col, r.row))
        q = lunar_quality(args.lunar_ldec, None, b)["lola_observed_fraction"] or 0.0
        if best is None or q > best[0]:
            best = (q, int(r.row), int(r.col))
    return best[1], best[2], "auto"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lunar-dem", required=True)
    ap.add_argument("--earth-dem", required=True)
    ap.add_argument("--lunar-ldec")
    ap.add_argument("--lunar-toterr")
    ap.add_argument("--lunar-center", type=float, nargs=2, metavar=("X", "Y"))
    ap.add_argument("--earth-crs", default="EPSG:32616", help="UTM del ROI (Haughton: zona 16N)")
    ap.add_argument("--res", type=float, default=90.0, help="escala de análisis (m/píxel)")
    ap.add_argument("--window-m", type=float, default=3000.0)
    ap.add_argument("--step-m", type=float, default=1500.0)
    ap.add_argument("--out", default="data/outputs")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # --- Etapa 1: manifiesto de datos
    manifest = [describe_raster(args.lunar_dem, "lunar_dem", LUNAR_URL, "LOLA Site01 5 mpp"),
                describe_raster(args.earth_dem, "earth_dem", EARTH_URL, EARTH_DATASET)]
    for p, role in ((args.lunar_ldec, "lunar_ldec"), (args.lunar_toterr, "lunar_toterr")):
        if p:
            manifest.append(describe_raster(p, role, LUNAR_URL, "LOLA Site01 5 mpp"))
    (out / "data_manifest.json").write_text(json.dumps(manifest, indent=2))

    # --- Etapa 2/3: superficies a escala común y métricas
    moon = load_surface(args.lunar_dem, args.res)
    earth = load_surface(args.earth_dem, args.res, dst_crs=args.earth_crs)
    n = window_pixels(args.window_m, args.res)
    m_slope, m_rough = derive_layers(moon)
    e_slope, e_rough = derive_layers(earth)

    r0, c0, how = pick_lunar_window(moon, m_slope, m_rough, n, args)
    lunar = window_metrics(moon.z, m_slope, m_rough, r0, c0, n)
    if lunar.get("valid_coverage_fraction", 0) < MIN_COVERAGE:
        raise SystemExit(f"La ventana lunar elegida tiene cobertura {lunar.get('valid_coverage_fraction'):.2f} < {MIN_COVERAGE}.")
    cx, cy = moon.transform @ (c0 + n / 2, r0 + n / 2)
    bounds = (moon.transform @ (c0, r0 + n)) + (moon.transform @ (c0 + n, r0))
    lunar_ref = {"selection": how, "center_x_m": cx, "center_y_m": cy, "crs": str(moon.crs),
                 "row": r0, "col": c0, "metrics": lunar,
                 "slope_hist": slope_histogram(m_slope, r0, c0, n),
                 "slope_classes": {"labels": SLOPE_CLASSES, "fractions": slope_class_fractions(m_slope, r0, c0, n)},
                 "quality": lunar_quality(args.lunar_ldec, args.lunar_toterr, bounds)}

    img = out / "img"
    zl, dxl, dyl = read_window_native(args.lunar_dem, bounds)
    lunar_ref["hillshade"] = hillshade_png(zl, dxl, dyl, img / "lunar_reference.png")

    # --- Etapa 4: barrido terrestre y ranking
    sweep = sweep_windows(earth, e_slope, e_rough, args.window_m, args.step_m)
    ok = usable(sweep)
    params = {"analysis_scale_m": args.res, "window_size_m": args.window_m, "step_m": args.step_m,
              "actual_window_m": n * args.res, "actual_step_m": max(int(round(args.step_m / args.res)), 1) * args.res,
              "roughness_window_m": 270, "min_coverage": MIN_COVERAGE, "weights": WEIGHTS,
              "earth_crs": args.earth_crs, "processing_version": VERSION}
    summary = {"experiment_id": EXPERIMENT_ID, "earth_region": {"name": EARTH_NAME, "dataset": EARTH_DATASET, "url": EARTH_URL}, "params": params, "lunar_reference": lunar_ref,
               "earth_windows_total": int(len(sweep)), "earth_windows_usable": int(len(ok))}

    if ok.empty:
        summary["status"] = "no_candidates"
        summary["conclusion"] = "No se identificaron ventanas terrestres con datos suficientes bajo estos criterios."
        (out / "metrics.json").write_text(json.dumps(summary, indent=2))
        print(summary["conclusion"])
        return

    scales = robust_scales(ok)
    ranked = compute_distances(ok, lunar, scales)
    top = select_distinct(ranked, 3, args.window_m)
    controls = pick_controls(ranked, top, n=10, min_sep_m=2 * args.window_m)
    sens = weight_sensitivity(ranked, 3, args.window_m)

    # --- Etapa 5: exportación
    feats = []
    for i, (_, r) in enumerate(top.iterrows(), 1):
        poly = window_polygon(earth, int(r.row), int(r.col), n)
        clon, clat = warp_transform(earth.crs, "EPSG:4326", [r.center_x], [r.center_y])
        lons = [p_[0] for p_ in poly]
        lats = [p_[1] for p_ in poly]
        ze, dxe, dye = read_window_native(args.earth_dem, (min(lons), min(lats), max(lons), max(lats)))
        cand_img = hillshade_png(ze, dxe, dye, img / f"candidate-{i:03d}.png")
        cand_metrics = {k: float(r[k]) for k in ("slope_p50_deg", "slope_p90_deg", "roughness_270m_m", "relief_p95_p5_m")}
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [poly]},
                      "properties": {
            "candidate_id": f"candidate-{i:03d}", "experiment_id": EXPERIMENT_ID, "source_body": "Earth",
            "reference_site": "Moon / LOLA / Site01 Connecting Ridge",
            "center": {"latitude": clat[0], "longitude": clon[0]}, "area_km2": (args.window_m / 1000) ** 2,
            "metrics": {k: float(r[k]) for k in ("slope_p50_deg", "slope_p90_deg", "roughness_270m_m", "relief_p95_p5_m")},
            "ranking": {"position": i, "normalized_distance": float(r.D),
                        "component_distances": {"slope": float(r.d_slope), "roughness": float(r.d_rough), "relief": float(r.d_relief)}},
            "data_quality": {"valid_coverage_fraction": float(r.valid_coverage_fraction),
                             "lunar_lola_uncertainty_assessed": lunar_ref["quality"]["lola_toterr_median_m"] is not None,
                             "warnings": [
                                 "Referencia lunar con alta proporción de píxeles interpolados: no inferir obstáculos pequeños.",
                                 f"{EARTH_DATASET}: no resuelve rocas ni irregularidades menores.",
                                 "Acceso, permisos y propiedades del suelo sin evaluar."]},
            "processing": {"analysis_scale_m": args.res, "window_size_m": args.window_m, "processing_version": VERSION},
            "evidence": {"lunar_dataset_url": LUNAR_URL, "earth_dataset_url": EARTH_URL},
            "similarity_percentile": percentile_similarity(ranked["D"].to_numpy(), float(r.D)),
            "slope_classes": {"labels": SLOPE_CLASSES,
                              "fractions": slope_class_fractions(e_slope, int(r.row), int(r.col), n)},
            "comparison": compare_text(lunar, cand_metrics, scales),
            "hillshade": cand_img,
            "pending_validation": PENDING_VALIDATION,
            "status": "computed"}})
    (out / "candidates.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, indent=2))

    ranked["role"] = "window"
    ranked.loc[top.index, "role"] = "top"
    ranked.loc[controls.index, "role"] = "control"
    ranked.to_csv(out / "metrics.csv", index=False)

    # --- Datos para la interfaz: tabla terrestre completa y ranking por ventana lunar
    lon_all, lat_all = warp_transform(earth.crs, "EPSG:4326", ok.center_x.tolist(), ok.center_y.tolist())
    ok_out = ok.assign(center_lat=lat_all, center_lon=lon_all)
    ok_out.to_csv(out / "earth_windows.csv", index=False)
    lrows = lunar_grid(moon, m_slope, m_rough, n, max(int(round(500 / args.res)), 1), args.lunar_ldec)
    ranks = rank_lunar_windows(lrows, ok, scales, 3, args.window_m)
    for lr, rk in zip(lrows, ranks):
        rk["metrics"] = {k: lr[k] for k in ("slope_p50_deg", "slope_p90_deg", "roughness_270m_m", "relief_p95_p5_m")}
        rk["lola_observed_fraction"] = lr["lola_observed_fraction"]
        rk["slope_classes"] = lr["slope_classes"]
    (out / "lunar_windows.json").write_text(json.dumps(
        {"crs": str(moon.crs), "window_m": n * args.res, "scales": scales, "weights": WEIGHTS,
         "windows": ranks}, indent=1))

    summary.update({
        "status": "computed", "scales": scales,
        "sensitivity_weights": sens,
        "controls": {"n": int(len(controls)), "median_D": float(controls.D.median()) if len(controls) else None,
                     "top_D": [float(x) for x in top.D]},
        "earth_windows_median_D": float(ranked.D.median()),
    })
    (out / "metrics.json").write_text(json.dumps(summary, indent=2))
    print(f"Ventanas terrestres útiles: {len(ok)}/{len(sweep)}. Top D: {[round(x, 2) for x in top.D]}")
    print(f"Ranking estable ante pesos alternativos: {sens['stable']}")
    print(f"Salidas en {out}/")


if __name__ == "__main__":
    main()
