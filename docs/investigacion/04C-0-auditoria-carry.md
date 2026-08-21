# BOT 2.0 — 04C-0 Auditoría de carry

## Estado

**PREDECLARADO — auditoría de datos/instrumentos, sin PnL y sin selección por resultados internos.**

04B queda cerrada como familia direccional. 04C adopta un funnel literature-first. La metodología candidata prioritaria es **cash-and-carry delta-neutral**: long Spot y short Futures para capturar basis/funding, no para predecir la dirección del Spot.

## Base externa

La referencia principal es *Crypto Carry* (Schmeling, Schrimpf y Todorov; Management Science, publicado online 6-may-2026; BIS Working Paper 1087). El trabajo define el carry como la diferencia entre futuros y Spot y estudia una posición cash-and-carry long Spot / short Futures. Documenta carry promedio superior al 10% anual y episodios por encima del 40%, pero también advierte que no es una oportunidad libre de riesgo por fricciones de margen, segmentación y posibles pérdidas mark-to-market antes del vencimiento.

04C-0 no intenta replicar aún esos retornos. Primero verifica si Binance permite una reconstrucción histórica suficientemente fiel.

## Universo fijado

- BTC y ETH únicamente;
- Spot USDT: `BTCUSDT`, `ETHUSDT`;
- futuros fechados USD-M descubiertos desde el archivo público, patrón `BTCUSDT_YYMMDD` / `ETHUSDT_YYMMDD`;
- perpetuos `BTCUSDT`, `ETHUSDT` solo como variante secundaria para auditoría de funding;
- ventana histórica: 2022-01-01 a 2025-12-31;
- 2026 cerrado.

No se amplía a altcoins si BTC/ETH no muestran infraestructura histórica suficiente.

## Fuentes a inventariar

Binance Public Data / `data.binance.vision`:

1. Spot monthly `1h` klines de BTCUSDT y ETHUSDT;
2. USD-M monthly `1h` klines de contratos fechados BTC/ETH;
3. USD-M monthly `1h` markPriceKlines de esos mismos contratos;
4. USD-M monthly fundingRate de los perpetuos BTCUSDT/ETHUSDT.

Se listan metadatos S3; **no se descargan ZIP en 04C-0**.

## Qué debe medir

Por subyacente y contrato:

- contratos fechados realmente archivados;
- fecha de vencimiento codificada en el símbolo;
- primer/último mes disponible;
- continuidad mensual desde el primer mes observado hasta el mes de vencimiento;
- archivos de tamaño cero y duplicados;
- existencia pareada de trade-price klines y mark-price klines;
- cobertura Spot 2022–2025;
- cobertura de funding perpetual 2022–2025;
- bytes comprimidos de cada familia para dimensionar 04C-1.

## Gate de aptitud de datos

El resultado será `DATASET_CARRY_APTO_04C0` solo si simultáneamente:

- Spot BTC y ETH tienen los 48 meses 2022–2025 en `1h`;
- existen futuros fechados BTC y ETH con vencimientos en los cuatro años;
- cada año tiene al menos dos vencimientos archivados por subyacente;
- al menos 90% de los contratos fechados descubiertos tienen continuidad mensual de klines hasta su mes de vencimiento;
- al menos 90% tienen markPriceKlines pareados suficientes para modelar riesgo mark-to-market;
- funding perpetual BTC/ETH está disponible al menos en 95% de los 48 meses;
- no hay objetos ZIP de tamaño cero en los objetos usados por el gate;
- el listado S3 termina completamente, sin error de paginación.

Si falla el gate, no se calcula PnL y se documenta la brecha.

## Costos y ejecución: qué NO se inferirá todavía

04C-0 no fija una comisión histórica por conveniencia. Binance usa maker/taker y la tarifa depende del producto, VIP/BNB y condiciones vigentes. Tampoco se asumirá cross-margin ni acceso de la cuenta a Futures.

Antes de 04C-1 deberán quedar fijados:

- modelo conservador de fee Spot;
- modelo conservador de fee Futures;
- spread/slippage por pata;
- capital inmovilizado;
- margen y buffer de liquidación;
- tratamiento de mark-to-market;
- si la simulación usa entrada/salida taker o maker;
- impuestos/costos externos, si aplican al caso real.

## Variante primaria y secundaria

### Primaria: futuros fechados

Long Spot + short future fechado. El basis converge mecánicamente al vencimiento, sujeto a ejecución, margen y riesgo de liquidación. Esta variante es la más cercana a la referencia académica y será la primera candidata a 04C-1.

### Secundaria: perpetual funding carry

Long Spot + short perpetual cuando funding esperado sea positivo. No se mezclará con la variante fechada en un mismo backtest. Funding puede cambiar de signo y los intervalos pueden cambiar, por lo que requiere otra especificación.

## Candados

- sin PnL en 04C-0;
- sin thresholds de entrada de basis/funding;
- sin optimización;
- sin elegir contratos por rentabilidad observada;
- sin 2026;
- sin mayo-julio 2026;
- sin credenciales reales;
- sin órdenes;
- sin PAPER operativo;
- sin LIVE;
- sin Render;
- sin GPT para decidir operaciones;
- no mergear mientras sea investigación.

## Decisión posterior

Si `DATASET_CARRY_APTO_04C0`, 04C-1 deberá predeclarar una única réplica económica de cash-and-carry **antes de leer sus retornos**, incluyendo fees, slippage, capital total comprometido, margen y criterio de liquidación. Si no es apto, no se rescata cambiando universo o años dentro de 04C-0.
