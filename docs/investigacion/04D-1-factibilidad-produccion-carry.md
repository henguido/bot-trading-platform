# BOT 2.0 — 04D-1 Factibilidad pública de producción del carry 04C-2

## Estado

**AUDITORÍA READ-ONLY. No modifica la estrategia 04C-2, no envía órdenes y no autoriza producción.**

04C-2 demostró una prima económica en BTC/ETH long Spot + short USD-M perpetual durante 2022-2025, pero no superó su gate de producción conservador. 04C-3 no ofreció una alternativa de mejor eficiencia: 0/32 calendar spreads fueron elegibles bajo su protocolo congelado.

04D-1 deja de buscar edge. Su objetivo es identificar los blockers operativos reales del edge ya demostrado.

## Preguntas

1. ¿Los libros públicos actuales BTC/ETH Spot y USD-M soportan tamaños modestos y medianos sin consumir una parte material del presupuesto de 60 bps heredado de 04C-2?
2. ¿La arquitectura ingenua `1x Spot + 1x USDT de margen Futures`, sin top-ups ni cross-collateral, habría sobrevivido al stress histórico observado en 04C-2?
3. ¿Qué datos faltan necesariamente antes de poder modelar liquidation y capital efectivo de una cuenta real?

## Inputs congelados

De PR #31, cerrado sin merge:

- `CARRY_ECONOMICAMENTE_APTO_04C2`;
- `CARRY_NO_CANDIDATO_PRODUCCION_04C2`;
- media anual neta notional 9.3764%;
- media anual sobre referencia 2x 4.6882%;
- peor año sobre referencia 2x 0.6207%;
- Sharpe 10.3481;
- max DD económico 0.8881%;
- mark excursions anuales BTC/ETH copiadas en `carry_04c2_inputs_04d1.json`.

04D-1 no recalcula esos retornos ni cambia sus gates.

## Audit de order book

Se consultan exclusivamente endpoints públicos:

- Spot: `GET /api/v3/depth`;
- USD-M Futures: `GET /fapi/v1/depth`.

Símbolos:

- BTCUSDT;
- ETHUSDT.

Escalas fijas antes de ejecutar el audit:

- $500;
- $5,000;
- $25,000;
- $100,000 de compra Spot inicial por activo.

Para cada escala:

1. simular market-buy Spot y obtener la cantidad base;
2. simular short Futures por exactamente esa cantidad base;
3. simular venta Spot de la misma cantidad;
4. simular recompra Futures de la misma cantidad;
5. calcular VWAP y profundidad consumida;
6. medir fricción hipotética round-trip de cruzar los dos libros al snapshot.

No se envía ninguna orden.

Gate de liquidez pública:

`roundtrip_book_friction <= 10 bps`

para los cuatro tamaños y ambos activos.

Los 10 bps no reemplazan fees. Sirven para medir si spread + market impact visible consumen una parte material del **budget all-in de 60 bps heredado de 04C-2**. El fee tier real de la cuenta sigue pendiente.

Un snapshot favorable tampoco garantiza fills futuros; 04D-1 es capacity screening, no simulación de ejecución completa.

## Audit histórico de margen

04C-2 reportó la máxima excursión adversa anual del mark price de la pata short.

Para un short estático con margen USDT separado, un lower bound deliberadamente favorable para simplemente absorber PnL adverso es:

`minimum_futures_margin_multiple >= mark_excursion`

Por tanto:

`minimum_total_capital_multiple >= 1x Spot + mark_excursion`

Este cálculo **ignora** maintenance margin, fees y cualquier diferencia mark/index. Es un lower bound, no una fórmula de liquidation.

Se compara contra la referencia simplificada de 04C-2:

`1x Spot + 1x Futures margin = 2x total`.

Si `1 + mark_excursion > 2`, queda demostrado que la arquitectura estática 2x no habría bastado incluso antes de maintenance margin.

Inputs de stress:

| Activo | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| BTC | 3.57% | 167.96% | 154.15% | 34.11% |
| ETH | 4.99% | 104.22% | 79.49% | 44.92% |

Consecuencias matemáticas pre-audit:

- BTC 2023: lower bound total 2.6796x;
- BTC 2024: 2.5415x;
- ETH 2023: 2.0422x.

Así, si el código reproduce esos valores, la arquitectura aislada estática de 2x queda falsada como implementación segura del histórico.

Esto **no falsifica el edge económico**. Significa que el hedge debe compartir collateral económico, recibir top-ups oportunos o usar una arquitectura equivalente que evite liquidación de una pata mientras la otra acumula la ganancia compensatoria.

## Información que no se inventará

Binance ajusta leverage y maintenance margin por notional bracket. Los brackets y la configuración efectiva dependen de datos de cuenta/posición. Asimismo, Multi-Assets Mode puede admitir activos distintos de USDT como collateral sujeto a collateral ratios/haircuts.

04D-1 no tiene autorización para usar credenciales. Por tanto deja explícitamente pendientes:

- fee tier real Spot;
- fee tier real USD-M;
- leverage brackets BTCUSDT/ETHUSDT aplicables a la cuenta;
- maintenance margin rate;
- collateral ratios/haircuts del modo real que se usaría;
- balances disponibles para top-ups;
- configuración Cross/Isolated/Multi-Assets.

La página pública de fees de Binance depende de contexto/login y la API de metadata de collateral consultada sin credenciales rechazó la solicitud; por tanto no se hardcodea un fee o haircut actual como si fuese dato de cuenta.

## Evidencia externa vigente

Binance documenta en 2026 que:

- leverage y maintenance margin dependen del notional bracket;
- mayor leverage aumenta el riesgo de liquidación;
- Multi-Assets Mode permite usar otros activos, incluido BTC en productos compatibles, como collateral sujeto a haircuts;
- funding de perpetuals es un cash-flow entre longs y shorts y el intervalo puede ser dinámico.

Estas reglas justifican el siguiente gate autenticado/read-only, pero no alteran el backtest 2022-2025.

## Veredictos posibles 04D-1

Liquidez:

- `EJECUCION_PUBLICA_APTA_04D1`;
- `EJECUCION_PUBLICA_NO_VERIFICADA_04D1`.

Margen:

- `MARGEN_ESTATICO_2X_INSUFICIENTE_04D1`;
- `MARGEN_ESTATICO_2X_NO_FALSADO_04D1`.

Overall de esta etapa siempre permanece:

`PRODUCCION_NO_AUTORIZADA_04D1`

porque faltan fee tier, brackets, maintenance margin y collateral ratios reales.

## Siguiente gate si 04D-1 completa

04D-2 debe ser **read-only account metadata**, no trading:

1. consultar fee tier efectivo;
2. obtener leverage brackets/maintenance margin para BTCUSDT y ETHUSDT;
3. obtener collateral ratios aplicables;
4. elegir Cross/Isolated/Multi-Assets de forma explícita;
5. reconstruir liquidation buffer y top-ups en cada intervalo histórico 04C-2;
6. calcular capital efectivo pico;
7. mantener LIVE cerrado.

Solo después correspondería construir un PAPER shadow planner. El holdout 2026 seguirá cerrado hasta congelar la arquitectura operacional.

## Candados

- no órdenes;
- no credenciales;
- no Render;
- no LIVE;
- no cambios a scanner/risk/PAPER operativo;
- no cambios a retornos o thresholds 04C-2;
- no usar 2026 como retorno;
- no mergear esta investigación antes de cerrar el audit.
