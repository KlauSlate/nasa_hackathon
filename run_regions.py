"""Pipeline multirregión: compara ventanas lunares de cada sitio de lunar_sites.json con TODAS las regiones de regions.json.

Cada región se procesa en su UTM, con la misma escala (90 m) y las mismas métricas. La
escala robusta de normalización se calcula con las ventanas de TODAS las regiones juntas,
para que D sea comparable entre regiones. El contexto ambiental (sismicidad, volcanes,
temperatura, composición) no entra en D: se guarda aparte y solo se muestra.

    python fetch_regions.py                     # descarga DEMs y contexto
    python run_regions.py                       # usa lunar_sites.json (sitios sin DEM en data/raw se omiten)
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
from src.base import base_suitability
from src import illum as illum_mod
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
    ap.add_argument("--lunar-sites", default="lunar_sites.json")
    ap.add_argument("--regions", default="regions.json")
    ap.add_argument("--res", type=float, default=90.0)
    ap.add_argument("--window-m", type=float, default=3000.0)
    ap.add_argument("--step-m", type=float, default=1500.0)
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

    # --- Luna (uno o varios sitios; X/Y son polares estereográficas y no se repiten entre sitios)
    sites_cfg = json.loads(Path(args.lunar_sites).read_text(encoding="utf-8"))
    sites, lrows, manifest = {}, [], []
    for sc in sites_cfg:
        if not Path(sc["dem"]).exists():
            print(f"[sitio lunar omitido] {sc['id']}: falta {sc['dem']}")
            continue
        moon = load_surface(sc["dem"], args.res)
        m_slope, m_rough = derive_layers(moon)
        lr = lunar_grid(moon, m_slope, m_rough, n, max(int(round(500 / args.res)), 1), sc.get("ldec"))
        for w in lr:
            w["site"] = sc["id"]
        if illum_mod.available():
            with rasterio.open(sc["dem"]) as src_b:
                bb = src_b.bounds
            layers_i = illum_mod.load_site_layers((bb.left, bb.bottom, bb.right, bb.top))
            if layers_i is not None:
                for w in lr:
                    w["illumination"] = illum_mod.window_illumination(layers_i, w["center_x"], w["center_y"], n * args.res)
            else:
                print(f"[sin mapa de iluminación] {sc['id']} queda fuera del mapa 85S-90S")
        else:
            print("[sin mapas de iluminación] faltan archivos en data/raw (ver src/illum.py)")
        lrows += lr
        sites[sc["id"]] = {"cfg": sc, "crs": str(moon.crs)}
        manifest.append(describe_raster(sc["dem"], f"lunar_dem:{sc['id']}", LUNAR_URL, f"LOLA {sc['id']} 5 mpp"))
        for key in ("ldec", "toterr"):
            if sc.get(key) and Path(sc[key]).exists():
                manifest.append(describe_raster(sc[key], f"lunar_{key}:{sc['id']}", LUNAR_URL, f"LOLA {sc['id']} 5 mpp"))
        print(f"Luna {sc['id']}: {len(lr)} ventanas")
    if not lrows:
        raise SystemExit("No hay ningún sitio lunar con DEM en data/raw.")
    if illum_mod.available():
        for lname, lpath in illum_mod.LAYERS.items():
            manifest.append(describe_raster(lpath, f"lunar_{lname}", illum_mod.SOURCE_URL, "LOLA polar illumination 85S-90S 60 m (Mazarico et al.)"))

    # --- Regiones
    surf, layers, frames, skipped = {}, {}, [], []
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
        rk["site"] = lr["site"]
        rk["metrics"] = {k: lr[k] for k in METRICS}
        rk["lola_observed_fraction"] = lr["lola_observed_fraction"]
        rk["slope_classes"] = lr["slope_classes"]
        rk["illumination"] = lr.get("illumination")
        rk["base_suitability"] = base_suitability(lr["slope_classes"], lr.get("illumination"))

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
    ref_site = next((sid for sid in sites if sites[sid]["cfg"].get("ref_center")), next(iter(sites)))
    xr, yr = sites[ref_site]["cfg"].get("ref_center") or (None, None)
    cand_ids = [i for i, w in enumerate(ranks) if w["site"] == ref_site]
    if xr is None:
        xr, yr = ranks[cand_ids[0]]["center_x"], ranks[cand_ids[0]]["center_y"]
    ref_i = min(cand_ids, key=lambda i: (ranks[i]["center_x"] - xr) ** 2 + (ranks[i]["center_y"] - yr) ** 2)
    ref_w = ranks[ref_i]
    ranked = compute_distances(pooled, ref_w["metrics"], scales)
    sens = weight_sensitivity(ranked, 3, args.window_m)
    ctrl = ranked.sample(n=min(30, len(ranked)), random_state=0)
    ref_info = {"site": ref_site, "center": [ref_w["center_x"], ref_w["center_y"]], "sensitivity_weights": sens,
                "control_median_D": float(ctrl.D.median()), "all_windows_median_D": float(ranked.D.median()),
                "best_D": [t["D"] for t in ref_w["top"]]}

    # --- Contexto ambiental
    context = {rid: region_context(regions[rid]) for rid in surf}

    # --- Salidas
    lunar_meta = {}
    for sid, info in sites.items():
        sc = info["cfg"]
        with rasterio.open(sc["dem"]) as src:
            bb = src.bounds
        z, dx, dy = read_window_native(sc["dem"], (bb.left, bb.bottom, bb.right, bb.top))
        hillshade_png(z, dx, dy, web / "img" / f"lunar_{sid}.png", out_px=1000)
        comp = sc.get("composition") or {
            "status": "pendiente",
            "text": "Sin descripción de composición incorporada para este sitio.",
            "caveat": "No se ha revisado literatura ni mapas de composición para este sitio.", "sources": []}
        lunar_meta[sid] = {"id": sid, "name": sc["name"], "short": sc["short"], "description": sc["description"],
                           "crs": info["crs"], "bounds": [bb.left, bb.bottom, bb.right, bb.top],
                           "image": f"data/img/lunar_{sid}.png", "window_m": n * args.res, "source_url": LUNAR_URL,
                           "illumination_source": illum_mod.SOURCE_URL, "composition": comp, "windows": int(sum(1 for w in ranks if w["site"] == sid))}

    reg_meta = {rid: {k: regions[rid][k] for k in ("id", "name", "short", "status", "type", "center", "roi", "reference",
                                                    "coords", "windows_total", "windows_usable", "utm")} for rid in surf}
    params = {"analysis_scale_m": args.res, "window_size_m": args.window_m, "step_m": args.step_m,
              "actual_window_m": n * args.res, "actual_step_m": max(int(round(args.step_m / args.res)), 1) * args.res,
              "roughness_window_m": 270, "min_coverage": MIN_COVERAGE, "weights": WEIGHTS,
              "processing_version": VERSION, "normalization": "MAD robusta sobre todas las regiones (conjunta)"}
    meta = {
        "experiment": "Experimento 01 · Lunar Rover Terrain Analog",
        "lunar_sites": lunar_meta, "default_site": ref_site, "source_url_moon": LUNAR_URL,
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
