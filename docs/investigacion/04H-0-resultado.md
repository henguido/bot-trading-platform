# BOT 2.0 — Resultado 04H-0 Funding Cross-Venue Binance / Hyperliquid

## Veredicto

`DATASET_CROSSVENUE_FUNDING_APTO_04H0`

La infraestructura pública 2024-2025 es suficiente para diseñar una hipótesis económica cross-venue predeclarada. Este resultado **no demuestra rentabilidad**: 04H-0 no calculó funding spread, normalización económica, retorno, Sharpe ni PnL.

## Ejecución

- branch: `agent/bot-2.0-04h0-crossvenue-funding-audit`
- HEAD ejecutado: `3ff77799d7b08891ce08bda7af62b28d6a84d91e`
- workflow `research-04h0` run #1: success
- CI general #153: success
- locks: success
- tests: 4/4
- artifact: `crossvenue-funding-audit-04h0`
- artifact ID: `9475140850`
- SHA256 ZIP: `379addbf38a754c68fe8e4c8cb23417ddcb0ba3868aa2e668e3e43304d000284`
- tamaño: 1.067 bytes

## Universo

Candidatos predeclarados: BTC, ETH, SOL, XRP, BNB.

Los cinco aparecen en el universo actual de Hyperliquid y tienen equivalente Binance USDT. Los activos obligatorios del gate fueron BTC, ETH y SOL.

## Hyperliquid 2024-2025

### Funding horario

Cada activo obligatorio:

- BTC: 17.543 registros / 17.544 slots esperados; cobertura 99,9943%; 0 duplicados; 0 inválidos.
- ETH: 17.543 / 17.544; cobertura 99,9943%; 0 duplicados; 0 inválidos.
- SOL: 17.543 / 17.544; cobertura 99,9943%; 0 duplicados; 0 inválidos.

### Perpetual candles 8h

Cada activo obligatorio:

- BTC: 2.193/2.193 barras, cobertura 100%; 0 duplicados; 0 inválidos.
- ETH: 2.193/2.193, cobertura 100%; 0 duplicados; 0 inválidos.
- SOL: 2.193/2.193, cobertura 100%; 0 duplicados; 0 inválidos.

## Binance Vision 2024-2025

Para BTCUSDT, ETHUSDT y SOLUSDT:

- fundingRate: 24/24 meses válidos por activo; 2.193 settlements por activo.
- perpetual klines 8h: 24/24 meses válidos por activo; 2.193 barras por activo.
- sin motivos de rechazo de cobertura/integridad.

## Qué NO se hizo

- no se restó funding Hyperliquid menos Binance;
- no se anualizó ni armonizó funding entre venues;
- no se midió basis cross-venue;
- no se calculó retorno o PnL;
- no se seleccionó BTC/ETH/SOL por rendimiento;
- no se imputó el slot horario faltante;
- no se usaron credenciales;
- no PAPER operativo, LIVE ni Render;
- 2026 cerrado.

## Limitaciones para 04H-1

La suficiencia histórica no equivale a ejecutabilidad productiva. Antes del PnL, 04H-1 debe fijar de forma conservadora:

1. orientación de la posición basada en literatura, no en nuestros resultados;
2. regla exacta de acumulación/alineación de funding horario Hyperliquid y settlements reales Binance;
3. fees de entrada/salida de ambas patas sin asumir VIP histórico favorable;
4. basis cross-venue y su cambio durante la posición;
5. slippage;
6. capital separado por venue y leverage fijo;
7. buffer de liquidación/stress, reconociendo que candles 8h no son mark-price histórico completo;
8. gates económicos y productivos antes de observar PnL.

04H-0 autoriza únicamente diseñar 04H-1 bajo esos candados.
