# BOT 2.0 — 04E-2 Resultado auditoría pública ETH staking

## Veredicto

`MARKET_DATA_APTA_REWARDS_NO_PUBLICOS_04E2`

- `market_data_apt=True`
- `reward_series_public=False`
- `economic_backtest_allowed=False`
- `reward_security_type=USER_DATA`
- `pnl_calculated=False`
- `credentials_used=False`
- `development_2026_opened=False`

04E-2 **no falsifica económicamente** ETH staking. Determina que, bajo la política actual de datos públicos/reproducibles, no existe una serie oficial pública suficiente para reconstruir correctamente el reward histórico Binance 2022-2025.

## Cobertura pública observada

### BETHETH

- estado actual reportado por exchangeInfo: `BREAK`
- primera barra: `2022-01-01`
- última barra: `2023-10-11`
- barras totales: `649`
- 2022: `365`
- 2023: `284`
- 2024: `0`
- 2025: `0`
- missing calendar days entre barras existentes: `0`
- max gap: `0`

BETH supera el gate predeclarado de al menos 350 barras en 2022.

### WBETHETH

- estado actual reportado por exchangeInfo: `TRADING`
- primera barra: `2023-05-12`
- última barra: `2025-12-31`
- barras totales: `965`
- 2022: `0`
- 2023: `234`
- 2024: `366`
- 2025: `365`
- missing calendar days entre barras existentes: `0`
- max gap: `0`

La primera barra WBETH aparece antes del límite predeclarado `2023-06-30`.

## Bloqueo de rewards/rate

Las series económicamente necesarias están documentadas por Binance como `USER_DATA`:

- `/sapi/v1/eth-staking/eth/history/rewardsHistory` — distribución de rewards BETH.
- `/sapi/v1/eth-staking/eth/history/rateHistory` — historial oficial de rate WBETH.
- `/sapi/v1/eth-staking/eth/history/wbethRewardsHistory` — rewards WBETH.

Por mecánica:

- BETH era rebasing vía distribución de BETH adicional; el precio BETH/ETH no contiene por sí solo el total return.
- WBETH es reward-bearing; el reward se refleja en su exchange/redemption rate. El precio secundario WBETH/ETH puede contener spread, liquidez y premium/discount, por lo que no sustituye el rate oficial.

No se imputó APR de Ethereum, no se usó precio secundario como reward y no se introdujeron credenciales.

## Transporte y validación

El primer intento llegó a locks y 4/4 tests, pero el runner no resolvía la raíz del repo; se corrigió solo el import path.

El siguiente intento volvió a pasar locks/tests y alcanzó red pública, pero `api.binance.com` devolvió HTTP 451 desde GitHub Actions. Binance documenta `https://data-api.binance.vision` como base oficial para APIs de solo market data; se cambió únicamente ese host, manteniendo endpoints, símbolos, fechas y gates.

Run final `research-04e2` #6:

- methodology locks: success
- tests específicos: 4/4 passed
- market data audit: success
- artifact upload: success

CI general #130: success.

Artifact:

- nombre: `eth-staking-data-audit-04e2`
- ID: `9466673817`
- SHA256 del ZIP: `af18fc4b93ac90c961e93618a0a6b52cfd89c8afcb71e1bc9eedf17e000bf2ea`

## Decisión

No avanzar a backtest económico Binance ETH staking con BETH/WBETH bajo la política actual de datos públicos. Hacerlo requeriría al menos una de estas acciones no permitidas por 04E-2:

1. usar USER_DATA privado como fuente histórica;
2. imputar rewards a partir de APR externo;
3. usar el precio secundario como sustituto de una distribución/rate distinto;
4. excluir el régimen BETH de 2022 y cambiar el periodo después de observar la limitación.

La dirección de staking ETH queda **bloqueada por reproducibilidad de datos, no falsada por retorno**. La siguiente hipótesis debe preferir una fuente de yield/settlement con historial público verificable y mecánica auditable antes de PnL.

Cierre metodológico: sin merge a `main`, sin PAPER operativo, sin LIVE, sin Render, sin credenciales y con 2026 cerrado.
