# BOT 2.0 — 04B-v23a auditoría acotada de contenido AggTrades

## Estado

**PREDECLARADO — contenido remoto todavía no observado al fijar este protocolo.**

v23 probó que existen 1.920/1.920 ZIP mensuales Spot + USD-M para los 20 símbolos entre 2022 y 2025, pero el archivo comprimido total mide 222.518 GiB. v23a no formula una señal: valida si podemos leer y normalizar correctamente el contenido real con una muestra limitada y reproducible.

## Pregunta única

¿Los archivos diarios `aggTrades` de Binance Vision son parseables y consistentes, en ambos mercados y a través de los cambios históricos relevantes, para construir posteriormente features de order flow sin ambigüedad de esquema o tiempo?

## Muestra predeclarada

Los símbolos no se eligen por liquidez ni rendimiento. Se ordena alfabéticamente el universo fijo de 20 y se toma mínimo, mediana y máximo:

- `AAVEUSDT`;
- `ETHUSDT`;
- `XRPUSDT`.

Estratos temporales:

- marzo 2022: antes de la actualización histórica de aggregate trades señalada por Binance Public Data en abril de 2022;
- junio 2022: después de esa actualización;
- junio 2024: régimen Spot todavía en milisegundos;
- junio 2025: régimen Spot en microsegundos desde 2025-01-01.

Mercados:

- Spot;
- USD-M Futures.

Total objetivo: `3 símbolos × 4 periodos × 2 mercados = 24` ZIP diarios.

Dentro de cada símbolo/mercado/mes se listan los ZIP diarios no vacíos y se escoge determinísticamente el de tamaño mediano. No se usa precio, retorno ni ninguna métrica económica para escoger la fecha.

Límites de seguridad:

- máximo 128 MiB por ZIP seleccionado;
- máximo 1 GiB comprimido para toda la muestra;
- máximo dos descargas/parsers concurrentes.

## Validaciones de contenido

Para cada ZIP seleccionado:

- exactamente un CSV;
- 8 columnas para Spot y 7 para USD-M Futures;
- header opcional detectado defensivamente;
- aggregate trade ID entero no negativo, único y ascendente;
- first/last trade IDs enteros y `first <= last`;
- precio y cantidad finitos y estrictamente positivos;
- `isBuyerMaker` booleano estricto;
- `isBestMatch` booleano estricto en Spot;
- timestamps no descendentes;
- timestamps pertenecen al día UTC nominal del archivo;
- Spot antes de 2025: milisegundos;
- Spot desde 2025-01-01: microsegundos;
- USD-M Futures: milisegundos.

La reconstrucción del lado agresor se limita a comprobar semántica y capacidad técnica:

- `isBuyerMaker=false` → comprador agresor/taker buy;
- `isBuyerMaker=true` → vendedor agresor/taker sell.

Se contabilizan trades y volúmenes base/quote por lado, pero **no se relacionan con retornos**.

## Gate predeclarado

v23a pasa únicamente si:

- al menos 90% de las 24 muestras son válidas;
- cada estrato mercado/periodo tiene al menos 2 de 3 símbolos válidos;
- no se excede 1 GiB de transferencia objetivo;
- las muestras declaradas válidas cumplen todas las reglas estrictas de esquema, IDs, timestamps, precios, cantidades y booleanos.

## Prohibiciones

- no retornos;
- no labels;
- no correlaciones;
- no ranking económico;
- no optimización de ventanas;
- no señal long/short;
- no imputación;
- no GPT;
- no scanner;
- no RiskEngine;
- no PAPER operativo;
- no LIVE;
- no Render;
- 2026 cerrado;
- mayo-julio 2026 cerrado.

## Decisión posterior

Si v23a falla, se corrige únicamente una causa demostrable de transporte/formato y se repite el mismo protocolo; no se relajan reglas por conveniencia.

Si v23a pasa, queda técnicamente habilitado diseñar una **hipótesis económica nueva y predeclarada** sobre order flow. Esa hipótesis será otra versión y deberá fijar antes de mirar resultados su construcción, horizonte, baseline, hurdle y criterios de estabilidad.
