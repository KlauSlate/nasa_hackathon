"""Fase 3 — Validación del método (Experimento 01).

No hay una "verdad de terreno" de análogos a escala de ventana de 3 km, así que no se puede medir
exactitud contra un estándar. Lo que sí se mide es si el método es:
  V1 discriminante   (¿la métrica distingue terrenos mejor que el azar?)
  V2 recuperable     (¿una ventana con ruido se encuentra a sí misma?)
  V3 robusto         (¿el ranking sobrevive a otros pesos, normalizaciones y escalas?)
  V4 creíble en datos (¿incertidumbre LOLA y producto DEM cambian la conclusión?)

Los umbrales de "cumple / con reservas" son criterios del equipo fijados ANTES de ver los resultados;
no son normas de NASA. Todo el cálculo sale de data/outputs/ y data/raw/.

    python validate.py                # todo (incluye sensibilidad a la escala, varios minutos)
    python validate.py --skip-scale   # pruebas rápidas
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds
from scipy.stats import spearmanr

from run_regions import METRICS, utm_epsg
from src.similarity import (ALT_WEIGHTS, METRIC_COLS, MIN_COVERAGE, WEIGHTS, compute_distances, derive_layers,
                            robust_scales, select_distinct, sweep_windows, usable, window_pixels)
from src.terrain import load_surface, window_metrics
from rasterio.warp import transform as warp_transform

# Criterios (heurísticos, definidos de antemano)
CRIT = {"recovery_lift": 2.0, "noise_rank_pct": 5.0, "stable_ok": 0.80, "stable_partial": 0.50,
        "slope_unc_ratio": 0.5, "dem_spearman": 0.90, "dem_delta_ratio": 0.5}


def verdict(ok: bool, partial: bool = False) -> str:
    return "cumple" if ok else ("con reservas" if partial else "no cumple")


def km_sep(a_lat, a_lon, b_lat, b_lon):
    dy = (a_lat - b_lat) * 110.54
    dx = (a_lon - b_lon) * 111.32 * np.cos(np.radians((a_lat + b_lat) / 2))
    return np.maximum(np.abs(dx), np.abs(dy))


def load_inputs(out: Path, web: Path):
    pooled = pd.read_csv(out / "earth_windows.csv")
    meta = json.loads((web / "meta.json").read_text(encoding="utf-8"))
    lunar = json.loads((web / "lunar_windows.json").read_text(encoding="utf-8"))
    return pooled, meta, lunar


# ---------------------------------------------------------------- V1 / V2
def v1_discrimination(P, scales, n_per_region=40, exclude_km=9.0, seed=0):
    """Una ventana consulta, sin sus vecinas de la misma región (<9 km): ¿su mejor coincidencia cae en su misma región?"""
    rng = np.random.default_rng(seed)
    hits, chance, per = [], [], {}
    for rid, g in P.groupby("region"):
        q = g.sample(n=min(n_per_region, len(g)), random_state=int(rng.integers(1e6)))
        h = []
        for _, r in q.iterrows():
            same = P.region == rid
            near = same & (km_sep(P.center_lat, P.center_lon, r.center_lat, r.center_lon) < exclude_km)
            cand = P[~near]
            d = compute_distances(cand, {c: r[c] for c in METRIC_COLS}, scales)
            best = d.loc[d.D.idxmin()]
            h.append(best.region == rid)
            chance.append(float((cand.region == rid).mean()))
        per[rid] = float(np.mean(h))
        hits += h
    acc, ch = float(np.mean(hits)), float(np.mean(chance))
    return {"accuracy_same_region": acc, "chance": ch, "lift": acc / ch if ch else None, "per_region": per,
            "n_queries": len(hits), "status": verdict(acc / ch >= CRIT["recovery_lift"] if ch else False)}


def v2_noise_recovery(P, scales, n=300, noise=0.5, seed=1):
    """Ventana + ruido gaussiano (σ = 0.5 escala robusta por métrica): ¿en qué posición queda la original entre todas?"""
    rng = np.random.default_rng(seed)
    q = P.sample(n=min(n, len(P)), random_state=2)
    ranks = []
    for idx, r in q.iterrows():
        vec = {c: r[c] + rng.normal(0, noise * scales[c]) for c in METRIC_COLS}
        d = compute_distances(P, vec, scales)
        ranks.append(int((d.D < d.loc[idx, "D"]).sum()) + 1)
    pct = np.array(ranks) / len(P) * 100
    return {"noise_sigma_scales": noise, "n_queries": len(ranks), "median_rank": float(np.median(ranks)),
            "median_rank_pct": float(np.median(pct)), "p90_rank_pct": float(np.percentile(pct, 90)), "windows_total": len(P),
            "status": verdict(np.median(pct) <= CRIT["noise_rank_pct"], np.median(pct) <= 2 * CRIT["noise_rank_pct"])}


# ---------------------------------------------------------------- V3
def _top(P, m, scales, weights):
    d = compute_distances(P, m, scales, weights)
    t = select_distinct(d, 3, 3000.0)
    return [(r.region, int(r.row), int(r.col)) for _, r in t.iterrows()]


def v3_weights_and_norm(P, lunar, scales):
    """Estabilidad del top 3 y de la región ganadora ante pesos y normalizaciones alternativas (las 625 ventanas lunares)."""
    norms = {"std_conjunta": {c: float(P[c].std()) for c in METRIC_COLS},
             "mad_por_region_mediana": {c: float(np.median([robust_scales(g)[c] for _, g in P.groupby("region")])) for c in METRIC_COLS},
             "mad_ventanas_lunares": {c: float(1.4826 * np.median(np.abs(np.array([w["metrics"][c] for w in lunar]) - np.median([w["metrics"][c] for w in lunar])))) or 1.0 for c in METRIC_COLS}}
    res = {"weights": {k: {"same_set": 0, "same_top1_region": 0} for k in ALT_WEIGHTS},
           "norm": {k: {"same_top1_region": 0, "etna_share": 0} for k in norms}}
    flags = []
    for w in lunar:
        base = [(t["region"], t["row"], t["col"]) for t in w["top"]]
        f = {}
        for k, wt in ALT_WEIGHTS.items():
            alt = _top(P, w["metrics"], scales, wt)
            res["weights"][k]["same_set"] += set(alt) == set(base)
            res["weights"][k]["same_top1_region"] += alt[0][0] == base[0][0]
            f[f"w_{k}"] = alt[0][0] == base[0][0]
        for k, sc in norms.items():
            alt = _top(P, w["metrics"], sc, WEIGHTS)
            res["norm"][k]["same_top1_region"] += alt[0][0] == base[0][0]
            res["norm"][k]["etna_share"] += alt[0][0] == "etna"
            f[f"n_{k}"] = alt[0][0] == base[0][0]
        flags.append(f)
    N = len(lunar)
    for blk in res.values():
        for v in blk.values():
            for kk in list(v):
                v[kk] = v[kk] / N
    wmin = min(v["same_top1_region"] for v in res["weights"].values())
    nmin = min(v["same_top1_region"] for v in res["norm"].values())
    base_etna = float(np.mean([w["top"][0]["region"] == "etna" for w in lunar]))
    res["base_etna_share"] = base_etna
    res["status_weights"] = verdict(wmin >= CRIT["stable_ok"], wmin >= CRIT["stable_partial"])
    res["status_norm"] = verdict(nmin >= CRIT["stable_ok"], nmin >= CRIT["stable_partial"])
    res["n_lunar_windows"] = N
    return res, flags


# ---------------------------------------------------------------- V4
def v4_lola_uncertainty(lunar, scales, slperr_path):
    """Incertidumbre de pendiente de LOLA (5 m) frente a la tolerancia (escala robusta de pendiente) del método."""
    vals = []
    with rasterio.open(slperr_path) as s:
        for w in lunar[::6]:
            h = 1485.0
            b = (w["center_x"] - h, w["center_y"] - h, w["center_x"] + h, w["center_y"] + h)
            a = s.read(1, window=from_bounds(*b, s.transform), masked=True)
            if a.count():
                vals.append(float(np.ma.median(a)))
    med = float(np.median(vals))
    ratio = med / scales["slope_p50_deg"]
    return {"median_slope_uncertainty_deg": med, "p90_slope_uncertainty_deg": float(np.percentile(vals, 90)),
            "tolerance_scale_deg": scales["slope_p50_deg"], "ratio": ratio, "n_windows": len(vals),
            "note": "Incertidumbre a 5 m (cota superior: al promediar a 90 m baja, pero no se ha cuantificado).",
            "status": verdict(ratio <= CRIT["slope_unc_ratio"], ratio <= 1.0)}


def v4_dem_product(scales, res=90.0, window_m=3000.0, step_m=1500.0):
    """Atacama con dos productos DEM independientes (Copernicus GLO-30 vs NASADEM): ¿dan las mismas métricas por ventana?"""
    epsg = utm_epsg(-23.25, -68.5)
    out = {}
    tabs = []
    for name, path in (("cop30", "data/raw/atacama_cop30.tif"), ("nasadem", "data/raw/atacama_nasadem.tif")):
        s = load_surface(path, res, dst_crs=epsg)
        sl, ro = derive_layers(s)
        t = usable(sweep_windows(s, sl, ro, window_m, step_m))
        tabs.append(t.reset_index(drop=True))
    a, b = tabs
    xa, ya = a.center_x.to_numpy(), a.center_y.to_numpy()
    d2 = (xa[:, None] - b.center_x.to_numpy()[None, :]) ** 2 + (ya[:, None] - b.center_y.to_numpy()[None, :]) ** 2
    j = d2.argmin(axis=1)
    ok = d2[np.arange(len(a)), j] < (res * 1.5) ** 2
    A, Bm = a[ok].reset_index(drop=True), b.iloc[j[ok]].reset_index(drop=True)
    rows = {}
    for c in METRIC_COLS:
        rho = float(spearmanr(A[c], Bm[c])[0])
        dr = float(np.median(np.abs(A[c] - Bm[c])) / scales[c])
        rows[c] = {"spearman": rho, "median_abs_diff_in_scales": dr}
    worst_rho = min(v["spearman"] for v in rows.values())
    worst_d = max(v["median_abs_diff_in_scales"] for v in rows.values())
    out = {"windows_compared": int(ok.sum()), "metrics": rows, "worst_spearman": worst_rho, "worst_median_diff_scales": worst_d,
           "status": verdict(worst_rho >= CRIT["dem_spearman"] and worst_d <= CRIT["dem_delta_ratio"],
                             worst_rho >= 0.75)}
    return out


# ---------------------------------------------------------------- V3b: escala de análisis
def v3_scale(lunar, regions, base_scales, moon_dem, res_list=(60.0, 150.0), window_m=3000.0, step_m=1500.0):
    """Repite el ranking con otra escala de análisis (mismas ventanas lunares, mismos centros)."""
    base_top1 = [w["top"][0]["region"] for w in lunar]
    base_D = np.array([w["top"][0]["D"] for w in lunar])
    out = {}
    for res in res_list:
        moon = load_surface(moon_dem, res)
        m_sl, m_ro = derive_layers(moon)
        n = window_pixels(window_m, res)
        frames = []
        for rid, r in regions.items():
            dem = Path(f"data/raw/{rid}_cop30.tif")
            s = load_surface(dem, res, dst_crs=utm_epsg(*r["center"]))
            sl, ro = derive_layers(s)
            ok = usable(sweep_windows(s, sl, ro, window_m, step_m))
            lon, lat = warp_transform(s.crs, "EPSG:4326", ok.center_x.tolist(), ok.center_y.tolist())
            frames.append(ok.assign(region=rid, center_lat=lat, center_lon=lon))
        P = pd.concat(frames, ignore_index=True)
        sc = robust_scales(P)
        top1, bestD, valid = [], [], []
        for w in lunar:
            col, row = ~moon.transform @ (w["center_x"], w["center_y"])
            r0, c0 = int(round(row - n / 2)), int(round(col - n / 2))
            if r0 < 0 or c0 < 0 or r0 + n > moon.z.shape[0] or c0 + n > moon.z.shape[1]:
                top1.append(None); bestD.append(np.nan); valid.append(False); continue
            m = window_metrics(moon.z, m_sl, m_ro, r0, c0, n)
            if "slope_p50_deg" not in m or m["valid_coverage_fraction"] < MIN_COVERAGE:
                top1.append(None); bestD.append(np.nan); valid.append(False); continue
            d = compute_distances(P, m, sc)
            b = d.loc[d.D.idxmin()]
            top1.append(b.region); bestD.append(float(b.D)); valid.append(True)
        v = np.array(valid)
        same = np.array([a == b for a, b in zip(top1, base_top1)])
        out[str(int(res))] = {"windows_valid": int(v.sum()), "same_top1_region": float(same[v].mean()),
                              "spearman_bestD": float(spearmanr(np.array(bestD)[v], base_D[v])[0]),
                              "flags": [bool(s) if val else None for s, val in zip(same, valid)],
                              "windows_earth": int(len(P))}
    worst = min(v["same_top1_region"] for v in out.values())
    out["status"] = verdict(worst >= CRIT["stable_ok"], worst >= CRIT["stable_partial"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/outputs")
    ap.add_argument("--web-data", default="web/data")
    ap.add_argument("--lunar-dem", default="data/raw/Site01_final_adj_5mpp_surf.tif")
    ap.add_argument("--slperr", default="data/raw/Site01_final_adj_5mpp_slperr.tif")
    ap.add_argument("--skip-scale", action="store_true")
    args = ap.parse_args()
    out, web = Path(args.out), Path(args.web_data)
    P, meta, lunar_all = load_inputs(out, web)
    # La validación usa el DEM y la incertidumbre de un solo sitio (el de referencia, Site01).
    # Las ventanas de otros sitios quedan sin banderas de robustez y la interfaz lo indica.
    vsite = meta.get("default_site", "site01")
    lunar = [w for w in lunar_all if w.get("site", vsite) == vsite]
    scales = meta["scales"]
    regions = {rid: r for rid, r in meta["regions"].items()}
    print(f"{len(P)} ventanas terrestres, {len(lunar)} lunares")

    R = {"criteria_note": "Umbrales definidos por el equipo antes de ver los resultados; no son normas de NASA.", "criteria": CRIT}
    print("V1 discriminación..."); R["v1_discrimination"] = v1_discrimination(P, scales)
    print("V2 recuperación con ruido..."); R["v2_noise_recovery"] = v2_noise_recovery(P, scales)
    print("V3 pesos y normalización..."); R["v3_weights_norm"], flags = v3_weights_and_norm(P, lunar, scales)
    print("V4 incertidumbre LOLA..."); R["v4_lola_uncertainty"] = v4_lola_uncertainty(lunar, scales, args.slperr)
    print("V4 producto DEM (Atacama)..."); R["v4_dem_product"] = v4_dem_product(scales)
    scale_flags = None
    if not args.skip_scale:
        print("V3 escala de análisis (60 y 150 m)...")
        R["v3_scale"] = v3_scale(lunar, regions, scales, args.lunar_dem)
        scale_flags = {k: R["v3_scale"][k].pop("flags") for k in ("60", "150")}
    (out / "validation.json").write_text(json.dumps(R, indent=2, ensure_ascii=False), encoding="utf-8")
    (web / "validation.json").write_text(json.dumps(R, indent=1, ensure_ascii=False), encoding="utf-8")

    # robustez por ventana lunar (para mostrarla junto al ranking)
    for i, w in enumerate(lunar):
        f = flags[i]
        w["robust"] = {"weights_top1_region": all(v for k, v in f.items() if k.startswith("w_")),
                       "norm_top1_region": all(v for k, v in f.items() if k.startswith("n_"))}
        if scale_flags:
            w["robust"]["scale_top1_region"] = (None if any(scale_flags[k][i] is None for k in scale_flags)
                                                else all(scale_flags[k][i] for k in scale_flags))
    (web / "lunar_windows.json").write_text(json.dumps(lunar_all), encoding="utf-8")
    print("OK ->", out / "validation.json")


if __name__ == "__main__":
    main()
