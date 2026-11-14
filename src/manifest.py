"""Registro de procedencia de los archivos de datos (data_manifest.json)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import rasterio


def sha256(path, chunk=1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def describe_raster(path, role: str, url: str = "", version: str = "") -> dict:
    """Metadatos verificables de un ráster: tamaño, CRS, NoData, rango, sha256."""
    p = Path(path)
    with rasterio.open(p) as src:
        band = src.read(1, masked=True)
        return {
            "role": role,
            "path": str(p),
            "url": url,
            "version": version,
            "size_bytes": p.stat().st_size,
            "sha256": sha256(p),
            "accessed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "crs": src.crs.to_string() if src.crs else None,
            "shape": [src.height, src.width],
            "pixel_size": list(src.res),
            "nodata": src.nodata,
            "bounds": list(src.bounds),
            "dtype": src.dtypes[0],
            "valid_fraction": float(1 - np_mask_fraction(band)),
            "min": float(band.min()) if band.count() else None,
            "max": float(band.max()) if band.count() else None,
        }


def np_mask_fraction(band) -> float:
    return float(band.mask.mean()) if hasattr(band.mask, "mean") and band.mask.shape else float(bool(band.mask))
