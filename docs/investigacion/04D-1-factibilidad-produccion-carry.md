# BOT 2.0 — 04D-1 Factibilidad pública de producción del carry 04C-2

## Estado

**AUDITORÍA READ-ONLY. No modifica la estrategia 04C-2, no envía órdenes y no autoriza producción.**

Resultado final: `docs/investigacion/04D-1-resultado.md`.

04C-2 demostró una prima económica en BTC/ETH long Spot + short USD-M perpetual durante 2022-2025, pero no superó su gate de producción conservador. 04C-3 no ofreció una alternativa de mejor eficiencia: 0/32 calendar spreads fueron elegibles bajo su protocolo congelado.

04D-1 deja de buscar edge. Su objetivo es identificar los blockers operativos reales del edge ya demostrado.

## Inputs congelados

- BTCUSDT y ETHUSDT.
- Notionals: $500 / $5,000 / $25,000 / $100,000.
- Budget all-in heredado de 04C-2: 60 bps.
- Gate de fricción visible round-trip: <=10 bps.
- Referencia estática separada: 1x Spot + 1x USDT margen Futures = 2x.
- Sin credenciales, órdenes, PAPER operativo, LIVE, Render ni retornos 2026.

## Resultado de liquidez

Snapshot público mediante libros Spot + USD-M, sin órdenes:

| Activo | $500 | $5k | $25k | $100k |
|---|---:|---:|---:|---:|
| BTCUSDT | 0.0142 bps | 0.0142 | 0.0528 | 0.1985 |
| ETHUSDT | 0.1888 bps | 0.5102 | 1.8500 | 3.4182 |

Máximo: **3.4182 bps < 10 bps**. La liquidez observable actual no es el blocker principal hasta $100k por activo.

GitHub Actions recibió HTTP 451 de `fapi.binance.com`; el snapshot final se obtuvo mediante las herramientas públicas conectadas de Binance y quedó fijado en `backend/economia/data/liquidity_snapshot_04d1.json`. Es un snapshot puntual, no una distribución histórica de slippage.

## Resultado de margen separado

Lower bound favorable, sin maintenance margin, fees ni mark/index basis:

| Activo/año | Excursión adversa | Capital total mínimo separado |
|---|---:|---:|
| BTC 2022 | 3.57% | 1.0357x |
| BTC 2023 | 167.96% | **2.6796x** |
| BTC 2024 | 154.15% | **2.5415x** |
| BTC 2025 | 34.11% | 1.3411x |
| ETH 2022 | 4.99% | 1.0499x |
| ETH 2023 | 104.22% | **2.0422x** |
| ETH 2024 | 79.49% | 1.7949x |
| ETH 2025 | 44.92% | 1.4492x |

La arquitectura estática separada 2x queda falsada por BTC 2023, BTC 2024 y ETH 2023.

## Matiz de collateral compartido

04D-1 no demuestra que toda arquitectura necesite >2x. Cross Margin, Multi-Assets Mode o Portfolio Margin pueden reconocer collateral compartido y compensaciones entre Spot y Futures, sujeto a maintenance margin, haircuts y reglas efectivas de la cuenta.

Por tanto 04D-2 sigue siendo necesario: no para cambiar el edge, sino para determinar si una arquitectura de collateral compartido puede sobrevivir al histórico con suficiente eficiencia de capital.

## Metadata que 04D-2 necesita

- fee tier real Spot y USD-M;
- leverage brackets y maintenance margin;
- collateral ratios/haircuts;
- Cross/Isolated/Multi-Assets/Portfolio Margin disponible;
- balances/collateral elegible;
- reglas de liquidation/top-up.

La conexión Binance disponible aquí expone market data público, no endpoints privados de cuenta. No se inventarán valores ni se introducirán secretos en CI.

## Veredicto

- `EJECUCION_PUBLICA_APTA_SNAPSHOT_04D1`.
- `MARGEN_ESTATICO_2X_INSUFICIENTE_04D1`.
- `PRODUCCION_NO_AUTORIZADA_04D1`.

Siguiente gate: **04D-2 collateral/margin architecture read-only**.
