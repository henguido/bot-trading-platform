# BOT 2.0 — 04C-1 Réplica cash-and-carry BTC/ETH

## Estado final

**`CARRY_FALSADO_04C1` — datos completos y PnL agregado positivo, pero la réplica no supera los gates predeclarados de estabilidad.**

04C-0 había resultado `DATASET_CARRY_APTO_04C0`. 04C-1 mantuvo exactamente la especificación congelada antes del PnL: 32 contratos BTC/ETH, entrada 28 días antes a 08:00 UTC, long Spot + short futuro fechado con igual notional, hurdle all-in fijo de 60 bps, reserva Futures de 1x notional y stress de margen de 50%.

## Resultado reproducible

Workflow válido: `research-04c1` run #3 sobre HEAD ejecutable `5aaa1434c9f1977b354e71a5551fa9343876510d`.

- 32/32 contratos con datos completos;
- 9/32 contratos superaron `basis > 60 bps`;
- años con operaciones: 2023, 2024 y 2025;
- PnL neto agregado: **positivo**, `1048.83306` unidades de PnL por las unidades base usadas en la réplica;
- media `net_notional`: **+0.173741%** por operación elegible;
- media anualizada simple sobre capital comprometido: **+1.132421%**;
- 6/9 operaciones net-positive = **66.667%**;
- operaciones con stress de margen >=50%: **0**;
- BTC diagnóstico neto: `+1029.58362`;
- ETH diagnóstico neto: `+19.24944`.

Resultado por año:

- 2022: 0 operaciones, PnL 0;
- 2023: 2 operaciones, PnL neto **-41.97092**;
- 2024: 6 operaciones, PnL neto **+1171.15158**;
- 2025: 1 operación, PnL neto **-80.34760**.

Motivos de rechazo exactos:

- `FRACCION_OPERACIONES_POSITIVAS_INSUFICIENTE`;
- `ANIO_CON_OPERACIONES_PNL_NEGATIVO`.

El gate exigía >=75% de operaciones ganadoras y ningún año activo con PnL agregado negativo. No se modifican retrospectivamente.

## Operaciones elegibles

BTC:

- `BTCUSDT_231229`: basis 81.6911 bps, net_notional -0.0829%, annualized committed -0.5402%, margin drawdown 16.8829%;
- `BTCUSDT_240329`: basis 171.3872 bps, net_notional +0.5320%, annualized committed +3.4673%, margin drawdown 20.4020%;
- `BTCUSDT_240628`: basis 84.8845 bps, net_notional +0.0593%, annualized committed +0.3868%, margin drawdown 5.6217%;
- `BTCUSDT_241227`: basis 147.6653 bps, net_notional +0.8098%, annualized committed +5.2781%, margin drawdown 12.3503%;
- `BTCUSDT_250328`: basis 61.1959 bps, net_notional -0.1014%, annualized committed -0.6612%, margin drawdown 19.7245%.

ETH:

- `ETHUSDT_231229`: basis 80.7554 bps, net_notional -0.4911%, annualized committed -3.2006%, margin drawdown 16.2305%;
- `ETHUSDT_240329`: basis 172.5793 bps, net_notional +0.1440%, annualized committed +0.9388%, margin drawdown 22.2384%;
- `ETHUSDT_240628`: basis 93.8025 bps, net_notional +0.0449%, annualized committed +0.2928%, margin drawdown 4.2242%;
- `ETHUSDT_241227`: basis 160.4740 bps, net_notional +0.6490%, annualized committed +4.2299%, margin drawdown 15.3421%.

## Qué aprendimos

La falsación **no** significa que el crypto carry no exista. La réplica mostró:

1. basis ex ante suficientemente amplio en nueve vencimientos;
2. PnL agregado positivo después del buffer conservador;
3. media de retorno positiva;
4. cero incumplimientos del stress de margen a 1x;
5. pero insuficiente consistencia temporal.

Las pérdidas de 2023 y 2025 no se explican por liquidación. El diagnóstico muestra una fricción de realización: el `deliveryPrice` del futuro y el Spot ejecutable exactamente a las 08:00 UTC no coinciden. En el modelo textbook, el payoff depende de convergencia `F_T = S_T`; en una implementación cash-settled el índice de settlement y el precio ejecutable Spot pueden presentar tracking difference alrededor del fix. Esa diferencia puede consumir un basis pequeño incluso cuando el basis inicial supera el buffer de costos.

Este diagnóstico **no permite rescatar 04C-1** cambiando la hora, el hurdle o escogiendo solo BTC. La versión queda falsada tal como fue predeclarada.

## Referencia externa

Schmeling, Schrimpf y Todorov, *Crypto Carry* (Management Science, online 6-may-2026; BIS Working Paper 1087) estudian BTC/ETH fixed-maturity carry. Su configuración textbook es long Spot / short Futures cuando carry positivo y suficientemente grande para cubrir costos. También muestran que las dos patas deben financiarse separadamente y que la pata short Futures puede sufrir drawdowns severos antes de convergencia.

El paper construye series de basis de madurez constante de uno y tres meses; su análisis de riesgo toma posiciones aproximadamente 28 días antes de expiración. La siguiente investigación, si se realiza, debe aproximar mejor una **posición de carry continua/rolada** en lugar de forzar venta y recompra de Spot en cada settlement.

## Costos y ejecución usados

- hurdle all-in fijo: 60 bps sobre notional Spot;
- sin BNB discount;
- sin maker fill garantizado;
- sin VIP favorable;
- collateral Futures de referencia igual al notional Spot;
- capital comprometido de referencia `2*S0`;
- sin Portfolio Margin/cross-collateral;
- settlement oficial Binance congelado antes del PnL para evitar HTTP 451 de GitHub-hosted Actions;
- markPrice hourly para stress de margen.

El primer intento real del workflow no produjo resultado económico porque `fapi.binance.com` devolvió HTTP 451 desde GitHub Actions. Los 32 `deliveryPrice` oficiales se capturaron antes del PnL y se congelaron en `backend/economia/data/carry_04c1_delivery_prices.json`; el run #3 es el resultado válido.

## Validación de ingeniería

- locks 04C-1: OK;
- 6 tests dedicados: passed;
- CI general: **1147 tests passed**, 1391 warnings;
- `compileall backend`: OK;
- frontend build: 841 módulos;
- v20.1: `DATASET_POSICIONAMIENTO_APTO_V20A`.

## Candados preservados

- no cambiar 28 días;
- no cambiar 08:00 UTC;
- no bajar hurdle de 60 bps;
- no cambiar BTC/ETH;
- no eliminar años;
- no seleccionar BTC-only tras observar resultado;
- no reverse carry;
- no leverage >1x;
- no cross/portfolio margin;
- no imputación;
- no 2026;
- no mayo-julio 2026;
- sin credenciales reales;
- sin PAPER operativo;
- sin LIVE;
- sin Render;
- sin GPT para decidir entradas;
- no mergear esta rama.

## Decisión

**04C-1 queda cerrada como falsada por estabilidad, no por ausencia de carry.**

La siguiente fase no debe ajustar 04C-1. Una posible 04C-2 deberá ser una metodología distinta y predeclarada, apoyada por la literatura: mantener la pata Spot y **rolar** futuros de vencimiento fijo/constant-maturity para reducir churn de Spot y separar el carry estructural del tracking puntual del settlement. Debe definir de antemano la regla de roll, costos por roll, capital y stress de margen antes de leer nuevos PnL.