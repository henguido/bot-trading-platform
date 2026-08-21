# BOT 2.0 — 04D-1 resultado: factibilidad pública del carry 04C-2

## Veredicto

- Liquidez snapshot: `EJECUCION_PUBLICA_APTA_SNAPSHOT_04D1`.
- Margen estático separado 2x: `MARGEN_ESTATICO_2X_INSUFICIENTE_04D1`.
- Producción: `PRODUCCION_NO_AUTORIZADA_04D1`.

04D-1 no cambia el veredicto económico de 04C-2. Su objetivo fue identificar blockers de ejecución y capital antes de cualquier PAPER operativo o LIVE.

## Liquidez pública

Se congelaron ex ante notionals de USD 500, 5,000, 25,000 y 100,000 por activo. Se simuló un round-trip en el mismo snapshot público: compra Spot + venta USD-M y cierre inverso, sin enviar órdenes.

Fricción estimada del libro, en bps:

| Activo | $500 | $5k | $25k | $100k |
|---|---:|---:|---:|---:|
| BTCUSDT | 0.0142 | 0.0142 | 0.0528 | 0.1985 |
| ETHUSDT | 0.1888 | 0.5102 | 1.8500 | 3.4182 |

Máximo observado: **3.4182 bps**, por debajo del gate congelado de **10 bps**. La profundidad observable actual de BTC/ETH no es el blocker principal en estas escalas.

Limitación: es un snapshot puntual, no una distribución histórica de slippage. El runner de GitHub pudo usar el host público alternativo de Spot, pero `fapi.binance.com` respondió HTTP 451 por geofencing. El snapshot final se obtuvo mediante las herramientas públicas conectadas de Binance y quedó fijado en `backend/economia/data/liquidity_snapshot_04d1.json`.

## Stress histórico de margen

Lower bound para una arquitectura **separada** long Spot + short Futures, sin reconocer el Spot como collateral del short y sin maintenance margin, fees ni mark/index basis:

| Activo/año | Excursión adversa mark | Capital total mínimo lower-bound separado |
|---|---:|---:|
| BTC 2022 | 3.57% | 1.0357x |
| BTC 2023 | 167.96% | **2.6796x** |
| BTC 2024 | 154.15% | **2.5415x** |
| BTC 2025 | 34.11% | 1.3411x |
| ETH 2022 | 4.99% | 1.0499x |
| ETH 2023 | 104.22% | **2.0422x** |
| ETH 2024 | 79.49% | 1.7949x |
| ETH 2025 | 44.92% | 1.4492x |

La referencia simplificada de 2x (1x Spot + 1x margen Futures separado) queda falsada como arquitectura estática segura por BTC 2023, BTC 2024 y ETH 2023.

## Implicación correcta

04C-2 ya fallaba el gate de producción bajo la referencia 2x committed:

- media anual committed: 4.6882% < 5%;
- peor año committed: 0.6207% < 2%.

Pero 04D-1 **no demuestra** que toda arquitectura de capital deba requerir >2x. Cross Margin, Multi-Assets Mode o Portfolio Margin pueden reconocer collateral compartido y compensaciones económicas entre la pata Spot y la pata short Futures, sujeto a haircuts, maintenance margin y reglas de la cuenta.

Por tanto la conclusión válida es más limitada y más útil: **la arquitectura estática separada 2x no sirve**, pero una arquitectura de collateral compartido todavía debe auditarse antes de cerrar definitivamente la viabilidad productiva del edge.

No se permite usar esta observación para añadir leverage especulativo ni para cambiar los gates económicos de 04C-2.

## Metadata todavía necesaria para 04D-2

- fee tier real Spot y USD-M;
- leverage brackets y maintenance margin;
- collateral ratios/haircuts de Multi-Assets/Portfolio Margin;
- margin mode disponible;
- balances/collateral elegible;
- reglas efectivas de liquidation y top-up.

La conexión Binance disponible en este entorno expone market data público, no endpoints privados de cuenta para esos campos. La documentación vigente de Binance separa market-data público de account/trade endpoints firmados; 04D-2 deberá mantenerse read-only y nunca introducir credenciales reales en CI.

## Cierre

`04C-2`: edge económico demostrado, todavía **no candidato a producción**.

`04D-1`: liquidez pública suficiente en el snapshot hasta $100k; **la arquitectura de margen separado es el blocker demostrado**.

Siguiente gate: 04D-2, collateral/margin architecture read-only.

No se habilita PAPER operativo, LIVE ni Render. No se abre 2026. No se recalibran gates de 04C-2.
