# BOT 2.0 — 04C-0 Auditoría de carry

## Estado final

**`DATASET_CARRY_APTO_04C0` — auditoría completada con datos suficientes. No se calculó PnL.**

Resultado reproducible sobre Binance Public Data 2022–2025:

- Spot BTCUSDT: 48/48 meses;
- Spot ETHUSDT: 48/48 meses;
- funding perpetual BTCUSDT: 48/48 meses;
- funding perpetual ETHUSDT: 48/48 meses;
- 32 futuros fechados USD-M descubiertos: 16 BTC + 16 ETH;
- cuatro vencimientos por año y subyacente en 2022, 2023, 2024 y 2025;
- continuidad de klines de contratos fechados: 100%;
- cobertura de `markPriceKlines`: 100%;
- cero motivos de rechazo;
- inventario total usado por el gate: aproximadamente 0.012590 GiB comprimidos.

Workflow válido: `research-04c0` run #1, success. CI general del mismo HEAD: run #96, **1141 tests passed**, `compileall` OK, frontend 841 módulos y v20.1 revalidada.

04C-0 demuestra únicamente que la réplica histórica de cash-and-carry es técnicamente viable. No demuestra rentabilidad.

## Base externa

La referencia principal es *Crypto Carry* (Schmeling, Schrimpf y Todorov; Management Science, publicado online 6-may-2026; BIS Working Paper 1087). El trabajo define el carry como la diferencia entre futuros y Spot y estudia una posición cash-and-carry long Spot / short Futures. Documenta una prima de carry económicamente relevante, pero también advierte que no es una oportunidad libre de riesgo por fricciones de margen, segmentación y posibles pérdidas mark-to-market antes del vencimiento.

## Universo auditado

- BTC y ETH únicamente;
- Spot USDT: `BTCUSDT`, `ETHUSDT`;
- futuros fechados USD-M descubiertos desde el archivo público, patrón `BTCUSDT_YYMMDD` / `ETHUSDT_YYMMDD`;
- perpetuos `BTCUSDT`, `ETHUSDT` solo como variante secundaria para auditoría de funding;
- ventana histórica: 2022-01-01 a 2025-12-31;
- 2026 cerrado.

No se amplió a altcoins.

## Fuentes auditadas

Binance Public Data / `data.binance.vision`:

1. Spot monthly `1h` klines de BTCUSDT y ETHUSDT;
2. USD-M monthly `1h` klines de contratos fechados BTC/ETH;
3. USD-M monthly `1h` markPriceKlines de esos mismos contratos;
4. USD-M monthly fundingRate de los perpetuos BTCUSDT/ETHUSDT.

04C-0 listó metadatos S3; **no descargó ZIP para calcular retornos**.

## Contratos fechados encontrados

BTC y ETH presentan la misma parrilla trimestral:

- 2022: 220325, 220624, 220930, 221230;
- 2023: 230331, 230630, 230929, 231229;
- 2024: 240329, 240628, 240927, 241227;
- 2025: 250328, 250627, 250926, 251226.

Todos los 32 contratos pasaron continuidad de trade-price y mark-price desde su primer mes observado hasta el mes de vencimiento.

## Gate de aptitud aplicado

El resultado solo podía ser `DATASET_CARRY_APTO_04C0` si simultáneamente:

- Spot BTC y ETH tenían los 48 meses 2022–2025 en `1h`;
- existían futuros fechados BTC y ETH con vencimientos en los cuatro años;
- cada año tenía al menos dos vencimientos archivados por subyacente;
- al menos 90% de contratos fechados tenían continuidad mensual hasta vencimiento;
- al menos 90% tenían `markPriceKlines` suficientes;
- funding perpetual BTC/ETH estaba disponible al menos en 95% de los 48 meses;
- no había objetos ZIP de tamaño cero usados por el gate;
- los listados S3 terminaban completamente.

Todos los requisitos se cumplieron.

## Costos y ejecución todavía no inferidos

04C-0 no fijó una comisión histórica por conveniencia. Antes de observar PnL en 04C-1 deben quedar congelados:

- modelo conservador de fee Spot;
- modelo conservador de fee Futures;
- spread/slippage por pata;
- capital inmovilizado;
- margen y buffer de liquidación;
- tratamiento de mark-to-market;
- tipo de ejecución maker/taker;
- hora exacta de entrada y settlement.

Tampoco se asume cross-margin ni acceso de una cuenta real a Futures.

## Variante primaria

La siguiente fase será una réplica de **futuro fechado**, no una predicción direccional: long Spot + short future fechado aproximadamente un mes antes del vencimiento, con el mismo notional y seguimiento de riesgo mark-to-market hasta settlement. Perpetual funding carry queda fuera de esa misma prueba.

## Candados preservados

- no hubo PnL en 04C-0;
- no hubo thresholds de entrada de basis/funding;
- no hubo optimización;
- no se eligieron contratos por rentabilidad observada;
- sin 2026;
- sin mayo-julio 2026;
- sin credenciales reales;
- sin órdenes;
- sin PAPER operativo;
- sin LIVE;
- sin Render;
- sin GPT para decidir operaciones;
- no mergear esta rama de investigación.

## Decisión

**Habilitado diseñar 04C-1.** La metodología y los costos de 04C-1 deberán predeclararse antes de leer retornos históricos. Si la réplica económica falla, no se rescatará cambiando retrospectivamente entrada, vencimientos, leverage o hurdle.