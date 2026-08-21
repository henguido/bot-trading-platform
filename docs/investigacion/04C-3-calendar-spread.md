# BOT 2.0 — 04C-3 Calendar Spread Perpetual vs Quarterly

## Estado

**PREDECLARADO — parámetros económicos y gates congelados antes de calcular PnL 04C-3.**

04C-2 demostró una prima económica en long Spot + short USD-M perpetual BTC/ETH, pero no superó el gate de producción por eficiencia de capital y por el año 2022. 04C-3 no modifica esa estrategia ni sus thresholds. Prueba una estructura distinta y aproximadamente delta-neutral dentro de Binance USD-M:

**long perpetual + short futuro trimestral**, igual cantidad de activo base.

La hipótesis es que una prima trimestral suficientemente alta puede capturarse contra el perpetual, pagando durante el holding el funding real de la pata long perpetual.

## Motivación externa

De Blasis y Webb (Journal of Futures Markets, 2022, DOI 10.1002/fut.22305) estudian específicamente futuros perpetuos y trimestrales stablecoin-denominated de Binance. Documentan diferencias de microestructura, spillovers y oportunidades de cash-and-carry en futuros trimestrales, especialmente durante dislocaciones. La disponibilidad de datos de su estudio se atribuye a Binance Vision.

Esta referencia motiva la familia; **no fija ni optimiza nuestros retornos**.

El 21-ago-2026 se verificó mediante metadata pública de Binance USD-M que BTC/ETH continúan ofreciendo contratos `PERPETUAL`, `CURRENT_QUARTER` y `NEXT_QUARTER`. Esa consulta solo valida la existencia actual de la estructura contractual; ningún precio o retorno 2026 entra en 04C-3.

## Universo y calendario

Exclusivamente:

- BTCUSDT;
- ETHUSDT;
- Binance USD-M perpetual;
- Binance USD-M quarterly futures.

Años cerrados: 2022, 2023, 2024, 2025.

Para cada año se usan los vencimientos trimestrales del tercer viernes de marzo, junio, septiembre y diciembre a las 08:00 UTC.

Entrada fija: **28 días exactos antes del expiry, 08:00 UTC**.

Esto produce 16 expiries × 2 activos = **32 oportunidades esperadas**. El horizonte de 28 días se hereda de 04C-1 y no se modifica después de ver 04C-3.

2026 permanece holdout cerrado.

## Datos

Binance Vision público:

- perpetual 1h: `futures/um/monthly/klines/{symbol}/1h`;
- quarterly 1h: `futures/um/monthly/klines/{contract}/1h`;
- perpetual mark 1h: `futures/um/monthly/markPriceKlines/{symbol}/1h`;
- funding history: `futures/um/monthly/fundingRate/{symbol}`.

Delivery price:

- fixture de 32 valores copiado literalmente de 04C-1;
- esos valores proceden de `GET /futures/data/delivery-price` y fueron capturados antes de observar PnL 04C-1;
- se reutilizan en 04C-3 antes de observar PnL 04C-3 para evitar depender del endpoint desde runners GitHub.

No se usa Spot para generar retorno 04C-3.

## Semántica temporal

Los `fundingTime` de Binance pueden tener un desplazamiento de milisegundos respecto a la hora nominal. Se reutiliza el tratamiento validado pre-PnL en 04C-2:

- solo aceptar offset desde la hora nominal `<= 1 segundo`;
- normalizar mecánicamente a esa hora;
- para mark price faltante en archivo mensual, permitir únicamente fallback al archivo diario oficial de Binance Vision del mismo día;
- si sigue faltando, fail closed;
- sin interpolación ni forward-fill.

## Posición

Por oportunidad elegible:

- long `1` unidad base del USD-M perpetual;
- short `1` unidad base del quarterly;
- sin leverage económico adicional;
- sin optimizar hedge ratio.

Referencia de capital de screening: **1× notional del perpetual en entrada**.

Esto no afirma que 1× sea el margen real requerido. Si 04C-3 pasa el gate de producción, una etapa posterior debe reconstruir initial margin, maintenance margin, margin ratio, top-ups y liquidation distance con reglas reales de Binance.

## Regla de elegibilidad ex-ante

Solo se usa información conocida en el instante de entrada.

Definiciones en `entry`:

- `P0`: perpetual open 1h;
- `Q0`: quarterly open 1h;
- `entry_spread = (Q0 - P0) / P0`;
- `trailing_funding_cost`: suma de los pagos que habría soportado una posición long perpetual durante los **28 días inmediatamente anteriores** a entry, usando funding realizado y mark price publicado, dividida por `P0`.

`predicted_net = entry_spread - trailing_funding_cost - 0.006`

Se entra **únicamente si `predicted_net > 0`**.

No se prueba otro lookback, otro umbral, otro signo ni otro modelo. No se usa funding futuro para decidir.

Si la oportunidad no es elegible, esa sleeve permanece en cash y aporta retorno cero.

## PnL realizado

Para una operación elegible:

- `P1`: perpetual open 1h en expiry;
- `D`: delivery price oficial del quarterly;
- funding de holding: eventos estrictamente `entry < fundingTime < expiry`, para no asumir de forma favorable el orden de funding/ejecución exactamente en los boundaries.

Por 1 unidad base:

`perp_pnl = P1 - P0`

`quarter_pnl = Q0 - D`

`funding_pnl_long = -sum(rate_i * mark_i)`

`gross_pnl = perp_pnl + quarter_pnl + funding_pnl_long`

`gross_return = gross_pnl / P0`

Coste fijo conservador por round-trip completo de ambas patas:

`net_return = gross_return - 0.006`

Los **60 bps se aplican por trade**, no por año. No se reduce este coste tras observar resultados.

## Stress intratrade

Durante cada holding se reconstruye cada hora disponible común entre perpetual y quarterly:

`mtm_t = (P_t - P0) + (Q0 - Q_t) + funding_acumulado_long_hasta_t`

`mtm_return_t = mtm_t / P0`

Se registra la peor excursión negativa desde entry. No se usa para cambiar posiciones retrospectivamente; es un gate de riesgo/margen.

Cobertura horaria mínima para stress: **95%** de las horas esperadas. Entry y expiry son obligatorios.

## Agregación

Los cuatro trades trimestrales no se solapan dentro de cada activo.

Por activo/año:

`annual_return = sum(net_return de trades elegibles del año)`

Una oportunidad no elegible aporta cero.

Portafolio primario por año:

`portfolio_year = mean(BTC annual_return, ETH annual_return)`

Por quarter se calcula igual, con cash=0 para la pata no elegible. La serie de 16 retornos trimestrales del portafolio se usa para Sharpe y drawdown.

Sharpe trimestral anualizado:

`mean(quarterly) / stdev(quarterly) * sqrt(4)`

## Gate de datos

`DATOS_INSUFICIENTES_04C3` si ocurre cualquiera:

1. fixture no contiene los 32 delivery prices esperados;
2. falta entry o expiry perpetual para alguna oportunidad;
3. falta quarterly entry para alguna oportunidad;
4. falta cualquier funding/mark necesario para lookback o holding;
5. funding duplicado o timestamp con offset >1 segundo;
6. precio no positivo/no finito;
7. cobertura horaria de stress <95% en cualquier oportunidad evaluable;
8. evento fuera de 2022-2025 en la muestra de retorno;
9. cualquier descarga/parse obligatorio falla sin fuente oficial alternativa declarada.

Sin imputación.

## Gate económico

`CALENDAR_ECONOMICAMENTE_APTO_04C3` solo si simultáneamente:

1. datos aptos;
2. al menos **8 trades elegibles** de las 32 oportunidades;
3. portafolio neto >0 en **4/4 años**;
4. media anual neta >0;
5. Sharpe trimestral neto >= **1.0**;
6. max drawdown trimestral <= **15%**;
7. peor stress intratrade >= **-15%**.

## Gate candidato a producción

`CALENDAR_CANDIDATO_PRODUCCION_04C3` solo si, además del gate económico:

1. media anual neta sobre capital de referencia 1× >= **5%**;
2. peor año neto >= **2%**;
3. Sharpe trimestral neto >= **1.5**;
4. max drawdown trimestral <= **7.5%**;
5. peor stress intratrade >= **-7.5%**;
6. win rate entre trades elegibles >= **60%**;
7. al menos **8 trades elegibles**.

No se baja ningún gate tras observar resultados.

## Diagnósticos obligatorios

Por cada una de las 32 oportunidades:

- contract code;
- entry/expiry;
- entry spread;
- trailing 28d funding cost;
- predicted net;
- elegible sí/no;
- realized funding del holding;
- perp PnL;
- quarterly PnL;
- gross/net return;
- horas de stress esperadas/observadas;
- peor stress intratrade.

Agregados:

- trades elegibles por activo/año;
- win rate;
- retorno anual BTC, ETH y equal-weight;
- retorno por quarter;
- media anual;
- peor año;
- Sharpe trimestral;
- max drawdown;
- peor stress intratrade.

## Candados

- BTC/ETH solamente;
- 28 días de holding;
- 28 días de trailing funding;
- predicted net >0 como única regla;
- 60 bps por trade;
- no cambiar sign;
- no probar múltiples lookbacks/thresholds y escoger ganador;
- no altcoins;
- no otros exchanges;
- no leverage adicional;
- no imputation;
- no GPT;
- no 2026;
- no PAPER operativo;
- no LIVE;
- no Render;
- no mergear investigación.

## Camino si supera producción

04C-3 todavía no autoriza producción. Un resultado `CALENDAR_CANDIDATO_PRODUCCION_04C3` habilitaría la siguiente etapa operativa:

1. margin model real USD-M para ambas patas;
2. initial/maintenance margin y liquidation distance;
3. top-ups y capital efectivo pico;
4. fee tier real y funding operational timing;
5. order-book slippage para tamaños objetivo;
6. partial-fill/leg risk;
7. rollover/expiry mechanics;
8. API/exchange outage y circuit breakers;
9. PAPER shadow sin órdenes reales;
10. solo después, apertura única del holdout 2026.

LIVE permanece cerrado hasta completar esos gates.
