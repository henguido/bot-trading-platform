# BOT 2.0 — Resultado 04C-3 Calendar Spread

## Veredicto

**CALENDAR_ECONOMICAMENTE_FALSADO_04C3**

**CALENDAR_NO_CANDIDATO_PRODUCCION_04C3**

04C-3 evaluó la estructura predeclarada long USD-M perpetual + short USD-M quarterly, BTC/ETH, 28 días antes de cada vencimiento trimestral 2022-2025, usando una única regla ex-ante de entrada y 60 bps de coste por trade.

## Integridad de datos

- oportunidades esperadas: 32;
- inputs válidos: **32/32**;
- errores de descarga/parse: **0**;
- cobertura horaria de stress: **100% en las 32 oportunidades**;
- 2026 cerrado;
- sin credenciales, sin imputación y sin órdenes.

La corrección factual de calendario de tercer viernes a último viernes quedó registrada **antes de que el runner histórico llegara a ejecutarse**. Ningún parámetro económico se modificó después de observar PnL.

## Resultado del selector congelado

Regla:

`predicted_net = entry_spread - trailing_28d_funding_cost - 0.006`

Elegible únicamente si `predicted_net > 0`.

Resultado:

**0/32 oportunidades elegibles.**

Por tanto la estrategia permaneció en cash en las 32 oportunidades y los retornos del portafolio fueron 0% en 2022, 2023, 2024 y 2025.

## Diagnóstico estructural

En todas las oportunidades, la combinación de spread trimestral observable, coste esperado de funding de la pata long perpetual y hurdle operativo de 60 bps dejó `predicted_net <= 0`.

El caso más cercano fue BTCUSDT_240329:

- spread de entrada: **1.6280%**;
- trailing funding 28d: **1.1450%**;
- carry pre-cost aproximado: **+0.4830%**;
- predicted net después de 60 bps: **-0.1170%**;
- realized gross posterior: **-1.8978%**;
- peor stress intratrade: **-2.5330%**.

ETHUSDT_240329 fue similar:

- spread: **1.6557%**;
- trailing funding: **1.1833%**;
- predicted net: **-0.1276%**;
- realized gross: **-2.3375%**;
- stress: **-2.4894%**.

El hecho de que las oportunidades más cercanas al hurdle terminaran además con realized gross negativo refuerza que bajar retrospectivamente el coste o seleccionar episodios de 2024 no sería una justificación válida para producción.

## Agregados

- eligible trades: **0/32**;
- win rate: **0%**;
- media anual: **0%**;
- peor año: **0%**;
- Sharpe trimestral: **0**;
- max drawdown del portafolio ejecutado: **0%**, porque no hubo trades.

## Gate económico

No superado por:

- `TRADES_ELEGIBLES_INSUFICIENTES`;
- `NO_4_DE_4_ANIOS_POSITIVOS`;
- `MEDIA_ANUAL_NO_POSITIVA`;
- `SHARPE_ECONOMICO_INSUFICIENTE`.

## Gate de producción

No superado por:

- `GATE_ECONOMICO_NO_SUPERADO`;
- `MEDIA_ANUAL_MENOR_5PCT`;
- `PEOR_ANIO_MENOR_2PCT`;
- `SHARPE_PRODUCCION_MENOR_1_5`;
- `WIN_RATE_MENOR_60PCT`;
- `TRADES_PRODUCCION_INSUFICIENTES`.

## Decisión metodológica

Esta variante queda **cerrada bajo los parámetros congelados**.

No se permite ahora:

- bajar los 60 bps porque ninguna operación entró;
- seleccionar solo 2024/2025;
- probar varios lookbacks y publicar el mejor;
- invertir el signo;
- añadir leverage;
- quitar funding del predictor;
- usar realized gross futuro para decidir qué trades habrían sido elegibles.

Esas acciones convertirían 04C-3 en optimización retrospectiva.

## Implicación para producción

04C-3 no mejora el camino de 04C-2. El hallazgo productivo relevante sigue siendo 04C-2: existe una prima económica estable en long Spot + short perpetual BTC/ETH, pero aún debe someterse a ingeniería operativa real antes de considerar producción.

El siguiente paso recomendado es **04D-1: Production Feasibility Audit de 04C-2**, en un módulo de investigación/read-only, para sustituir supuestos conservadores por mediciones públicas de fees, order-book slippage, margin mechanics, maintenance margin, liquidation buffer y capital efectivo. Esto no reescribe el fallo del gate 04C-2 y no autoriza LIVE.

## Estado de seguridad

- `main` intacto;
- cerrar este PR sin merge;
- no PAPER operativo;
- no LIVE;
- no Render;
- holdout 2026 cerrado.
