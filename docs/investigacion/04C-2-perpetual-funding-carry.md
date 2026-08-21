# BOT 2.0 — 04C-2 Perpetual Funding Carry BTC/ETH

## Estado

**PREDECLARADO — parámetros económicos congelados antes de calcular PnL 04C-2.**

04C-1 confirmó que existe carry agregado en futuros trimestrales, pero la realización por `deliveryPrice` no fue suficientemente estable. 04C-2 prueba una estrategia materialmente distinta y más cercana a la literatura de perpetuals: **long Spot + short USD-M perpetual con igual cantidad de activo base**, mantenida de forma continua y medida en los settlements reales de funding.

No se usa funding para predecir Spot. El funding es directamente una fuente de cash-flow de la posición short perpetual.

Antes de observar PnL 04C-2 se hizo una auditoría exclusivamente temporal de los 8,766 `fundingTime` BTC/ETH 2022-2025. Encontró offset máximo de 31 ms respecto a la hora nominal y p99 de 22 ms en ambos activos. Sobre esa evidencia, y todavía sin PnL, se fijó una regla determinista: normalizar hacia abajo a la hora nominal únicamente si el offset es <=1,000 ms; cualquier offset mayor falla cerrado.

La misma auditoría detectó que los únicos huecos restantes en horas de funding provenían de `markPriceKlines` mensuales: 9 BTC y 6 ETH, concentrados en 2022-07-31, 2022-10-02 y 2023-02-24. Binance publica también archivos diarios oficiales de `markPriceKlines`; 04C-2 puede usarlos exclusivamente como fallback de la misma serie cuando el mensual carece de una hora. Esto **no es imputación**: la observación debe existir literalmente en el archivo diario o el gate sigue fallando.

## Referencias externas

Referencias primarias:

1. Christin, Routledge, Soska y Zetlin-Jones, *The Crypto Carry Trade* (CMU working paper). En Binance, la estrategia Tether-margined se define como long coin + short perpetual; su retorno por ventana de funding se descompone en funding recibido + cambio del basis. En la submuestra posterior a la reducción de leverage de Binance reportan aproximadamente 10.22% anual para BTC y 9.75% para ETH, con Sharpe 7.943 y 6.882 respectivamente. Es evidencia histórica, no un objetivo a replicar ni una garantía.
2. He, Manela, Ross y von Wachter, *Fundamentals of Perpetual Futures*. Derivan bounds de no arbitraje con costos y documentan que perpetuals pueden desviarse de spot; una estrategia de arbitraje implícita presenta Sharpe alto incluso con costos elevados.

La literatura también muestra que condicionar exclusivamente a funding positivo aporta poco en muestras donde funding es positivo gran parte del tiempo. Por eso **04C-2 es incondicional**: no selecciona periodos por funding observado.

## Universo

Exclusivamente:

- BTCUSDT Spot + BTCUSDT USD-M perpetual;
- ETHUSDT Spot + ETHUSDT USD-M perpetual.

Ventana cerrada:

- desde 2022-01-01 00:00 UTC;
- hasta 2025-12-31 23:59:59 UTC;
- 2026 cerrado;
- mayo-julio 2026 cerrado.

No se añaden altcoins, COIN-M, otros exchanges ni DEX.

## Datos

Fuentes públicas Binance Vision:

- `spot/monthly/klines/{symbol}/1h`;
- `futures/um/monthly/klines/{symbol}/1h`;
- `futures/um/monthly/markPriceKlines/{symbol}/1h`;
- `futures/um/monthly/fundingRate/{symbol}`;
- fallback permitido solo para huecos reales del mensual: `futures/um/daily/markPriceKlines/{symbol}/1h`.

Se conservan los settlements reales publicados en funding history. **No se presupone una cadencia fija de 8h**; se usa `funding_interval_hours` del archivo.

Alineación temporal pre-PnL:

1. conservar el `funding_interval_hours` y `last_funding_rate` originales;
2. calcular `offset = fundingTime % 3,600,000`;
3. si `offset <= 1,000 ms`, usar como clave de mercado `fundingTime - offset`;
4. si `offset > 1,000 ms`, rechazar el dato;
5. después de normalizar, timestamps duplicados fallan cerrado;
6. Spot, perpetual y mark deben existir en esa hora nominal;
7. si solo falta mark en el mensual, se consulta el archivo diario oficial del mismo símbolo/día/intervalo y se usa únicamente si contiene exactamente esa hora;
8. no se interpola, forward-fill, backward-fill ni sintetiza ningún precio.

## Construcción de la posición

Por cada activo:

- long `1` unidad Spot;
- short `1` unidad USD-M perpetual;
- sin leverage económico adicional;
- sin selección por signo de funding;
- sin market timing;
- sin rebalanceo de cantidad base dentro del año.

04C-2 mide la **prima económica**. El capital/margen real, top-ups, liquidation distance y reglas operativas se modelarán en 04C-3 si y solo si 04C-2 supera el gate económico y el gate candidato a producción.

## Retorno por intervalo de funding

Para dos settlements consecutivos `t0 < t1` del mismo activo:

- `S0`, `S1`: Spot open 1h en `t0`, `t1`;
- `F0`, `F1`: perpetual open 1h en `t0`, `t1`;
- `M1`: mark-price open 1h en `t1`;
- `r1`: `last_funding_rate` realizado en `t1`.

El short recibe funding cuando `r1 > 0`.

Por una unidad base:

`spot_pnl = S1 - S0`

`perp_pnl = F0 - F1`

`funding_pnl = r1 * M1`

`gross_pnl = spot_pnl + perp_pnl + funding_pnl`

`interval_return_notional = gross_pnl / S0`

La descomposición diagnóstica obligatoria será:

- funding;
- cambio de basis;
- carry total.

No se cambia el signo tras ver resultados.

## Evaluación anual

Cada año 2022, 2023, 2024 y 2025 se trata como una sleeve independiente para evitar que un solo periodo de carry domine toda la muestra y para aplicar costos de forma conservadora.

Por activo/año:

- inicio = primer settlement real del año;
- fin = último settlement real del año;
- se usan todos los intervalos consecutivos dentro de ese año;
- no se cruza el límite de año;
- no se usa ningún precio 2026 para cerrar 2025.

Se aplica un **drag all-in fijo de 60 bps por año sobre el notional Spot inicial de cada sleeve**. Este drag representa de forma conservadora entrada/salida, fees, spread, slippage y fricción operativa. No se probarán otros costos en 04C-2; no se asume BNB discount, VIP ni maker fill.

`annual_net_notional = annual_gross_notional - 0.006`

Referencia de capital para decidir si merece pasar a ingeniería operativa:

`reference_committed_capital = 2 * spot_notional`

por lo que:

`annual_net_committed = annual_net_notional / 2`

Esto **no** afirma que el capital real necesario sea 2x. 04C-3 debe reconstruir margen y top-ups; por eso 04C-2 solo usa 2x como filtro mínimo de viabilidad.

## Portafolio primario

El veredicto primario es BTC+ETH equal-weight.

Para cada año:

`portfolio_net_notional = mean(BTC annual_net_notional, ETH annual_net_notional)`

BTC-only y ETH-only se reportan, pero no pueden rescatar el resultado conjunto.

## Sharpe y drawdown

Se construye una serie diaria BTC+ETH equal-weight usando los retornos de intervalos de funding ocurridos en cada día UTC.

- retorno diario bruto = suma de intervalos del día por activo y luego media BTC/ETH;
- drag anual de 60 bps se amortiza linealmente como `0.006 / días_del_año` sobre notional;
- Sharpe diario neto anualizado = `mean(daily_net) / stdev(daily_net) * sqrt(365)`;
- max drawdown se calcula sobre riqueza acumulada `prod(1 + daily_net)`.

No se usan retornos diarios para seleccionar periodos.

## Gate de datos

`DATOS_INSUFICIENTES_04C2` si cualquiera ocurre:

1. falta algún mes de funding BTC o ETH;
2. cobertura de eventos alineados Spot+Perp+Mark < 99% por activo;
3. existe timestamp de funding normalizado duplicado;
4. existe evento fuera de 2022-2025;
5. precio/mark no positivo o no finito;
6. falta cualquiera de los cuatro años en BTC o ETH;
7. existe un salto entre settlements alineados que no coincide con el `funding_interval_hours` publicado para el settlement final;
8. algún `fundingTime` tiene offset >1 segundo respecto de la hora nominal;
9. un fallback diario requerido falla o no contiene la observación exacta solicitada.

Sin imputación.

## Gate económico

`CARRY_ECONOMICAMENTE_APTO_04C2` únicamente si simultáneamente:

1. datos aptos;
2. portafolio BTC+ETH neto > 0 en **4/4 años**;
3. media de retorno anual neto sobre notional > 0;
4. Sharpe diario neto anualizado >= 1.0;
5. max drawdown diario neto <= 10%;
6. componente funding agregado 2022-2025 > 0.

## Gate candidato a producción

`CARRY_CANDIDATO_PRODUCCION_04C2` únicamente si además del gate económico:

1. media anual neta sobre capital de referencia 2x >= **5%**;
2. peor año neto sobre capital de referencia 2x >= **2%**;
3. Sharpe diario neto anualizado >= **2.0**;
4. max drawdown diario neto <= **7.5%**.

Estos thresholds se fijaron **antes** del PnL para evitar desplegar una estrategia que sea positiva pero demasiado débil para compensar riesgo de exchange, custodia, margen y operación.

Si pasa el gate económico pero no el de producción, no se baja ningún threshold: se documenta como prima real pero insuficiente para producción bajo este protocolo.

## Diagnósticos obligatorios

- número real de settlements por año/activo;
- distribución de `funding_interval_hours`;
- cobertura alineada;
- funding PnL por año/activo;
- basis-change PnL por año/activo;
- gross y net returns;
- BTC-only y ETH-only;
- portfolio equal-weight;
- Sharpe diario neto;
- max drawdown;
- peor día;
- fracción de días net-positive;
- máxima excursión adversa de mark por año como insumo para 04C-3, **sin usarla para cambiar 04C-2**.

## Candados

- no cambiar BTC/ETH;
- no seleccionar solo periodos con funding positivo;
- no cambiar 60 bps/año;
- no cambiar equal-weight;
- no cambiar thresholds tras observar resultados;
- no ampliar la tolerancia temporal >1 segundo;
- no usar fuentes distintas de Binance Vision para completar market data;
- no interpolar huecos;
- no añadir leverage;
- no optimizar hedge ratio;
- no altcoins;
- no otros exchanges;
- no imputación;
- no GPT;
- no 2026;
- no PAPER operativo;
- no LIVE;
- no Render;
- no mergear investigación.

## Camino a producción

04C-2 **no autoriza producción**. Si alcanza `CARRY_CANDIDATO_PRODUCCION_04C2`, el siguiente gate obligatorio es 04C-3:

1. reproducir margin balance y maintenance margin;
2. calcular top-ups necesarios y capital efectivo pico;
3. incorporar fee schedule real de la cuenta;
4. slippage/depth en tamaños objetivo;
5. liquidation distance y circuit breakers;
6. fallo de una sola pata / partial fills;
7. exchange/API outage;
8. PAPER shadow continuo sin órdenes reales;
9. holdout 2026 solo después de congelar todo lo anterior.

LIVE permanece cerrado hasta completar esos gates.