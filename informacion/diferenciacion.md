# Diferenciación frente a lo que ya existe

Comparación entre dos referencias cercanas y la propuesta del proyecto. Pensada para el criterio de **creatividad** del jurado ([criterios_jurado.md](criterios_jurado.md)) y para el pitch.

## Lo que existe

### 1. NASA Planetary Analog Explorer

Fuente: [science.nasa.gov/solar-system/analog-explorer](https://science.nasa.gov/solar-system/analog-explorer/)

- Galería interactiva con 11 pares curados de sitios terrestres y de otros mundos (por ejemplo "Lava Caves: California y la Luna", "Basalt Landscapes: Kilauea y la Luna", "Subsurface Ice: Islandia y la Luna").
- Cada par es una imagen con descripción y un deslizador para compararlas.
- No muestra puntajes, métricas ni método de selección. Los números que aparecen son escalas de las imágenes.
- Limitación de la revisión: se leyó cerca del 77 % de la página. No se pudo confirmar si hay una entrada polar.

### 2. Artículo en NHSJS (abril 2026)

Fuente: [Finding Earth's Best Testbeds for Moon and Mars Rovers](https://nhsjs.com/2026/finding-earths-best-testbeds-for-moon-and-mars-rovers-a-quantitative-terrain-comparison/)

- Compara 10 sitios terrestres con 10 sitios lunares (solo mares basálticos) y 10 marcianos.
- Usa imágenes en escala de grises, no datos de elevación. Calcula 4 números por imagen (brillo medio, su variación y dos medidas de textura) y mide la distancia a un centroide por cuerpo.
- No tiene herramienta interactiva ni enlace a código o datos.
- Limitaciones declaradas por el autor: la iluminación, el albedo y la composición distorsionan la textura; la resolución afecta la rugosidad; la muestra es pequeña. Propone como trabajo futuro validar con pendiente y rugosidad calculadas desde DEM.
- Inconsistencias: el resumen dice que Devon Island sale entre los más parecidos, pero la tabla lo pone último. Las cifras no se pueden reproducir con lo publicado, así que no conviene apoyarse en sus resultados.
- Dato útil: Askja aparece entre los sitios más cercanos a la Luna. Sirve solo como respaldo débil, dado el método.

### Referencia que no se pudo confirmar

Un dataset de sitios análogos en data.gov (`known-terrestrial-analog-sites-for-planetary-science`) aparecía en una búsqueda, pero la URL devolvió error 404. No usarlo como referencia.

## Comparación

| Aspecto | Analog Explorer | Artículo NHSJS | Esta propuesta |
|---|---|---|---|
| Qué compara | Imágenes lado a lado | Brillo y textura de imágenes | Pendiente y rugosidad desde DEM, más temperatura, aridez, litología, cuevas e iluminación |
| Resultado | Galería fija | Ranking de 10 sitios | Ranking por cada sitio lunar, con la razón de cada coincidencia |
| Luna | 3 pares | Solo mares | Polo sur (Artemis), cuevas y basalto |
| Sitios nuevos | No, son curados | Casi todos conocidos | Búsqueda de sitios nuevos con justificación |
| Herramienta | Sí, cualitativa | No | Dashboard clicable con datos |
| Validación | No indica | Bootstrap, con inconsistencias | Controles positivos y negativos, y sensibilidad |
| Fuentes | Créditos de imagen | Archivos sin nombrar | Cada dato con fuente y estado de verificación |

## Los tres puntos más sólidos

1. **Datos de elevación en vez de imágenes.** Es lo que el propio artículo propone como siguiente paso. No es un invento propio, pero es un avance concreto y defendible.
2. **Polo sur y Artemis.** El artículo no los cubre y, hasta donde se pudo ver, la galería tampoco. La propuesta usa los sitios candidatos con iluminación y pendiente reales.
3. **Cuantificar lo que la galería muestra de forma cualitativa.** La galería dice que un sitio se parece a la Luna. La herramienta dice cuánto y en qué.

## Dónde no hay diferencia

- **Las cuevas como idea.** La galería ya incluye "Lava Caves: California y la Luna". El aporte sería cuantificarlas, no descubrirlas.
- **Sitios famosos.** Askja ya aparece en el artículo. Aporta como respaldo independiente, no como novedad.

## Condiciones para que la diferencia sea real

Estas diferencias valen solo si se construyen:

- Sin el **bloque 3** (DEM reales, ver [plan_proyecto.md](plan_proyecto.md)) se pierde el punto más fuerte. Protegerlo antes que pulir el dashboard.
- Sin **controles negativos** y sensibilidad, la validación se parece a la del artículo, que tiene inconsistencias.
- En el pitch hay que **citar el trabajo previo** y decir en qué se diferencia. Ocultarlo resta; reconocerlo suma.

## Frase para el pitch (borrador)

"La galería de NASA muestra pares curados y los estudios existentes comparan imágenes. Nosotros cuantificamos con elevación y datos de agencias, buscamos sitios nuevos y explicamos cada coincidencia, con foco en el polo sur de Artemis."
