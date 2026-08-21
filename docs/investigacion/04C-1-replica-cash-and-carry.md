# BOT 2.0 — 04C-1 Réplica cash-and-carry BTC/ETH

## Estado

**PREDECLARADO — especificación congelada antes de descargar precios de entrada/salida o calcular PnL 04C-1.**

04C-0 resultó `DATASET_CARRY_APTO_04C0`: Spot BTC/ETH 48/48 meses, 32 futuros fechados USD-M (16 BTC + 16 ETH), cuatro vencimientos por año/subyacente 2022–2025, continuidad trade-price y mark-price 100%.

04C-1 prueba una sola metodología: **long Spot + short futuro fechado USD-M con el mismo notional**, aproximadamente un mes antes de expiración. No predice dirección del Spot.

## Referencia externa

La referencia principal es Schmeling, Schrimpf y Todorov, *Crypto Carry* (Management Science, online 6-may-2026; BIS Working Paper 1087). El trabajo estudia carry en BTC/ETH y cash-and-carry con futuros de vencimiento fijo. Su análisis de riesgo usa una entrada aproximadamente 19 días hábiles CME / 28 días calendario antes de vencimiento y destaca que la convergencia al settlement no elimina el riesgo de margin call/liquidación previo.

Binance publica:

- contratos USDⓈ-M trimestrales BTC/ETH con settlement en USDT;
- vencimiento/settlement a las 08:00 UTC;
- un endpoint público `GET /futures/data/delivery-price` para settlement histórico;
- Spot/Futures/mark-price históricos en Binance Public Data;
- leverage Futures desde 1x, sujeto al símbolo/cuenta.

## Universo y observaciones

Se usan exactamente los 32 contratos descubiertos en 04C-0:

- BTC: 16 contratos trimestrales 2022–2025;
- ETH: 16 contratos trimestrales 2022–2025;
- cuatro vencimientos por año/subyacente;
- 2026 cerrado.

No se añaden altcoins ni perpetuos en 04C-1.

## Momento de entrada

Para cada contrato con fecha de expiración `E`:

- `T = E - 28 días calendario`;
- hora de entrada: **08:00 UTC**;
- `S0`: open de la vela Spot 1h que comienza en T 08:00 UTC;
- `F0`: open de la vela del futuro fechado 1h que comienza en T 08:00 UTC;
- `M(t)`: mark-price hourly desde T 08:00 UTC hasta antes del settlement.

No se busca la mejor hora del día ni otro número de días.

## Señal económica

Basis de entrada:

`basis_bps = (F0 / S0 - 1) * 10,000`

Solo se abre cash-and-carry si:

`basis_bps > 60 bps`

Los 60 bps son un **hurdle all-in conservador predeclarado**, no un estimado optimizado retrospectivamente. Se usa porque la comisión real histórica de Futures depende de VIP/cuenta/promociones y no puede reconstruirse fielmente sin datos privados. El hurdle debe cubrir conjuntamente trading fees, delivery/settlement, spread, slippage y margen de seguridad.

Referencia de conservadurismo:

- Binance publica actualmente 0.10% por lado para usuario regular Spot antes de descuentos;
- las comisiones Futures dependen de maker/taker y nivel de cuenta;
- mantener una posición hasta delivery puede añadir costo de settlement;
- el backtest no asumirá BNB discount, maker fill garantizado ni VIP.

No se probarán hurdles alternativos dentro de 04C-1.

## Construcción de la posición

Por cada unidad de activo base elegible:

- comprar `1` unidad Spot a `S0`;
- vender `1` unidad del futuro fechado a `F0`;
- reservar collateral Futures igual a `S0` (modelo de investigación equivalente a **1x de notional inicial**, sin borrowing);
- capital comprometido de referencia: `2 * S0` = capital Spot + reserva Futures.

No se reutilizan ganancias Spot como margen intradía. El modelo deliberadamente no supone Portfolio Margin ni cross-collateral entre Spot y Futures.

## Settlement y salida

A la expiración `E`:

- el futuro se liquida usando el `deliveryPrice` oficial de Binance para el par y `deliveryTime` correspondiente;
- la pata Spot se vende al open de la vela Spot 1h que comienza en **E 08:00 UTC**;
- no se cierra manualmente el futuro antes del delivery;
- no se abre una nueva posición durante los diez minutos previos al delivery.

PnL bruto por unidad base:

`spot_pnl = S1 - S0`

`future_pnl = F0 - D`

`gross_pnl = spot_pnl + future_pnl`

`cost_buffer = 0.006 * S0`

`net_pnl = gross_pnl - cost_buffer`

Retorno neto sobre notional Spot:

`net_notional = net_pnl / S0`

Retorno neto sobre capital comprometido:

`net_committed_capital = net_pnl / (2 * S0)`

Para comparabilidad se reportará annualización simple a 28 días:

`annualized_committed = net_committed_capital * 365 / 28`

## Riesgo de margen predeclarado

El futuro short se sigue con `markPriceKlines`.

Adversidad máxima de la pata Futures respecto a la reserva inicial:

`max_margin_drawdown = max(0, max(M(t) - F0) / S0)`

04C-1 no pretende reproducir históricamente las tablas exactas de maintenance margin/VIP/risk tier de cada fecha. En su lugar aplica un buffer operacional deliberadamente severo:

- si `max_margin_drawdown >= 50%` en una operación, esa operación incumple el gate de seguridad;
- no se incrementa leverage para rescatar retorno sobre capital;
- no se supone que la ganancia Spot esté disponible automáticamente para evitar liquidación.

Esto no equivale a calcular el liquidation price exacto de una cuenta Binance histórica; es un stress gate conservador de la réplica.

## Gate de datos

04C-1 es `DATOS_INSUFICIENTES_04C1` si no se puede obtener para los 32 contratos:

- S0 Spot;
- F0 future;
- S1 Spot;
- deliveryPrice oficial;
- mark-price path completo entre entrada y expiración.

No se imputan observaciones ni se sustituyen contratos.

## Gate económico predeclarado

La réplica será `CARRY_APTO_04C1` únicamente si simultáneamente:

1. al menos 8 de los 32 contratos superan ex ante el hurdle de 60 bps;
2. hay operaciones elegibles en al menos 3 de los 4 años;
3. PnL neto agregado de todas las operaciones elegibles > 0;
4. media de `net_notional` > 0;
5. media de `annualized_committed` > 0;
6. al menos 75% de las operaciones elegibles tienen `net_pnl > 0`;
7. cada año que tenga operaciones elegibles presenta PnL neto agregado no negativo;
8. ninguna operación elegible alcanza `max_margin_drawdown >= 50%`.

Se reportan BTC y ETH separados, pero no se permite declarar éxito seleccionando retrospectivamente solo uno de los dos. El gate primario es conjunto.

## Diagnósticos obligatorios, no criterios de rescate

Se reportará:

- basis de entrada por contrato;
- gross y net PnL;
- retorno sobre notional y sobre capital comprometido;
- annualización simple;
- tracking difference al settlement `S1 - D`;
- máxima adversidad mark-to-market Futures;
- número de operaciones por año y subyacente;
- resultados BTC-only y ETH-only solo como diagnóstico;
- contratos que no superan 60 bps se registran como `CASH`.

Ningún diagnóstico permite cambiar el gate después del resultado.

## Candados

- no cambiar 28 días;
- no cambiar 08:00 UTC;
- no cambiar hurdle de 60 bps;
- no cambiar BTC/ETH;
- no eliminar 2022 u otro año;
- no seleccionar solo BTC o solo ETH tras observar resultados;
- no probar reverse carry;
- no probar leverage >1x;
- no asumir cross/portfolio margin;
- no BNB discount;
- no maker fill garantizado;
- no imputación;
- no 2026;
- no mayo-julio 2026;
- sin credenciales reales;
- sin PAPER operativo;
- sin LIVE;
- sin Render;
- sin GPT para decisión de entrada;
- no mergear mientras sea investigación.

## Interpretación

04C-1 no busca una correlación predictiva: pregunta si el basis observable 28 días antes de expiry deja una ganancia delta-neutral económicamente positiva **después de un hurdle conservador y con suficiente headroom de margen**. Si falla, no se rescata bajando costos, aumentando leverage o moviendo la fecha de entrada dentro de esta versión.
