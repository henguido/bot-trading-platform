# BOT 2.0 — 04E-2 Auditoría pública de datos y mecánica ETH staking

## Estado

**AUDITORÍA DE DATOS/MECÁNICA. NO ES BACKTEST Y NO OBSERVA PnL.**

04E-2 se abre después de falsar 04E-1. Su objetivo es decidir si existe una fuente histórica, pública, reproducible y económicamente correcta para modelar rewards de staking ETH en 2022-2025 sin credenciales privadas ni imputación.

## Pregunta exacta

¿Podemos construir, con datos públicos oficiales, una serie histórica de staking yield de Binance que cubra 2022-2025 y que pueda combinarse posteriormente con una cobertura ETH sin inventar rewards?

La auditoría separa dos cuestiones:

1. **Market data:** comprobar que BETH/ETH y WBETH/ETH cotizaron y tienen barras históricas suficientes.
2. **Reward accounting:** comprobar si el reward/rate económicamente necesario es público y reproducible.

Que (1) sea apto no implica que (2) lo sea.

## Mecánica documentada

### BETH

BETH representa ETH staked en Binance. En el régimen BETH, los rewards se distribuían como **BETH adicional** al holder. Por tanto, observar únicamente el precio BETH/ETH no captura el rendimiento total: la cantidad de BETH cambia.

### WBETH

WBETH fue lanzado el 27 de abril de 2023. Su mecánica es distinta: el staking reward se acumula en el **exchange/redemption rate** de WBETH contra ETH, de modo que una unidad de WBETH representa progresivamente más ETH.

Shanghai/Capella se activó el 12 de abril de 2023 y habilitó retiros de ETH staked; es contexto de transición de producto, no un input de PnL en 04E-2.

## Endpoints oficiales económicamente necesarios

La API oficial de Binance documenta:

- `GET /sapi/v1/eth-staking/eth/history/rewardsHistory`: historial de distribución BETH.
- `GET /sapi/v1/eth-staking/eth/history/rateHistory`: historial de rate WBETH.
- `GET /sapi/v1/eth-staking/eth/history/wbethRewardsHistory`: historial de rewards WBETH.

Los tres son **USER_DATA**. 04E-2 no usará API key/secret ni convertirá datos privados de una cuenta en un dataset histórico de investigación.

## Evidencia pública permitida

Solo endpoints públicos de market data:

- `/api/v3/exchangeInfo?symbol=BETHETH`
- `/api/v3/exchangeInfo?symbol=WBETHETH`
- `/api/v3/klines?symbol=...&interval=1d`

Periodo fijo: `2022-01-01 <= t < 2026-01-01`.

## Gates predeclarados

Market data es apto si:

1. BETHETH tiene al menos 350 barras diarias en 2022.
2. WBETHETH presenta su primera barra no más tarde del 30 de junio de 2023.
3. Las barras son parseables, ordenadas, únicas y con OHLC positivo/coherente.

El reward dataset solo sería apto para backtest económico si la serie requerida fuese pública. Según la clasificación oficial actual, ese gate no se cumple: los endpoints de rewards/rate son USER_DATA.

Estados posibles:

- `MARKET_DATA_APTA_REWARDS_NO_PUBLICOS_04E2`
- `MARKET_DATA_INCOMPLETA_04E2`

En ambos casos `economic_backtest_allowed=False` mientras no exista una fuente pública oficial de rewards/rate que cumpla el periodo y la mecánica.

## Prohibiciones metodológicas

- No PnL ni retornos en 04E-2.
- No credenciales Binance.
- No PAPER operativo, LIVE ni Render.
- 2026 permanece cerrado.
- No imputar staking APR desde Ethereum consensus/network statistics.
- No usar BETH/ETH como sustituto de la distribución BETH.
- No usar WBETH/ETH como sustituto del exchange/redemption rate oficial.
- No inferir reward a partir de apreciación del precio secundario.

La razón del último punto es económica: el precio secundario contiene liquidez, spread, descuento/premium y microestructura. El reward oficial es un flujo/cambio de rate distinto.

## Interpretación predeclarada

Si el market data es apto pero las series de reward/rate siguen siendo USER_DATA, el resultado **no falsifica económicamente ETH staking**. Falsifica únicamente la posibilidad de ejecutar un backtest 2022-2025 reproducible bajo la política actual de datos públicos.

En ese caso se cerrará 04E-2 sin PnL y la siguiente hipótesis deberá usar una fuente de yield/settlement con historial público verificable, en vez de relajar la política de datos o inventar rewards.
