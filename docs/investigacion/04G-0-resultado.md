# BOT 2.0 — 04G-0 Resultado factibilidad multi-quote order flow

## Veredicto

`DATASET_MULTIQUOTE_ORDERFLOW_APTO_04G0`

El archivo público de Binance Vision sí permite construir un proxy **multi-quote** sustancialmente más cercano a la dimensión de world order flow de la literatura que el USDT-only probado en v24.

Este resultado es exclusivamente de **cobertura de datos**. No se descargó contenido de klines, no se calculó order flow, no se entrenó ML y no se observó PnL.

## Resultado real

Workflow `research-04g0` #1, run `32553425786`, HEAD `f0b2d240cfed2766e767856378836a9c15a56735`:

- bases fijas: 20;
- quotes predeclarados: 14;
- pair prefixes auditados: **280/280**;
- pair prefixes con datos 2022-2025: **190**;
- meses objetivo: **48**;
- meses que pasan el gate multi-quote: **48/48**;
- activos multi-quote por mes, mínimo: **19/20**;
- activos multi-quote por mes, máximo: **20/20**;
- razones de rechazo: ninguna.

Gate congelado antes de observar cobertura:

- al menos 2 quote pairs por base/mes;
- al menos 15 de los 20 activos multi-quote en cada uno de los 48 meses.

La cobertura real supera el gate con holgura.

## Cobertura temporal de quotes

Meses 2022-2025 en los que cada quote aparece para al menos una base:

- USDT: 48;
- BUSD: 24;
- USDC: 43;
- TUSD: 43;
- FDUSD: 30;
- EUR: 48;
- GBP: 24;
- AUD: 18;
- BRL: 48;
- TRY: 48;
- RUB: 25;
- UAH: 48;
- BIDR: 29;
- IDRT: 5.

No se exige que las 14 monedas estén disponibles simultáneamente: el gate exige diversidad multi-quote ex-ante por activo/mes y prohíbe imputar quotes faltantes.

## Evidencia técnica

- methodology locks: success;
- tests específicos: 4/4 passed;
- auditoría S3: success;
- CI general #144: success;
- artifact: `world-orderflow-data-audit-04g0`;
- artifact ID: `9470712437`;
- SHA256: `8d7a05dc28624b42a92edcdb35d077b9193b091c04040b15df6f11769943f1c8`.

## Relación con v24

04G no reabre ni retunea v24. v24 probó una hipótesis distinta:

- Spot-USDT únicamente;
- OFI agregado de un lunes;
- residualización OLS cross-sectional contra retorno contemporáneo;
- top 25%;
- horizonte 7 días;
- sin modelo no lineal.

04G-0 demuestra que existe cobertura para investigar una construcción multi-quote antes de considerar los modelos no lineales que la literatura identifica como económicamente útiles.

## Candados preservados

No se realizó:

- descarga de contenido ZIP/CSV;
- cálculo de buyer/seller order flow;
- conversión o normalización entre monedas;
- ML;
- retorno futuro;
- PnL;
- credenciales;
- imputación;
- PAPER operativo;
- LIVE;
- Render;
- apertura de 2026.

## Decisión

04G puede avanzar a **04G-1: auditoría de contenido y semántica multi-quote**.

Antes de cualquier modelo económico, 04G-1 debe demostrar que `quote_volume` y `taker_buy_quote_volume` permiten reconstruir de forma consistente buyer-initiated y seller-initiated volume y debe congelar una normalización entre quotes que no use información futura.
