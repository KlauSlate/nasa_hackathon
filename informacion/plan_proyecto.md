# Plan del proyecto: Analog Mission Designer (Experimento 01)

Desafío: NASA Space Apps 2026, "Identify Earth Locations that Analog the Permanent Moon Base Location and Mars" (texto en [desafio_oficial.md](desafio_oficial.md)).

- **Entrega:** domingo 15-11-2026, cierre 23:59 hora local (el video y el formulario se resuelven en el pitch).
- **Enfoque:** la Luna primero (polo sur, Connecting Ridge). Marte queda como ampliación futura.
- **Datos:** hay API key de OpenTopography (sirve para Copernicus DEM). LOLA Site01 se baja a mano desde NASA/PGDA.
- **Especificación técnica:** PDF "NASA Space Challenge 2026" (producto y protocolo experimental). Maquetas de pantalla en `nasa_0` a `nasa_3.jpeg`.

## Idea central

El usuario indica la misión y su objetivo (MVP: navegación robótica de un rover), selecciona una **ventana cuadrada de 3×3 km sobre la Luna** y la herramienta devuelve un **ranking de ventanas terrestres** (cráter Haughton, isla Devon, Canadá) con métricas comparables, la razón de la coincidencia, la incertidumbre y lo que NO se puede concluir.

Flujo de la maqueta:
1. Seleccionar referencia lunar (nasa_1): ventana sobre Connecting Ridge con resumen topográfico.
2. Definir área terrestre (nasa_2): ROI de Haughton, tamaño de ventana y escala común.
3. Analizar y comparar.
4. Resultados (nasa_3): top 3 en mapa, ranking, comparación Luna vs. candidato, exportación.

**Las maquetas usan datos simulados** (cifras, fotos y similitudes). Ninguno de esos valores puede aparecer en la demo; todo número debe salir del pipeline.

## Qué hace la solución (y qué no)

- Compara pendiente (P50, P90 e histograma), rugosidad (residuo sobre un plano local de 270 m) y relieve local (P95–P5) a escala común de 90 m, cada superficie en su propio sistema métrico.
- Distancia compuesta `D = 0,45·pendiente + 0,35·rugosidad + 0,20·relieve`, normalizada con MAD robusta. Los pesos son hipótesis, no coeficientes calibrados.
- Es **similitud morfológica relativa**, no equivalencia planetaria ni certificación para rovers. No reproduce gravedad, suelo, iluminación ni obstáculos menores a la resolución.

## Estado actual

| Pieza | Estado |
|---|---|
| Repo reorganizado (`src/`, `tests/`, `run_pipeline.py`) | Hecho |
| Pendiente, rugosidad, relieve, barrido, ranking, controles, sensibilidad a pesos, manifiesto | Hecho, probado solo con datos sintéticos (4 pruebas pasan) |
| Descarga Copernicus DEM GLO-30 (OpenTopography) | Hecho: `data/raw/haughton_cop30.tif` (55 MB, ROI completo, 100 % válido, elevaciones −1 a 477 m) |
| Datos reales LOLA Site01 y Copernicus DEM | Hecho. LOLA: surf, ldec, toterr y slperr (16×16 km, ~9,5 % de píxeles observados) |
| Primera corrida real (ventana lunar fila 51, col 68; centro X=−11395, Y=−10075) | Hecho, resultados en `data/outputs/`. Ventana lunar aún provisional |
| Ventana lunar definitiva | Pendiente de confirmación del equipo |
| Ranking para una ventana lunar arbitraria | Hecho en datos: `lunar_windows.json` (625 ventanas lunares con su top 3) y `earth_windows.csv`. Falta el consumo desde la interfaz |
| Percentil, clases 0–5°/5–15°/>15°, texto de coincidencias, hillshade, lista de validación pendiente | Hecho (en `candidates.geojson` e `img/`) |
| Multirregión (9 regiones, `regions.json`), normalización conjunta, `run_regions.py` | Hecho y ejecutado con datos reales (18.750 entradas de ranking verificadas contra la interfaz) |
| Contexto ambiental por región (sismicidad USGS, volcanes GVP, temperatura NASA POWER, litología Macrostrat) | Hecho para las 9 regiones; Jingpo sin dato de litología. No entra en D |
| Contexto lunar | Composición cualitativa (literatura); temperatura **pendiente** (Diviner sin procesar); sismos/volcanes no comparable |
| Fase 3 · Validación (`validate.py`, paso 4 de la interfaz, `data/outputs/validation.json`) | Hecha. V1 y V2 cumplen; V3a, V3b, V3c, V4a y V4b quedan **con reservas** (ver abajo) |
| Frontend (`web/`, 3 pantallas, ventana lunar clicable, filtro de región, contexto, exportación) | Hecho, sin probar aún en navegador por el equipo |

## Decisiones tomadas

| Tema | Decisión |
|---|---|
| Zona terrestre | **Cráter Haughton** (isla Devon, Nunavut; ~75,4° N), ya no Atacama. Es un análogo conocido: el objetivo es caracterizar qué partes de Haughton se parecen a la ventana lunar, no "descubrir" un análogo nuevo |
| Datos terrestres | Copernicus DEM GLO-30 (ESA, ~30 m) vía OpenTopography. NASADEM/SRTM solo llegan a 60° de latitud y no cubren Haughton |
| ROI | lat 75,10 a 75,65; lon −91,00 a −88,30 (hipótesis, ajustable). UTM 16N (EPSG:32616) |
| Escala | 90 m. Con ella la ventana real es 2970 m (33 px) y el paso 1530 m (17 px); se registran en `metrics.json` |
| Similitud en pantalla | No mostrar "0,87" sin definición. Mostrar D, componentes y percentil ("más parecida que el X % de las ventanas del ROI") |
| Incertidumbre | LOLA tiene capa de error (`toterr`). Copernicus DEM no incluye una capa de error equivalente. Mostrar la lunar y la cobertura; no inventar propagación |
| Imágenes de candidatos | Hillshade calculado del DEM (o imagen satelital con etiqueta). No fotos de suelo |
| Ventana lunar arbitraria | El barrido terrestre se calcula una vez; solo se recalcula la ventana lunar. Ranking instantáneo y alojable en una página estática |
| Controles de nasa_2 | Solo lectura en el MVP (ROI, 3×3 km, 90 m fijos) |

## Roadmap de implementación

Orden pensado para el cierre del domingo 15 a las 23:59. Las horas son estimaciones.

### Fase 1 — Datos reales (bloqueante, ~2–3 h)
- Bajar `Site01_final_adj_5mpp_surf.tif`, `_ldec.tif`, `_toterr.tif` (y `_slperr.tif`) a `data/raw/`.
- Ejecutar `python -m src.download` para el DEM de Haughton (lat 75,10 a 75,65; lon −91,00 a −88,30).
- Inspeccionar CRS, NoData, rango, fracción interpolada y cobertura. Elegir la ventana lunar de 3×3 km mirando el hillshade y fijarla con `--lunar-center`.
- Primer `run_pipeline.py` real. **Hito: una comparación Luna–Tierra con números reales.**
- Si falla la descarga de LOLA o del DEM terrestre, aplicar las contingencias de la especificación (recorte validado, ROI menor) y documentarlo.

### Fase 2 — Ranking para cualquier ventana lunar (~3 h)
- Separar el pipeline en dos partes: tabla terrestre (`earth_windows.csv` con todas las ventanas y sus métricas) y capas lunares.
- Calcular métricas de ventanas lunares sobre una malla (paso ~250–500 m) y exportarlas a JSON.
- Función de ranking reutilizable: dado un vector lunar, devuelve D, componentes y percentil.
- Exportar hillshade de la ventana lunar y de cada candidato, y el histograma de pendientes en clases 0–5°, 5–15°, >15° (las de la maqueta).
- Definir y documentar la incertidumbre mostrada.

### Fase 3 — Validación (~2 h)
- **Prueba de recuperación:** tomar una ventana de Haughton como "referencia" y comprobar que el ranking la recupera arriba (cubre "¿funciona de verdad?").
- Contraste con ventanas de control y sensibilidad a pesos y escala (se reporta si el ranking es inestable).
- Segundo indicador topográfico fuera del puntaje, y búsqueda en literatura para no llamar "nuevo análogo" a una zona ya documentada.
- Si no hay buenos candidatos, el resultado negativo explicado es válido.

### Fase 4 — Frontend (~5–6 h)
- Página estática (HTML + JS/React, MapLibre o Leaflet) que lee los JSON precalculados; sin servidor.
- Pantallas: inicio y experimento (nasa_0), selección de ventana lunar (nasa_1), configuración en solo lectura (nasa_2), resultados con top 3, comparador y exportación CSV/GeoJSON (nasa_3).
- Sección visible de límites y validación pendiente por candidato.
- Marcar la UI como prototipo si algún dato no está calculado.

### Fase 5 — Entrega (~3 h)
- README, nota metodológica y fuentes citadas.
- Las 4 reglas de entrega: nombre y resumen, link a demo y proyecto, datos NASA y otras fuentes, cómo se usó la IA (ver [reglas_entrega.md](reglas_entrega.md)).
- Guion y video del pitch. Mensaje: "flujo reproducible del objetivo de misión a candidatos con evidencia y límites", sin afirmar validación de NASA.

### Resultados de la validación (14-11-2026)
Umbrales definidos por el equipo antes de ver los resultados (no son normas de NASA).

| Prueba | Resultado | Estado |
|---|---|---|
| V1 Poder discriminante | Una ventana (sin vecinas <9 km) encuentra su mejor coincidencia en su región el 42 % de las veces frente a 10,6 % por azar (×4,0) | cumple |
| V2 Recuperación con ruido | Con ruido de 0,5 escalas, la ventana original queda en mediana en el puesto 711 de 20.241 (3,5 %) | cumple |
| V3a Pesos alternativos | Región ganadora igual en 79–90 %; top 3 exacto idéntico solo en 19–37 % | con reservas |
| V3b Normalización alternativa | Región igual en 52–96 %; Etna gana en 49 % con la normalización base y en 22–50 % con las alternativas | con reservas |
| V3c Escala 60/150 m | Región igual en 74 % (60 m) y 58 % (150 m); correlación del mejor D 0,95 y 0,91 | con reservas |
| V4a Incertidumbre LOLA | Incertidumbre de pendiente (5 m) mediana 1,88° frente a la escala de 1,89° (razón 0,99) | con reservas |
| V4b Producto DEM (Atacama, COP30 vs NASADEM) | Spearman 0,99 pendiente, 1,0 relieve, 0,93 rugosidad; rugosidad difiere 0,65 escalas | con reservas |

Lectura: la métrica sí discrimina; lo defendible es la **región ganadora** y no las 3 ventanas exactas. Solo 135 de 625 ventanas lunares tienen región ganadora estable en las tres pruebas de robustez (pesos, normalización y escala). El dominio de Etna (49 % de las ventanas) depende de la normalización. No hay verdad de terreno ni validación en campo.

### Contexto ambiental (decidido)
Temperatura, composición y actividad sísmica/volcánica se muestran como **contexto por región**, no como puntaje: varían a decenas de km y no distinguen ventanas de una misma región. La actividad sísmica y volcánica se presenta como riesgo, nunca como similitud (la Luna no tiene volcanismo activo). Pendiente: temperatura lunar (LRO Diviner) y composición cuantitativa lunar.

### Si falta tiempo (de lo último a lo primero a recortar)
1. Controles interactivos de la pantalla 2.
2. Selección libre de ventana lunar: dejar 3–5 ventanas prefijadas.
3. Comparación de rutas con límites de pendiente hipotéticos.
4. Frontend avanzado: mantener solo la pantalla de resultados.

**No se recorta:** datos reales, métricas por componente, límites visibles y reproducibilidad.

## Riesgos

- Descargas pesadas de LOLA o de la API de OpenTopography.
- Píxeles lunares interpolados (~90 %): no inferir obstáculos pequeños.
- **Confirmado en la corrida real:** Site01 (ventana de prueba) es mucho más empinado que todo el ROI de Haughton (pendiente mediana 16,9° frente a un máximo de 13,0° en la zona; relieve 791 m frente a 372 m). Para esa ventana el mejor D es ~4,2. Solo 244 de las 625 ventanas lunares caen dentro del rango de Haughton; la interfaz avisa cuando una ventana queda fuera.
- Sin enmascarar agua ni hielo: el ROI incluye ventanas planas (relieve 0) que podrían sesgar las escalas robustas.
- 3000 y 1500 m no son múltiplos de 90 m (ver "Decisiones tomadas").
- Tiempo: la fecha de cierre es el domingo 23:59.

## Criterios del jurado y cómo se cubren

Ver [criterios_jurado.md](criterios_jurado.md). Validez se apoya en la prueba de recuperación, los controles y la sensibilidad; Relevancia, en que responde al enunciado con datos abiertos y una herramienta.

## Archivos del proyecto

```
informacion/desafio_oficial.md   texto oficial del desafío
informacion/plan_proyecto.md     este plan
informacion/nasa_0..3.jpeg       maquetas (datos simulados)
informacion/*.docx               documentos de parámetros (v1 Marte, v2 criterios lunares)
src/terrain.py                   DEM a escala común, pendiente, rugosidad, métricas por ventana
src/similarity.py                barrido, distancias, top-k sin solape, controles, sensibilidad
src/manifest.py                  procedencia de los datos (sha256, CRS, NoData)
src/download.py                  Copernicus DEM vía OpenTopography
run_pipeline.py                  ejecuta el flujo completo
tests/test_terrain.py            pruebas con terrenos sintéticos
README.md                        puesta en marcha y método
```

---

# Referencia para fases posteriores

Lo que sigue viene del plan anterior (varios sitios y parámetros). No es parte del MVP del Experimento 01, pero se conserva como diccionario de parámetros y base para ampliar.

## Parámetros posibles (más allá de la topografía)

| # | Parámetro | Luna | Tierra | Estado |
|---|---|---|---|---|
| 1 | Pendiente | LOLA | Copernicus DEM | En el MVP |
| 2 | Rugosidad | LOLA | Copernicus DEM | En el MVP |
| 3 | Rango térmico diario | Diviner | ERA5 o WorldClim | Pendiente |
| 4 | Aridez | Sin agua líquida | WorldClim o CHELSA | Pendiente, solo lado Tierra |
| 5 | Litología | Mapas geológicos USGS | GLiM | Pendiente, categórica |
| 6 | Cuevas y tubos de lava | Pozos de Marius Hills | Catálogos de cuevas | Pendiente |
| 7 | Hielo o permafrost | Polos | Mapas de permafrost | Recomendado |
| 8 | Iluminación (sitios polares) | Mapas del polo sur | Latitud y duración del día | Pendiente |

Altitud y UV de los .docx describen Atacama y no la Luna; quedan fuera.

## Sitios lunares candidatos

Regiones de Artemis a menos de 6° del polo sur: Shackleton (Connecting Ridge), Faustini Rim A, de Gerlache y Haworth. Criterios de la literatura: iluminación de al menos 65 %, pendientes bajo 15° y cercanía a sombra permanente. Además Marius Hills (tubos de lava) y Mare Tranquillitatis (basalto). Fuente: [Artemis III candidate sites](https://www.astronomy.com/space-exploration/here-are-the-nine-sites-where-artemis-3-might-land-on-the-moon/). Los conteos varían entre fuentes.

## Sitios terrestres ya conocidos (para contrastar resultados)

Kilauea, Lava Beds, Haughton. Un buen método debería ubicarlos arriba para referencias lunares equivalentes.

### Grupo A (usados por agencias)

| Sitio | Por qué es análogo lunar | Fuente |
|---|---|---|
| Askja y Mývatn (Islandia) | Paisaje volcánico basáltico. Nueve de los doce astronautas que caminaron en la Luna entrenaron allí en 1965 y 1967 | [Hey Iceland](https://www.heyiceland.is/blog/nanar/7292/the-lunar-and-other-extra-terrestrial-landscapes-of-iceland) |
| Cinder Lake (Arizona) | 47 cráteres en cenizas basálticas para reproducir parte del Mare Tranquillitatis a escala 1:1. Entrenamiento de Apolo 15 a 17 | [Apollo program training](https://en.wikipedia.org/wiki/Apollo_program_training) |
| Lanzarote (España) | Terreno volcánico con tubos de lava (La Corona, 8 km). La ESA entrena allí a astronautas de Artemis | [Phys.org/AFP](https://phys.org/news/2022-11-moon-astronauts-flock-spanish-isle.html) |
| Etna (Italia) | Campos de lava y suelo granular. La ESA y DLR probaron rovers lunares a 2,600 m en 2022 | [ANSA](https://www.ansa.it/amp/english/news/2022/06/27/moon-rover-being-tested-on-etna_0d1988a6-423b-4045-bca5-7ee368cb3422.html) |

Las fuentes discrepan sobre cuánto se parece Islandia a la Luna; decirlo así en la presentación.

### Grupo B (más novedosos, menos documentados)

| Sitio | Por qué es análogo lunar | Fuente |
|---|---|---|
| Jingpo Lake (China) | Propuesto como análogo del complejo Marius Hills | [Remote Sensing](https://mdpi-res.com/d_attachment/remotesensing/remotesensing-18-00512/article_deploy/remotesensing-18-00512.pdf) |
| Undara (Australia) | Tubos de lava terrestres más estudiados; miden 10 a 100 m de ancho, mucho menos que los lunares estimados | [Sauro et al.](https://cris.unibo.it/retrieve/bf298592-3a07-4d19-8979-599f91ae8131/2020%2bSauro%2bet%2bal%2bESR%2bLava%2btubes.pdf) |
| Harrat Khaybar (Arabia Saudita) | Campo de lava extenso y reciente en entorno hiperárido | Solo notas divulgativas; falta estudio científico |

Descartados por ahora: Emi Koussi (Chad) y Danakil (Etiopía), vinculados con Marte y Titán, no con la Luna.

Hueco abierto: no se encontró evidencia que ligue la Antártida (Valles Secos, Dome C) ni Svalbard con los candidatos polares de Artemis. Haughton cubre parte del caso.

## Estado de la verificación de los documentos .docx

**Confirmado:**
- Composición de EAC-1A (SiO₂ 43.7 %, MgO 11.9 %, TiO₂ 2.4 %, mediana de unos 70 µm). [Engelschiøn et al. 2020](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7096503/).
- Densidad del regolito: EAC-1A 1.45 g/cm³; núcleos de Apolo entre 1.30 y 1.83 g/cm³. [LUNA](https://luna-analog-facility.de/en/how-uniform-is-our-test-field/).
- Haughton: -16 °C de promedio y menos de 13 mm de precipitación al año.
- Haughton: permafrost a 60 cm, en un solo sitio de Isla Devon. [CREWES 2003](https://www.crewes.org/Documents/ResearchReports/2003/2003-08.pdf).
- UV en Marte: 79.6 % UVA, 15.3 % UVB, 5.1 % UVC (REMS). Falta contrastar con el paper de PNAS 2025.

**Imprecisos:**
- "Cero redondeo" en partículas lunares: BP-1 es angular, pero JSC-1A va de angular a subredondeado según [NASA](https://ares.jsc.nasa.gov/projects/simulants/jsc-1-1a.html).
- Percloratos de Marte "0.5 a 1 %": Phoenix midió 0.4 a 0.6 %.

**Sin respaldo o contradictorios (no usar sin rehacer):**
- Humedad relativa de Haughton (50 a 70 % frente a "desierto polar seco").
- Percloratos de Atacama (hasta 1,000 mg/kg): un perfil de Yungay da unos 4 mg/kg y otro sitio supera 100 mg/kg.
- Humedad del suelo de Atacama (0.66 a 2 %).
- UV de Marte en W/m².
- Dimensiones de tubos de lava del v2 (5 a 30 m, techo de más de 2 m).

**Problemas de estructura del v2:** mezcla propiedades de la Luna con criterios para elegir un sitio terrestre (altitud, UV y precipitación son rasgos de Atacama) y casi no cubre el polo sur (iluminación, sombras permanentes, hielo).
