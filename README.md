# Analog Mission Designer — Experimento 01: Lunar Rover Terrain Analog

NASA Space Apps Challenge 2026. Compara ventanas de 3×3 km de varios sitios del polo sur lunar (**Site01 Connecting Ridge, Site04 borde de Shackleton, Site20 meseta Leibnitz beta, Site23 macizo Malapert**; LOLA 5 m, ver `lunar_sites.json`) con ventanas de **9 regiones** (Haughton, Atacama, Etna, Lanzarote, Askja, Cinder Lake y las candidatas Khaybar, Undara y Jingpo; Copernicus DEM GLO-30, ver `regions.json`) usando pendiente, rugosidad y relieve local a escala común. Muestra las métricas por separado y un ranking de **similitud relativa**, nunca un "% de parecido".

> Estado: pipeline ejecutado con LOLA Site01 y Copernicus DEM reales (primera corrida, ventana lunar provisional). Resultados preliminares en `data/outputs/`; aún sin validación ni análisis de robustez completo.
> No es una certificación de aptitud para rovers ni una validación de NASA.

## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python -m pytest -q tests       # valida el cálculo (planos sintéticos)
```

## Datos (no se versionan, van en `data/raw/`)

| Fuente | Qué bajar |
|---|---|
| LOLA sitios del polo sur ([PGDA](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/)) | por sitio: `SiteNN_final_adj_5mpp_surf.tif`, `_ldec.tif`, `_toterr.tif` (Site01 además `_slperr.tif`, que usa la validación). Los sitios sin archivos en `data/raw/` se omiten |
| Iluminación LOLA ([PGDA](https://pgda.gsfc.nasa.gov/products/69)) | `AVGVISIB_85S_060M_201608.TIF` (iluminación media), `AVGVISIB_85S_060M_201608_EARTH.TIF` (visibilidad de la Tierra), `LPSR_85S_060M_201608.TIF` (sombra permanente), en `data/raw/`. Sin ellos el pipeline corre sin esa capa |
| Copernicus DEM GLO-30 ([DOI](https://doi.org/10.5270/ESA-c5d3d65)) | `python -m src.download` (OpenTopography, requiere `OPENTOPO_KEY` en `.env`). NASADEM no cubre 75° N |

Las regiones y sus cajas de búsqueda están en `regions.json` (coordenadas aproximadas, por verificar). Cada una se procesa en su UTM.

## Ejecutar (multirregión)

```bash
python fetch_regions.py      # DEM de cada región (OpenTopography) + contexto ambiental
python run_regions.py --lunar-dem data/raw/Site01_final_adj_5mpp_surf.tif \
    --lunar-ldec data/raw/Site01_final_adj_5mpp_ldec.tif --lunar-toterr data/raw/Site01_final_adj_5mpp_toterr.tif
```

Genera `web/data/` (interfaz) y `data/outputs/` (CSV, manifiesto, métricas). La normalización es **conjunta** (MAD sobre todas las regiones), de modo que D es comparable entre regiones.

### Contexto ambiental (no entra en D)
Por región, desde APIs abiertas y con fecha de consulta (`data/context/`): sismicidad (USGS), volcanes del Holoceno (Smithsonian GVP), temperatura (NASA POWER) y composición (litología del mapa geológico, Macrostrat). Del lado lunar: composición cualitativa de la literatura, temperatura pendiente (Diviner) y la actividad sísmica/volcánica marcada como no comparable.

## Ejecutar (una sola región, flujo original)

```bash
python run_pipeline.py --lunar-dem data/raw/Site01_final_adj_5mpp_surf.tif \
    --lunar-ldec data/raw/Site01_final_adj_5mpp_ldec.tif \
    --lunar-toterr data/raw/Site01_final_adj_5mpp_toterr.tif \
    --earth-dem data/raw/haughton_cop30.tif
```

Sin `--lunar-center X Y` la ventana lunar se elige automáticamente (mayor fracción observada según LDEC). Es provisional: inspecciónala y fija la definitiva con `--lunar-center` (metros, CRS polar del ráster). La elección queda registrada en `metrics.json`.

Salidas en `data/outputs/`: `candidates.geojson`, `metrics.csv`, `metrics.json` (parámetros, escalas, controles, sensibilidad), `data_manifest.json` (URL, tamaño, sha256, CRS, NoData).

## Interfaz web

```bash
cd web && python -m http.server 8000     # abrir http://localhost:8000
```

Página estática (HTML + JS + Leaflet) que solo lee `web/data/` (generado por el pipeline). Se elige una ventana lunar con un clic y se ven el ranking, el comparador y la exportación a GeoJSON/CSV. Los mapas terrestres necesitan internet para los tiles.

## Método

1. Cada superficie en su propio sistema métrico (Luna: polar estereográfico; Tierra: UTM 19S). Se promedian a 90 m. No se comparan coordenadas ni elevaciones absolutas.
2. Por ventana: pendiente P50/P90, rugosidad (desviación del residuo a un plano local de 270 m), relieve P95–P5, cobertura válida.
3. Descarta ventanas con <95 % de píxeles útiles (umbral provisional del equipo).
4. `D = 0,45·d(pendiente) + 0,35·d(rugosidad) + 0,20·d(relieve)`, cada `d` normalizada con MAD robusta del conjunto terrestre. Pesos: hipótesis de ingeniería.
5. Top 3 sin solapamiento, 10 ventanas de control aleatorias alejadas, y sensibilidad a pesos alternativos.

Como 3000 y 1500 m no son múltiplos de 90 m, el tamaño y paso reales (2970 m y 1530 m) se guardan en `metrics.json`.

## Estructura

```
src/terrain.py      carga/reproyección a escala común, pendiente, rugosidad, métricas por ventana
src/similarity.py   barrido, distancias, top-k sin solape, controles, sensibilidad
src/manifest.py     procedencia (sha256, CRS, NoData)
src/download.py     Copernicus DEM vía OpenTopography
run_regions.py      pipeline multirregión + datos de la interfaz
validate.py         validación (discriminación, ruido, pesos, normalización, escala, LOLA, producto DEM)
fetch_regions.py    descarga DEM y contexto de cada región
regions.json        catálogo de regiones
src/context.py      contexto ambiental (USGS, GVP, NASA POWER, Macrostrat)
run_pipeline.py     flujo de una sola región
web/                interfaz estática (index.html, app.js, style.css)
tests/              pruebas con terrenos sintéticos de respuesta conocida
```

## Límites

LOLA Site01 tiene ~90 % de píxeles interpolados; el DEM terrestre (~30 m) no resuelve rocas ni irregularidades pequeñas; suelo, adherencia, acceso y permisos quedan sin evaluar. Los parámetros no están calibrados contra rovers.
