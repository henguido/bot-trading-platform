# BOT 2.0 — 04D-2: collateral/margin architecture read-only

## Estado

**PREDECLARADO. READ-ONLY. NO AUTORIZA TRADING.**

04D-2 no busca un edge nuevo y no modifica 04C-2. Su objetivo es obtener la metadata mínima de cuenta necesaria para modelar una arquitectura de collateral compartido sin inventar fee tiers, maintenance margin, leverage brackets ni modo de margen.

## Contexto heredado

04C-2 demostró edge económico long Spot + short USD-M perpetual BTC/ETH en 2022-2025, pero no pasó producción bajo referencia committed 2x.

04D-1 mostró dos cosas:

1. liquidez pública actual apta en snapshot hasta $100k/activo: máximo 3.4182 bps de fricción visible round-trip frente a gate 10 bps;
2. una arquitectura **separada** 1x Spot + 1x margen Futures queda falsada por stress histórico de BTC 2023, BTC 2024 y ETH 2023.

Eso no descarta Cross/Multi-Assets/Portfolio Margin, porque una arquitectura de collateral compartido puede reconocer parte del hedge económico, sujeto a haircuts y maintenance rules.

## Endpoints USER_DATA necesarios

Documentación Binance vigente:

### Spot

- `GET /api/v3/account/commission?symbol=BTCUSDT`
- `GET /api/v3/account/commission?symbol=ETHUSDT`

### USD-M Futures

- `GET /fapi/v1/commissionRate?symbol=BTCUSDT|ETHUSDT`
- `GET /fapi/v1/leverageBracket?symbol=BTCUSDT|ETHUSDT`
- `GET /fapi/v1/multiAssetsMargin`
- `GET /fapi/v1/accountConfig`

Todos son lectura USER_DATA. 04D-2 no implementa endpoints TRADE ni llamadas de cambio de modo.

## Seguridad

El cliente requiere simultáneamente:

- `ALLOW_04D2_ACCOUNT_READONLY=1`;
- `BINANCE_API_KEY`;
- `BINANCE_API_SECRET`.

Sin las tres condiciones, retorna `METADATA_CUENTA_NO_DISPONIBLE_04D2` **sin tocar red**.

GitHub CI debe mantener las tres variables vacías y solo ejecutar tests con credenciales sintéticas/mock. No se guardan ni se imprimen secretos.

## Qué se necesita extraer cuando exista una ejecución local autorizada

Por símbolo:

- maker/taker Spot efectivos;
- maker/taker USD-M efectivos;
- brackets de notional;
- initial leverage permitido;
- maintenance margin ratio/bracket;
- configuración de symbol/account relevante.

Por cuenta:

- Single-Asset vs Multi-Assets Mode;
- configuración Futures efectiva.

Si la cuenta utiliza Portfolio Margin en lugar de USD-M estándar, 04D-2 deberá ampliar el protocolo a los endpoints `papi` correspondientes antes de modelar collateral; no se mezclará semántica entre modos.

## Resultado esperado en CI

CI, sin secrets:

`METADATA_CUENTA_NO_DISPONIBLE_04D2`

Eso es el resultado correcto de seguridad y no un fallo.

## Gates posteriores

Solo si una ejecución local read-only obtiene metadata completa:

1. congelar el modo de margen que se modelará;
2. congelar fee schedule efectivo;
3. congelar haircuts/brackets aplicables;
4. reconstruir el buffer de liquidación del hedge 04C-2;
5. medir capital efectivo pico sobre 2022-2025 sin usar 2026;
6. recalcular **únicamente** retorno sobre capital efectivo, sin cambiar señales ni gates;
7. decidir si merece PAPER shadow.

## Candados

- solo GET;
- no órdenes;
- no cambio de leverage;
- no cambio de margin mode;
- no cambio Multi-Assets;
- no transferencias;
- no Render;
- no LIVE;
- no PAPER operativo;
- no 2026;
- no recalibración retrospectiva 04C-2.
