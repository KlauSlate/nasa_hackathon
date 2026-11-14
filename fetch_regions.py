"""Descarga el DEM (Copernicus GLO-30) y el contexto ambiental de cada región de regions.json."""
import json
import sys
from pathlib import Path

from src.context import region_context
from src.download import download_earth_dem

regions = json.loads(Path("regions.json").read_text(encoding="utf-8"))
only = set(sys.argv[1:])
for r in regions:
    if only and r["id"] not in only:
        continue
    dem = Path(f"data/raw/{r['id']}_cop30.tif")
    if not dem.exists():
        try:
            download_earth_dem(r["roi"], "COP30", str(dem))
        except Exception as e:  # una región fallida no debe frenar a las demás
            print(f"[FALLO DEM] {r['id']}: {e}")
    else:
        print(f"[ya existe] {dem}")
    ctx = region_context(r)
    print(f"[contexto] {r['id']}: sismos M2.5+ {ctx['seismicity'].get('count_m25')}, "
          f"T media {ctx['temperature'].get('annual_mean_c')}, litología {ctx['composition'].get('lithology')}")
