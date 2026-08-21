# BOT 2.0 — 04B-v23 inventario histórico AggTrades

## Estado

**PREDECLARADO — resultado remoto todavía no observado al definir este protocolo.**

v23 no prueba rentabilidad ni formula una dirección económica. Su único objetivo es decidir si el archivo público de `aggTrades` de Binance permite una investigación posterior de order flow con cobertura Spot + USD-M Futures suficiente para el universo fijo de 20 activos.

## Motivo

v22 falsó rebote por caída de precio + contracción de OI + predominio taker vendedor. No corresponde rescatar esa familia modificando umbrales.

La siguiente fuente candidata es order flow de transacciones. Antes de diseñar v24 se exige demostrar que el histórico necesario existe de forma reproducible y conocer su volumen físico.

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

La normalización ms/µs será obligatoria antes de cualquier estudio de contenido. v23, sin embargo, solo inventaría objetos mensuales y tamaños; no descarga el contenido masivo.

## Periodo y universo

- 20 símbolos fijados previamente por 04B-v2;
- 2022-01-01 a 2025-12-31;
- 48 meses esperados;
- dos mercados: Spot y USD-M Futures;
- total nominal: `20 × 48 × 2 = 1.920` ZIP mensuales;
- 2026 cerrado;
- mayo-julio 2026 cerrado.

## Gate predeclarado

Un `symbol-market` es apto si:

- su listado S3 se obtiene completamente;
- tiene al menos 95% de los 48 meses;
- no hay periodos duplicados;
- no hay archivos de tamaño cero.

Un símbolo es pareadamente apto si:

- Spot y USD-M son aptos;
- al menos 95% de los meses existen en ambos mercados.

El dataset solo pasa si:

- al menos 15/20 símbolos son pareadamente aptos;
- al menos 95% de los 48 meses tienen >=15 símbolos con Spot+USD-M;
- cada año tiene al menos 90% de sus meses con >=15 símbolos pareados;
- todos los listados remotos terminan sin error.

El tamaño total del archivo se reporta, pero no se usa como threshold económico: sirve para diseñar el método de adquisición de una eventual v23.1/v24.

## Prohibiciones

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

## Decisión posterior

Si v23 falla, no se formula v24 sobre AggTrades con este universo/periodo.

Si v23 pasa, el siguiente paso será una auditoría de contenido acotada y predeclarada que valide esquema, timestamps ms/µs, orden, duplicados y reconstrucción buy/sell sin descargar el archivo completo de forma indiscriminada. Solo después de ese gate se podrá formular una hipótesis económica de order flow.
