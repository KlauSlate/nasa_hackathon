"""Descarga de datos terrestres vía OpenTopography.

Zona de búsqueda: cráter Haughton (isla Devon, Nunavut, Canadá), ~75,4° N.
NASADEM/SRTM solo cubren hasta 60° de latitud, así que para esa latitud se usa
Copernicus GLO-30 (ESA, ~30 m, cobertura global). Se pide con una API key
gratuita (.env -> OPENTOPO_KEY).

LOLA Site01 se baja a mano desde el índice oficial de NASA/PGDA
(https://pgda.gsfc.nasa.gov/products/78): Site01_final_adj_5mpp_surf.tif y las
capas _ldec, _toterr y _slperr, a data/raw/.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
OPENTOPO_URL = "https://portal.opentopography.org/API/globaldem"

# ROI provisional alrededor del cráter Haughton (~75,38° N, 89,67° O; diámetro ~23 km).
# Incluye el cráter y su entorno de meseta. Es una hipótesis de búsqueda, ajustable.
HAUGHTON_ROI = {"south": 75.10, "north": 75.65, "west": -91.00, "east": -88.30}


def download_earth_dem(roi=HAUGHTON_ROI, demtype="COP30", out="data/raw/haughton_cop30.tif") -> Path:
    """Baja un DEM global recortado al ROI (lat/lon WGS84, ~30 m)."""
    key = os.getenv("OPENTOPO_KEY")
    if not key or key == "pega_tu_key_aqui":
        raise RuntimeError("Falta OPENTOPO_KEY en tu archivo .env (copia .env.example).")

    params = {"demtype": demtype, **roi, "outputFormat": "GTiff", "API_Key": key}
    r = requests.get(OPENTOPO_URL, params=params, timeout=300)
    # El servicio no siempre declara Content-Type tiff: se valida la firma del archivo.
    is_tiff = r.content[:2] in (b"II", b"MM") and r.content[2:4] in (bytes([42,0]), bytes([0,42]), bytes([43,0]), bytes([0,43]))
    if r.status_code != 200 or not is_tiff:
        raise RuntimeError(f"OpenTopography respondió {r.status_code}: {r.text[:300]}")

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    print(f"OK {demtype}: {out} ({len(r.content) / 1e6:.1f} MB)")
    return out


if __name__ == "__main__":
    download_earth_dem()
