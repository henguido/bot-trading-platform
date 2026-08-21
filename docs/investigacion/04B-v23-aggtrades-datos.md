# BOT 2.0 — 04B-v23 inventario histórico AggTrades

## Estado

**Resultado final: `DATASET_AGGTRADES_INVENTARIO_APTO_V23`.**

v23 no prueba rentabilidad ni formula una dirección económica. Su único objetivo fue decidir si el archivo público de `aggTrades` de Binance permite una investigación posterior de order flow con cobertura Spot + USD-M Futures suficiente para el universo fijo de 20 activos.

## Motivo

v22 falsó rebote por caída de precio + contracción de OI + predominio taker vendedor. No corresponde rescatar esa familia modificando umbrales.

La siguiente fuente candidata es order flow de transacciones. Antes de diseñar una hipótesis económica se exigió demostrar que el histórico necesario existe de forma reproducible y conocer su volumen físico.

## Fuente oficial y contrato

Fuente de inventario:

- `data.binance.vision`
- Spot: `data/spot/monthly/aggTrades/{SYMBOL}/`
- USD-M Futures: `data/futures/um/monthly/aggTrades/{SYMBOL}/`

La documentación oficial de Binance Public Data indica que:

- los archivos `aggTrades` reproducen `/api/v3/aggTrades` para Spot;
- los archivos `aggTrades` USD-M reproducen `/fapi/v1/aggTrades`;
- ambos incluyen precio, cantidad, timestamp e indicador `isBuyerMaker`;
- los timestamps Spot desde 2025-01-01 están expresados en microsegundos.

La normalización ms/µs será obligatoria antes de cualquier estudio de contenido. v23 solo inventarió objetos mensuales y tamaños; no descargó el contenido masivo.

## Periodo y universo

- 20 símbolos fijados previamente por 04B-v2;
- 2022-01-01 a 2025-12-31;
- 48 meses esperados;
- dos mercados: Spot y USD-M Futures;
- total nominal: `20 × 48 × 2 = 1.920` ZIP mensuales;
- 2026 cerrado;
- mayo-julio 2026 cerrado.

## Gate predeclarado

Un `symbol-market` era apto si:

- su listado S3 se obtenía completamente;
- tenía al menos 95% de los 48 meses;
- no había periodos duplicados;
- no había archivos de tamaño cero.

Un símbolo era pareadamente apto si:

- Spot y USD-M eran aptos;
- al menos 95% de los meses existían en ambos mercados.

El dataset solo pasaba si:

- al menos 15/20 símbolos eran pareadamente aptos;
- al menos 95% de los 48 meses tenían >=15 símbolos con Spot+USD-M;
- cada año tenía al menos 90% de sus meses con >=15 símbolos pareados;
- todos los listados remotos terminaban sin error.

## Resultado remoto

Workflow aislado `research-04b` #72, job `aggtrades-v23`: **success**.

Resultado:

- listados completos: **40/40**;
- ZIP mensuales encontrados: **1.920/1.920**;
- símbolos pareadamente aptos: **20/20**;
- cobertura cross-sectional pareada global: **100%**;
- 2022: **12/12** meses con >=15 símbolos pareados;
- 2023: **12/12**;
- 2024: **12/12**;
- 2025: **12/12**;
- motivos de rechazo: **ninguno**.

Tamaño físico comprimido inventariado:

- Spot: **97.550 GiB**;
- USD-M Futures: **124.969 GiB**;
- total: **222.518 GiB**.

Artifact:

- `aggtrades-data-audit-v23-2022-2025`;
- id `9450777117`;
- digest `sha256:5a0f2d9688523a365bba62474261f562c3b840ab10567417836c8324079c8ae5`.

## Validación técnica

PR temporal: **#24 — WIP: auditar BOT 2.0-04B v23 AggTrades históricos**.

HEAD de implementación evaluada: `8f7c5dc8ff116402aa993f85381ce55cbbc141af`.

CI general #84: **success**.

- **1119 tests passed**;
- 1391 warnings;
- `compileall backend` OK;
- frontend build OK, **841 módulos** transformados;
- v20.1 volvió a resultar `DATASET_POSICIONAMIENTO_APTO_V20A`;
- `TRADING_MODE=PAPER`;
- sin credenciales Binance para investigación.

## Interpretación

El archivo histórico de AggTrades es excepcionalmente completo para el universo y periodo estudiados. El problema ya no es disponibilidad.

El hallazgo operativo importante es el volumen: **222.518 GiB comprimidos**. Descargar todo el archivo en CI o para una primera exploración sería innecesario y costoso. La siguiente etapa debe validar contenido mediante una muestra determinística y acotada, suficiente para cubrir:

- Spot y USD-M Futures;
- años anteriores y posteriores al cambio de unidad temporal de Spot en 2025;
- esquema real del CSV;
- timestamps y pertenencia al día nominal;
- IDs/orden/duplicados;
- precio y cantidad válidos;
- semántica de `isBuyerMaker` para reconstruir flujo agresor comprador/vendedor.

Esta conclusión es exclusivamente de ingeniería de datos. **No existe todavía evidencia de edge económico de order flow.**

## Prohibiciones mantenidas

- no retornos;
- no labels;
- no correlaciones;
- no ranking de activos;
- no señal long/short;
- no tuning;
- no imputación;
- no GPT;
- no scanner;
- no RiskEngine;
- no PAPER operativo;
- no LIVE;
- no Render;
- no abrir 2026.

## Conclusión

v23 pasa su gate de inventario: `DATASET_AGGTRADES_INVENTARIO_APTO_V23`.

Queda autorizada únicamente una auditoría de contenido acotada y predeclarada. No queda autorizada todavía una hipótesis económica, integración operativa ni apertura del holdout 2026.
