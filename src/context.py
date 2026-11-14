"""Contexto ambiental por región: sismicidad y volcanes, temperatura y composición.

IMPORTANTE: son descriptores de CONTEXTO, no entran en el puntaje D. Varían a
escala de decenas de km, no de 3 km, así que distinguen entre regiones y no
entre ventanas de una misma región. Todo valor sale de una API abierta y se
guarda con su fuente y fecha de consulta (data/context/<región>.json).

Fuentes: USGS Earthquake Catalog (FDSN), Smithsonian GVP (volcanes del Holoceno),
NASA POWER (climatología de temperatura) y Macrostrat (mapa geológico, escala pequeña).
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from datetime import date
from pathlib import Path

import requests

CACHE = Path("data/context")
USGS = "https://earthquake.usgs.gov/fdsnws/event/1"
GVP = ("https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs?service=WFS&version=1.0.0&request=GetFeature"
       "&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes&outputFormat=application/json")
POWER = "https://power.larc.nasa.gov/api/temporal/climatology/point"
MACROSTRAT = "https://macrostrat.org/api/v2/geologic_units/map"
RADIUS_KM = 100
SINCE = "1990-01-01"


def _get(url, params=None, timeout=60, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    return None


def haversine_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def seismicity(lat, lon):
    base = {"latitude": lat, "longitude": lon, "maxradiuskm": RADIUS_KM, "starttime": SINCE}
    out = {"radius_km": RADIUS_KM, "since": SINCE, "source": f"{USGS}/", "status": "ok"}
    for label, mag in (("m25", 2.5), ("m45", 4.5)):
        r = _get(f"{USGS}/count", {**base, "minmagnitude": mag, "format": "geojson"})
        out[f"count_{label}"] = r.json()["count"] if r else None
    r = _get(f"{USGS}/query", {**base, "minmagnitude": 2.5, "orderby": "magnitude", "limit": 1, "format": "geojson"})
    feats = r.json()["features"] if r else []
    out["max_magnitude"] = feats[0]["properties"]["mag"] if feats else None
    if out["count_m25"] is None:
        out["status"] = "sin_dato"
    out["caveat"] = "El conteo depende de la cobertura de estaciones sísmicas de cada región, no solo de su actividad."
    return out


def _gvp():
    f = CACHE / "gvp_holocene.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    r = _get(GVP, timeout=120)
    if not r:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(r.text, encoding="utf-8")
    return r.json()


def volcanoes(lat, lon):
    data = _gvp()
    out = {"radius_km": RADIUS_KM, "source": "https://volcano.si.edu/", "status": "ok"}
    if not data:
        return {**out, "status": "sin_dato"}
    near = []
    for f in data["features"]:
        x, y = f["geometry"]["coordinates"][:2]
        d = haversine_km(lat, lon, y, x)
        if d <= 300:
            p = f["properties"]
            near.append((d, p.get("Volcano_Name"), p.get("Last_Eruption_Year"), p.get("Primary_Volcano_Type")))
    near.sort()
    within = [n for n in near if n[0] <= RADIUS_KM]
    out["count_within_radius"] = len(within)
    n = near[0] if near else None
    out["nearest"] = {"name": n[1], "distance_km": round(n[0], 1), "last_eruption_year": n[2], "type": n[3]} if n else None
    return out


def temperature(lat, lon):
    r = _get(POWER, {"parameters": "T2M,T2M_MAX,T2M_MIN", "community": "RE", "longitude": lon, "latitude": lat, "format": "JSON"}, 90)
    out = {"source": "https://power.larc.nasa.gov/", "status": "sin_dato",
           "caveat": "Reanálisis (resolución de decenas de km) en el centro de la región; no es temperatura de superficie."}
    if not r:
        return out
    p = r.json()["properties"]["parameter"]
    months = [m for m in p["T2M"] if m != "ANN"]
    out.update({
        "status": "ok",
        "annual_mean_c": p["T2M"]["ANN"],
        "warmest_month_mean_max_c": max(p["T2M_MAX"][m] for m in months),
        "coldest_month_mean_min_c": min(p["T2M_MIN"][m] for m in months),
    })
    out["annual_range_c"] = round(out["warmest_month_mean_max_c"] - out["coldest_month_mean_min_c"], 2)
    return out


def composition(roi, n=4):
    """Litología del mapa geológico (Macrostrat, escala pequeña) en una malla n×n del ROI."""
    liths, names, valid = Counter(), Counter(), 0
    pts = [(roi["south"] + (i + .5) / n * (roi["north"] - roi["south"]), roi["west"] + (j + .5) / n * (roi["east"] - roi["west"]))
           for i in range(n) for j in range(n)]
    for la, lo in pts:
        r = _get(MACROSTRAT, {"lat": la, "lng": lo, "scale": "small", "format": "json"}, 40)
        units = r.json().get("success", {}).get("data", []) if r else []
        if units:
            valid += 1
            liths[(units[0].get("lith") or "sin clasificar").strip()] += 1
            names[(units[0].get("name") or "").strip()] += 1
        time.sleep(0.3)
    out = {"source": "https://macrostrat.org/", "samples": len(pts), "samples_with_data": valid,
           "caveat": "Mapa geológico a escala pequeña (compilación global): sirve para el tipo de roca dominante, no para detalle local."}
    if not valid:
        return {**out, "status": "sin_dato"}
    out.update({"status": "ok",
                "lithology": [{"lith": k, "share": round(v / valid, 2)} for k, v in liths.most_common(3)],
                "units": [k for k, _ in names.most_common(3) if k]})
    return out


def region_context(region: dict, refresh=False) -> dict:
    f = CACHE / f"{region['id']}.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text(encoding="utf-8"))
    lat, lon = region["center"]
    ctx = {"region": region["id"], "retrieved": date.today().isoformat(), "center": [lat, lon],
           "seismicity": seismicity(lat, lon), "volcanoes": volcanoes(lat, lon),
           "temperature": temperature(lat, lon), "composition": composition(region["roi"])}
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(ctx, indent=1, ensure_ascii=False), encoding="utf-8")
    return ctx
