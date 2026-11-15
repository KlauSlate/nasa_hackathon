# Qué es D y qué mide la validación

Nota para el equipo (y para explicar al jurado). Valores tomados de `data/outputs/validation.json`, `web/data/meta.json` y `web/app.js`.

## 1. La distancia D

**D es la distancia de similitud compuesta entre la ventana lunar de referencia (LOLA Site01) y una ventana de la Tierra (Copernicus DEM). Menor D = más parecida.**

```
D = 0,45 · (dif. pendiente) + 0,35 · (dif. rugosidad) + 0,20 · (dif. relieve)
```

- Cada diferencia se expresa en unidades de dispersión robusta (MAD), normalizada de forma conjunta sobre todas las regiones. Así pendiente, rugosidad y relieve son comparables entre sí.
- Los pesos 0,45 / 0,35 / 0,20 son **hipótesis del equipo**, no coeficientes calibrados.
- D = 0 sería una ventana idéntica. En la corrida actual, el mejor D de la ventana de referencia es ~0,88; los 3 candidatos finales (Haughton) tienen D ≈ 4,2 a 4,4.
- La interfaz muestra D en el badge de cada candidato, en la fila "Distancia total D" de la comparación y en el desglose Pendiente / Rugosidad / Relieve.

### Percentil
El percentil dice qué lugar ocupa la ventana respecto a todas las ventanas terrestres. Es relativo: puede ser alto (99,9) aunque D sea grande. Hay que mirar siempre D.

## 2. Similitud normalizada (maqueta) vs. validación

La maqueta (`nasa_3.jpeg`) muestra "Similitud (normalizada): 0,87". Eso es un índice por candidato. La **validación** es otra cosa: evalúa si el método funciona, no cuánto se parece cada candidato.

| | Qué responde | Dónde está |
|---|---|---|
| D / percentil / (índice 0–1 derivable de D) | ¿Qué tan parecida es esta zona a la referencia? | Por candidato |
| Validación (V1–V4) | ¿El método discrimina y es robusto? | Global, en `validation.json` |

Por eso **la validación no entrega un % de precisión por candidato**. Y el 42 % de V1 no es "precisión del 87 %".

El proyecto decidió no mostrar un "% de parecido" porque no hay verdad de terreno que lo respalde (ver README). Si se quiere un índice 0–1 como en la maqueta, puede derivarse de D (por ejemplo `1 / (1 + D)`), rotulado como **relativo**, no como precisión validada.

## 3. Resultados de la validación (14-11-2026)

| Prueba | Resultado | Estado |
|---|---|---|
| V1 discriminación entre regiones | Acierta 42 % vs 10,6 % por azar (4 veces mejor) | cumple |
| V2 recuperación con ruido | Rango mediano 3,5 % | cumple |
| V3 pesos | Misma región top-1: 79 % a 90 % | con reservas |
| V3 normalización | Misma región top-1: 52 % a 96 % | con reservas |
| V3 escala | 60 m: 74 %; 150 m: 58 % | con reservas |
| V4 incertidumbre LOLA | ~1,9° vs tolerancia 1,9° (razón 0,99) | con reservas |
| V4 producto DEM | Spearman ≥ 0,93 | con reservas |

Lectura: la métrica sí discrimina. Lo defendible es la **región ganadora**, no las 3 ventanas exactas. Solo 135 de 625 ventanas lunares tienen región ganadora estable en las tres pruebas de robustez. No hay verdad de terreno ni validación en campo.

## 4. Límites
- LOLA Site01 tiene ~90 % de píxeles interpolados: no inferir obstáculos pequeños.
- El DEM terrestre (~30 m) no resuelve rocas ni irregularidades menores.
- Suelo, adherencia, acceso y permisos quedan sin evaluar.
- No es una certificación de aptitud para rovers ni una validación de NASA.
