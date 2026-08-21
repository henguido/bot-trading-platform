# BOT 2.0 — 04B-v23a auditoría acotada de contenido AggTrades

## Estado

**Resultado final: `DATASET_AGGTRADES_CONTENIDO_APTO_V23A`.**

v23 probó que existen 1.920/1.920 ZIP mensuales Spot + USD-M para los 20 símbolos entre 2022 y 2025, pero el archivo comprimido total mide 222.518 GiB. v23a no formula una señal: valida si podemos leer y normalizar correctamente el contenido real con una muestra limitada y reproducible.

## Pregunta única

¿Los archivos diarios `aggTrades` de Binance Vision son parseables y consistentes, en ambos mercados y a través de los cambios históricos relevantes, para construir posteriormente features de order flow sin ambigüedad de esquema o tiempo?

## Muestra predeclarada

Los símbolos no se eligieron por liquidez ni rendimiento. Se ordenó alfabéticamente el universo fijo de 20 y se tomó mínimo, mediana y máximo:

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

Dentro de cada símbolo/mercado/mes se listaron los ZIP diarios no vacíos y se escogió determinísticamente el de tamaño mediano. No se usó precio, retorno ni ninguna métrica económica para escoger la fecha.

Límites de seguridad:

- máximo 128 MiB por ZIP seleccionado;
- máximo 1 GiB comprimido para toda la muestra;
- máximo dos descargas/parsers concurrentes.

## Validaciones de contenido

Para cada ZIP seleccionado se exigió:

- exactamente un CSV;
- 8 columnas para Spot y 7 para USD-M Futures;
- header opcional detectado defensivamente;
- aggregate trade ID entero no negativo, único y ascendente;
- first/last trade IDs enteros y `first <= last`;
- precio y cantidad finitos y estrictamente positivos;
- `isBuyerMaker` booleano estricto;
- `isBestMatch` booleano estricto en Spot;
- timestamps no descendentes;
- timestamps pertenecientes al día UTC nominal del archivo;
- Spot antes de 2025: milisegundos;
- Spot desde 2025-01-01: microsegundos;
- USD-M Futures: milisegundos.

La reconstrucción del lado agresor se limitó a comprobar semántica y capacidad técnica:

- `isBuyerMaker=false` → comprador agresor/taker buy;
- `isBuyerMaker=true` → vendedor agresor/taker sell.

Los trades y volúmenes base/quote por lado se contabilizaron, pero **no se relacionaron con retornos**.

## Gate predeclarado

v23a solo pasaba si:

- al menos 90% de las 24 muestras eran válidas;
- cada estrato mercado/periodo tenía al menos 2 de 3 símbolos válidos;
- no se excedía 1 GiB de transferencia objetivo;
- las muestras declaradas válidas cumplían todas las reglas estrictas de esquema, IDs, timestamps, precios, cantidades y booleanos.

## Resultado remoto

Workflow aislado `research-04b` #73, job `aggtrades-content-v23a`: **success**.

Resultado:

- selecciones encontradas: **24/24**;
- tamaño comprimido total seleccionado: **0.136 GiB**;
- muestras de contenido válidas: **24/24 = 100%**;
- filas `aggTrades` reales inspeccionadas: **10.140.629**;
- headers detectados: **6**;
- Spot en milisegundos: **9 muestras**;
- Spot en microsegundos: **3 muestras**;
- USD-M Futures en milisegundos: **12 muestras**;
- trades reconstruidos como comprador agresor: **4.995.431**;
- trades reconstruidos como vendedor agresor: **5.145.198**;
- motivos de rechazo: **ninguno**.

Los ocho estratos predeclarados pasaron **3/3**:

- Spot 2022-03;
- Spot 2022-06;
- Spot 2024-06;
- Spot 2025-06;
- USD-M Futures 2022-03;
- USD-M Futures 2022-06;
- USD-M Futures 2024-06;
- USD-M Futures 2025-06.

El contenido real confirmó el cambio esperado de unidad temporal de Spot: las nueve muestras Spot anteriores a 2025 usan milisegundos y las tres de 2025 usan microsegundos. Las doce muestras USD-M Futures usan milisegundos.

Artifact:

- `aggtrades-content-audit-v23a-2022-2025`;
- id `9451241262`;
- digest `sha256:5015ef6b7539b00192d3dfe4796b48e79538fdc0f7bacf8bf7f1201d817845ed`.

## Validación técnica

PR temporal: **#25 — WIP: auditar BOT 2.0-04B v23a contenido AggTrades**.

HEAD de implementación evaluada: `5271a13e276dd49e2a22e0f938615663870883cd`.

CI general #85: **success**.

- **1126 tests passed**;
- 1391 warnings;
- `compileall backend` OK;
- frontend build OK, **841 módulos** transformados;
- v20.1 volvió a resultar `DATASET_POSICIONAMIENTO_APTO_V20A`;
- `TRADING_MODE=PAPER`;
- sin credenciales Binance para investigación.

## Interpretación

v23a elimina la principal incertidumbre técnica restante de AggTrades: podemos leer el archivo real, distinguir correctamente las unidades temporales históricas, validar orden/IDs y reconstruir el lado agresor de forma consistente tanto en Spot como en USD-M Futures.

También demuestra que una auditoría cuidadosamente muestreada puede revisar más de diez millones de trades transfiriendo solo 0.136 GiB. Esto no significa que una prueba económica completa sea barata: el inventario v23 sigue midiendo 222.518 GiB comprimidos. Por tanto, cualquier prueba de order flow debe predeclarar también su calendario de muestreo y medir el coste de transferencia antes de descargar datos masivos.

**v23a no demuestra ningún edge económico.** Los conteos buy/sell observados no se interpretan como señal porque fueron obtenidos exclusivamente para validar la reconstrucción del lado agresor.

## Prohibiciones mantenidas

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

## Conclusión

v23a pasa su gate de contenido: `DATASET_AGGTRADES_CONTENIDO_APTO_V23A`.

Queda técnicamente habilitado diseñar una hipótesis económica nueva y predeclarada sobre order flow, pero antes de ejecutarla se debe dimensionar con datos S3 el calendario de archivos que requerirá. La siguiente versión no debe elegir fechas por tamaño o resultado económico; el calendario debe fijarse ex ante y mantenerse separado del holdout 2026.
