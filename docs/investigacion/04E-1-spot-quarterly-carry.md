# BOT 2.0 — 04E-1: Spot + short USD-M quarterly

## Estado

**PREDECLARADO ANTES DE PnL 04E-1.**

04E-1 es una hipótesis nueva. No rescata 04C-2 ni cambia sus gates. Tampoco reutiliza la estructura long perpetual + short quarterly falsada en 04C-3.

## Racional económico

04C-3 mostró que el spread quarterly-perpetual no cubría el funding de la pata long perpetual + 60 bps. 04E-1 sustituye esa pata long por Spot cash:

- long BTCUSDT/ETHUSDT Spot;
- short el USD-M quarterly del mismo activo;
- hold fijo 28 días hasta delivery;
- no funding en ninguna de las dos patas;
- al delivery el futuro lineal converge al precio de settlement, por lo que la prima trimestral de entrada es la fuente económica primaria.

La documentación vigente de Binance mantiene `CURRENT_QUARTER` y `NEXT_QUARTER` como tipos de contrato USD-M. 04E-1 usa exclusivamente contratos históricos de 2022-2025 ya fijados por calendario; 2026 permanece cerrado.

## Calendario congelado

BTCUSDT y ETHUSDT. Cuatro expiries por año: último viernes de marzo, junio, septiembre y diciembre a las 08:00 UTC. Entrada exactamente 28 días antes.

Años: 2022, 2023, 2024 y 2025.

Total: 16 expiries x 2 activos = 32 oportunidades.

No se probarán otros horizontes después de observar resultados.

## Regla de entrada

En la entrada:

`entry_basis = quarter_entry / spot_entry - 1`

Coste predeclarado por round-trip completo de ambas patas:

`drag = 0.006` = **60 bps por trade**.

`predicted_net = entry_basis - 0.006`

Solo hay trade si:

`predicted_net > 0`

Si no, la asignación queda en cash con retorno 0. No se invierte el signo ni se reduce el coste retrospectivamente.

## PnL realizado

Normalizando a una unidad del activo:

- capital Spot inicial = `spot_entry`;
- Spot PnL = `spot_exit - spot_entry`;
- short quarterly PnL = `quarter_entry - delivery_price`;
- gross return = suma de ambas patas / `spot_entry`;
- net return = gross return - 60 bps si fue elegible.

El precio de delivery procede del fixture público ya capturado antes del PnL de 04C-1/04C-3. El Spot entry/exit y las trayectorias horarias se descargan de Binance Vision; los contratos quarterly usan Binance Vision USD-M.

## Stress intratrade

Cada hora común entre Spot y quarterly:

`MTM = (spot_t - spot_0 + future_0 - future_t) / spot_0`

Cobertura mínima: 95% de las 672 horas esperadas. Sin imputación.

## Gates económicos

- datos aptos;
- >=8 trades elegibles;
- 4/4 años del portafolio >0;
- media anual >0;
- Sharpe trimestral >=1.0;
- max drawdown <=15%;
- peor stress intratrade <=15%.

## Gates de screening productivo

Capital 1x se usa **solo como cota optimista de screening**; no afirma que la cuenta pueda ejecutar el hedge con 1x real.

- media anual >=5%;
- peor año >=2%;
- Sharpe trimestral >=1.5;
- max drawdown <=7.5%;
- peor stress <=7.5%;
- win rate >=60%;
- >=8 trades;
- gate económico completo.

Si pasa, el veredicto significa **candidato para audit de margen**, no autorización de PAPER/LIVE.

## Candados

- 2026 cerrado;
- sin leverage adicional;
- sin imputación;
- sin optimizar horizonte;
- sin cambiar coste;
- sin inversión retrospectiva del signo;
- sin credenciales;
- sin órdenes;
- sin Render;
- sin PAPER operativo;
- sin LIVE.
