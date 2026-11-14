"""Pipeline multirregión: compara ventanas lunares de Site01 con TODAS las regiones de regions.json.

Cada región se procesa en su UTM, con la misma escala (90 m) y las mismas métricas. La
escala robusta de normalización se calcula con las ventanas de TODAS las regiones juntas,
para que D sea comparable entre regiones. El contexto ambiental (sismicidad, volcanes,
temperatura, composición) no entra en D: se guarda aparte y solo se muestra.

    python fetch_regions.py                     # descarga DEMs y contexto
    python run_regions.py --lunar-dem data/raw/Site01_final_adj_5mpp_surf.tif \
        --lunar-ldec data/raw/Site01_final_adj_5mpp_ldec.tif --lunar-toterr data/raw/Site01_final_adj_5mpp_toterr.tif
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import transform as warp_transform

from run_pipeline import EARTH_DATASET, EARTH_URL, LUNAR_URL, VERSION, lunar_quality, window_polygon
from src.context import region_context
from src.enrich import (PENDING_VALIDATION, SLOPE_CLASSES, hillshade_png, lunar_grid, rank_lunar_windows,
                        read_window_native, slope_class_fractions)
from src.manifest import describe_raster
from src.similarity import (MIN_COVERAGE, WEIGHTS, compute_distances, derive_layers, robust_scales,
                            sweep_windows, usable, weight_sensitivity, window_pixels)
from src.terrain import load_surface, window_metrics

METRICS = ("slope_p50_deg", "slope_p90_deg", "roughness_270m_m", "relief_p95_p5_m")

# Contexto lunar. Solo lo respaldado por fuentes revisadas; el resto figura como pendiente.
MOON_CONTEXT = {
    "composition": {
        "status": "cualitativo",
        "text": "Tierras altas del polo sur. Según la literatura revisada, el impacto de Shackleton expuso anortosita muy pura (PAN) y un terreno estratificado de eyectas, cerca de Connecting Ridge.",
        "caveat": "Descripción cualitativa de la literatura; no está mapeada con datos propios. Los mapas de FeO y plagioclasa (Lemelin et al. 2022) son de ~1 km por píxel con incertidumbre de 9 wt %, y no se han incorporado.",
        "sources": ["https://boris.unibe.ch/179288/1/Boazman_2022_Planet._Sci._J._3_275.pdf"],
    },
    "temperature": {
        "status": "pendiente",
        "text": "Sin dato incorporado. LRO Diviner publica productos polares (Polar Cumulative Product, GDR L2), pero aún no se han descargado ni procesado.",
        "sources": ["https://ode.rsl.wustl.edu/moon/pagehelp/Content/Missions_Instruments/LRO/DIVINER/PCP.htm"],
    },
    "seismic_volcanic": {
        "status": "no_comparable",
        "text": "La Luna no tiene volcanismo activo. Por eso la actividad sísmica y volcánica terrestre se muestra solo como contexto de riesgo, nunca como similitud.",
        "sources": [],
    },
}


def utm_epsg(lat: float, lon: float) -> str:
    zone = int((lon + 180) // 6) + 1
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lunar-dem", required=True)
    ap.add_argument("--lunar-ldec")
    ap.add_argument("--lunar-toterr")
    ap.add_argument("--regions", default="regions.json")
    ap.add_argument("--res", type=float, default=90.0)
    ap.add_argument("--window-m", type=float, default=3000.0)
    ap.add_argument("--step-m", type=float, default=1500.0)
    ap.add_argument("--ref-center", type=float, nargs=2, default=(-11395.0, -10075.0),
                    help="ventana lunar de referencia para la prueba de sensibilidad (X Y, metros)")
    ap.add_argument("--out", default="data/outputs")
    ap.add_argument("--web-data", default="web/data")
    args = ap.parse_args()

    out, web = Path(args.out), Path(args.web_data)
    out.mkdir(parents=True, exist_ok=True)
    (web / "img").mkdir(parents=True, exist_ok=True)
    for old in (web / "img").glob("earth_*.png"):
        old.unlink()
    regions = {r["id"]: r for r in json.loads(Path(args.regions).read_text(encoding="utf-8"))}
    n = window_pixels(args.window_m, args.res)

    # --- Luna
    moon = load_surface(args.lunar_dem, args.res)
    m_slope, m_rough = derive_layers(moon)
    lrows = lunar_grid(moon, m_slope, m_rough, n, max(int(round(500 / args.res)), 1), args.lunar_ldec)
    print(f"Luna: {len(lrows)} ventanas")

    # --- Regiones
    surf, layers, frames, manifest, skipped = {}, {}, [], [], []
    manifest.append(describe_raster(args.lunar_dem, "lunar_dem", LUNAR_URL, "LOLA Site01 5 mpp"))
    for p, role in ((args.lunar_ldec, "lunar_ldec"), (args.lunar_toterr, "lunar_toterr")):
        if p:
            manifest.append(describe_raster(p, role, LUNAR_URL, "LOLA Site01 5 mpp"))
    for rid, r in regions.items():
        dem = Path(f"data/raw/{rid}_cop30.tif")
        if not dem.exists():
            print(f"[omitida] {rid}: falta {dem}")
            skipped.append(rid)
            continue
        epsg = utm_epsg(*r["center"])
        s = load_surface(dem, args.res, dst_crs=epsg)
        sl, ro = derive_layers(s)
        sw = sweep_windows(s, sl, ro, args.window_m, args.step_m)
        ok = usable(sw)
        regions[rid]["windows_total"], regions[rid]["windows_usable"] = int(len(sw)), int(len(ok))
        regions[rid]["utm"] = epsg
        manifest.append(describe_raster(dem, f"earth_dem:{rid}", EARTH_URL, EARTH_DATASET))
        if ok.empty:
            print(f"[sin ventanas útiles] {rid}")
            skipped.append(rid)
            continue
        lon_c, lat_c = warp_transform(s.crs, "EPSG:4326", ok.center_x.tolist(), ok.center_y.tolist())
        frames.append(ok.assign(region=rid, center_lat=lat_c, center_lon=lon_c))
        surf[rid], layers[rid] = s, sl
        print(f"{rid}: {len(ok)}/{len(sw)} ventanas útiles ({epsg})")
    pooled = pd.concat(frames, ignore_index=True)
    scales = robust_scales(pooled)  # escala conjunta: D comparable entre regiones
    print("Escalas conjuntas:", {k: round(v, 2) for k, v in scales.items()})

    # --- Ranking por ventana lunar
    ranks = rank_lunar_windows(lrows, pooled, scales, 3, args.window_m)
    for lr, rk in zip(lrows, ranks):
        rk["metrics"] = {k: lr[k] for k in METRICS}
        rk["lola_observed_fraction"] = lr["lola_observed_fraction"]
        rk["slope_classes"] = lr["slope_classes"]

    # --- Ventanas terrestres referenciadas (polígono, clases de pendiente, imagen)
    refs = {(t["region"], t["row"], t["col"]) for w in ranks for t in w["top"]}
    refs |= {(rid, t["row"], t["col"]) for w in ranks for rid, ts in w["by_region"].items() for t in ts}
    idx = pooled.set_index(["region", "row", "col"])
    earth_out = {}
    for (rid, r0, c0) in sorted(refs):
        row = idx.loc[(rid, r0, c0)]
        poly = window_polygon(surf[rid], r0, c0, n)
        lons, lats = [p[0] for p in poly], [p[1] for p in poly]
        z, dx, dy = read_window_native(f"data/raw/{rid}_cop30.tif", (min(lons), min(lats), max(lons), max(lats)))
        img = hillshade_png(z, dx, dy, web / "img" / f"earth_{rid}_{r0}_{c0}.png")
        earth_out[f"{rid}:{r0}_{c0}"] = {
            "region": rid, "center": [float(row.center_lat), float(row.center_lon)], "polygon": poly,
            "metrics": {k: float(row[k]) for k in METRICS},
            "valid_coverage_fraction": float(row.valid_coverage_fraction),
            "slope_classes": slope_class_fractions(layers[rid], r0, c0, n),
            "image": f"data/img/earth_{rid}_{r0}_{c0}.png" if img else None}
    print(f"{len(earth_out)} ventanas terrestres referenciadas")

    # --- Sensibilidad a pesos y control para la ventana lunar de referencia
    xr, yr = args.ref_center
    ref_i = int(np.argmin([(w["center_x"] - xr) ** 2 + (w["center_y"] - yr) ** 2 for w in ranks]))
    ref_w = ranks[ref_i]
    ranked = compute_distances(pooled, ref_w["metrics"], scales)
    sens = weight_sensitivity(ranked, 3, args.window_m)
    ctrl = ranked.sample(n=min(30, len(ranked)), random_state=0)
    ref_info = {"center": [ref_w["center_x"], ref_w["center_y"]], "sensitivity_weights": sens,
                "control_median_D": float(ctrl.D.median()), "all_windows_median_D": float(ranked.D.median()),
                "best_D": [t["D"] for t in ref_w["top"]]}

    # --- Contexto ambiental
    context = {rid: region_context(regions[rid]) for rid in surf}

    # --- Salidas
    with rasterio.open(args.lunar_dem) as src:
        b = src.bounds
        z, dx, dy = read_window_native(args.lunar_dem, (b.left, b.bottom, b.right, b.top))
    hillshade_png(z, dx, dy, web / "img" / "lunar_site01.png", out_px=1000)

    reg_meta = {rid: {k: regions[rid][k] for k in ("id", "name", "short", "status", "type", "center", "roi", "reference",
                                                    "coords", "windows_total", "windows_usable", "utm")} for rid in surf}
    params = {"analysis_scale_m": args.res, "window_size_m": args.window_m, "step_m": args.step_m,
              "actual_window_m": n * args.res, "actual_step_m": max(int(round(args.step_m / args.res)), 1) * args.res,
              "roughness_window_m": 270, "min_coverage": MIN_COVERAGE, "weights": WEIGHTS,
              "processing_version": VERSION, "normalization": "MAD robusta sobre todas las regiones (conjunta)"}
    meta = {
        "experiment": "Experimento 01 · Lunar Rover Terrain Analog",
        "lunar": {"site": "Site01 · Connecting Ridge", "crs": str(moon.crs), "bounds": [b.left, b.bottom, b.right, b.top],
                  "image": "data/img/lunar_site01.png", "window_m": n * args.res, "source_url": LUNAR_URL},
        "earth": {"dataset": EARTH_DATASET, "source_url": EARTH_URL, "windows_total": int(sum(r["windows_total"] for r in reg_meta.values())),
                  "windows_usable": int(len(pooled)),
                  "ranges": {k: [float(pooled[k].min()), float(pooled[k].max())] for k in METRICS}},
        "regions": reg_meta, "params": params, "scales": scales, "weights": WEIGHTS,
        "slope_class_labels": SLOPE_CLASSES, "pending_validation": PENDING_VALIDATION,
        "moon_context": MOON_CONTEXT, "reference_window": ref_info, "skipped_regions": skipped,
        "status": "Resultados preliminares; sin validación completa.",
    }
    (web / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    (web / "lunar_windows.json").write_text(json.dumps(ranks), encoding="utf-8")
    (web / "earth_windows.json").write_text(json.dumps(earth_out), encoding="utf-8")
    (web / "context.json").write_text(json.dumps(context, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "data_manifest.json").write_text(json.dumps(manifest, indent=2))
    shutil.copy(out / "data_manifest.json", web / "data_manifest.json")
    pooled.to_csv(out / "earth_windows.csv", index=False)
    (out / "metrics.json").write_text(json.dumps({"params": params, "scales": scales, "regions": reg_meta,
                                                  "reference_window": ref_info}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK -> {web}/ y {out}/. Ranking de referencia estable ante pesos alternativos: {sens['stable']}")


if __name__ == "__main__":
    main()
