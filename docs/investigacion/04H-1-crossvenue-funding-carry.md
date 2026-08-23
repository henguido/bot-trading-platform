# BOT 2.0 — 04H-1 Cross-Venue Funding Carry

## Estado

**PREDECLARADO / PRE-PNL.**

04H-1 parte exclusivamente de `DATASET_CROSSVENUE_FUNDING_APTO_04H0`. No modifica Scanner, RiskEngine, PAPER, LIVE, Render ni credenciales. 2026 permanece cerrado.

Antes de habilitar PnL existe un gate adicional de reconstrucción económica: Hyperliquid publica `oraclePx` y `markPx` históricos en `s3://hyperliquid-archive/asset_ctxs`, un bucket requester-pays. La API gratuita `fundingHistory` no sustituye ese histórico de precios. 04H-1 **prohíbe usar candles como proxy de oracle/mark** para rescatar la prueba.

Mientras no se valide esa fuente exacta para 2024-2025, `CALCULAR_PNL_2024_2025_PERMITIDO_04H1 = False`.

## Hipótesis única

Una cartera equal-weight BTC/ETH/SOL, **long Binance USD-M perpetual y short Hyperliquid perpetual** en igual exposición base, obtiene un carry cross-venue neto positivo y económicamente suficiente durante 2024-2025 después de incorporar funding realizado, cambio de basis cross-venue y costes conservadores.

La orientación queda fijada antes del PnL por la evidencia externa revisada. Si la hipótesis falla, no se invierte el signo, no se seleccionan activos por resultado y no se optimizan costes o leverage después de observar el resultado.

## Universo y fechas

Activos fijos:

- BTC
- ETH
- SOL

Portfolio primario: equal-weight. Los resultados individuales se reportan como diagnóstico, pero ningún activo individual puede rescatar un fallo del portafolio conjunto.

Ventana económica:

- 2024-01-01 a 2024-12-31;
- 2025-01-01 a 2025-12-31;
- cada año se evalúa como sleeve independiente;
- 2026 cerrado.

## Posición

Por cada activo:

- long Binance USD-M perpetual;
- short Hyperliquid perpetual;
- igual exposición base en ambas patas;
- leverage de referencia fijo: **2x por pata**;
- sin market timing;
- sin selección por signo observado de funding;
- sin ML;
- sin GPT.

## Gate previo de reconstrucción económica

Para habilitar el runner de PnL deben existir observaciones oficiales suficientes para BTC/ETH/SOL durante 2024-2025:

1. funding realizado Hyperliquid mediante `fundingHistory`;
2. `oraclePx` histórico Hyperliquid desde `asset_ctxs`;
3. `markPx` histórico Hyperliquid desde `asset_ctxs`;
4. funding realizado Binance desde Binance Vision;
5. mark/perpetual prices Binance desde Binance Vision;
6. timestamps alineables sin imputación;
7. cero duplicados conflictivos y valores no finitos.

No se autoriza sustituir `oraclePx` o `markPx` por OHLC candles. Si el gate no puede demostrarse, el resultado permitido es únicamente `DATOS_ECONOMICOS_INSUFICIENTES_04H1` y no se calcula PnL.

La descarga requester-pays de Hyperliquid no se ejecuta automáticamente ni sin autorización explícita del usuario.

## Funding

No se inventa una cadencia común.

- Hyperliquid se procesa en sus timestamps reales de funding horario;
- Binance se procesa en sus settlements reales publicados;
- no se divide funding Binance artificialmente para crear observaciones horarias;
- cada cash-flow usa el precio histórico oficial requerido por el venue/protocolo;
- timestamps duplicados, tasas no finitas o desalineaciones no explicables fallan cerrado.

Convención de signos del portafolio:

- funding recibido por la pata short Hyperliquid suma;
- funding pagado/recibido por la pata long Binance se incorpora con su signo económico real;
- no se invierte ninguna serie después de ver resultados.

## Basis cross-venue

El PnL no puede reducirse a `funding_HL - funding_Binance`.

Para igual exposición base debe incluirse el cambio de precio relativo entre ambos perpetuals. El resultado económico debe descomponerse como mínimo en:

1. funding Hyperliquid;
2. funding Binance;
3. cambio de basis Binance-Hyperliquid;
4. costes;
5. neto total.

No se asume que delta-neutral implica basis-neutral.

## Capital de referencia

Leverage fijo: 2x por pata.

Para notional `N` por activo:

- margen de referencia Binance = `N / 2`;
- margen de referencia Hyperliquid = `N / 2`;
- capital comprometido inicial de referencia = `N`.

Este cálculo es un filtro económico, no una réplica completa de motores de margen o liquidación. Top-ups, maintenance margin y liquidación exacta pertenecen a una fase posterior si 04H-1 supera los gates.

## Costes congelados

No se reconstruyen retrospectivamente tiers VIP, descuentos BNB, staking, referrals ni maker fills favorables.

- caso primario: **60 bps all-in por año** sobre notional de referencia;
- stress: **120 bps all-in por año**.

Los costes representan entrada, salida, fees, spread, slippage y fricción operativa. No se modifican después de observar el PnL de 04H-1.

## Métricas obligatorias

Por activo, año y portfolio BTC/ETH/SOL:

- funding Hyperliquid;
- funding Binance;
- basis PnL;
- gross PnL;
- net return primario;
- net return stress;
- retorno neto sobre capital de referencia;
- Sharpe neto;
- max drawdown;
- peor día;
- fracción de días positivos;
- turnover/rebalances si los hubiera por mecánica de igualación;
- t-stat HAC/Newey-West del spread/carry agregado bajo una definición fijada en código antes del resultado.

## Gate económico

La hipótesis es económicamente apta únicamente si simultáneamente:

1. 2024 neto primario > 0;
2. 2025 neto primario > 0;
3. media anual neta > 0;
4. funding spread/carry agregado > 0;
5. Sharpe neto >= **1.0**;
6. max drawdown <= **10%**;
7. resultado agregado sigue > 0 con **120 bps** de stress;
8. `abs(t-stat HAC) >= 1.96` para la métrica predeclarada de carry/spread.

## Gate candidato a ingeniería productiva

Solo si el gate económico pasa. Además deben cumplirse todos:

1. media anual neta sobre capital de referencia >= **5%**;
2. peor año neto sobre capital de referencia >= **2%**;
3. Sharpe neto >= **2.0**;
4. max drawdown <= **7.5%**;
5. 2/2 años positivos;
6. portfolio conjunto positivo sin depender de un único activo;
7. stress de 120 bps positivo.

Estos umbrales conservan la vara ya utilizada en 04C-2; no se relajan para 04H-1.

## Limitación de liquidación

Incluso con oracle/mark históricos, 04H-1 es una prueba económica, no una réplica exacta de los motores de margen. Si supera el gate candidato, 04H-2 debe reconstruir maintenance margin, top-ups, liquidation buffer, partial fills, ejecución simultánea, outages, profundidad/slippage a tamaño objetivo y riesgo de exchange/custodia.

## Candados

- no cambiar BTC/ETH/SOL;
- no seleccionar activos por performance;
- no invertir long/short tras ver el resultado;
- no cambiar 60/120 bps;
- no optimizar leverage después del resultado;
- no seleccionar periodos por funding observado;
- no usar candles como oracle/mark histórico;
- no imputar;
- no añadir ML;
- no GPT;
- no credenciales;
- no PAPER operativo;
- no LIVE;
- no Render;
- no 2026.

## Camino posterior

- validar primero `asset_ctxs` 2024-2025;
- si falla el gate de datos: detener sin PnL;
- si pasa: habilitar el runner económico sin cambiar hipótesis ni gates;
- si falla económicamente: cerrar 04H-1 sin rescate post-hoc;
- si es positiva pero no supera gate productivo: documentar prima insuficiente;
- si supera gate candidato: diseñar 04H-2 de viabilidad operativa;
- abrir 2026 solo después de congelar completamente 04H-2;
- PAPER operativo permanece bloqueado hasta después del holdout final.
