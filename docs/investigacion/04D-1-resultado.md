# BOT 2.0 — 04D-1 resultado: factibilidad pública del carry 04C-2

## Veredicto

- Liquidez snapshot: `EJECUCION_PUBLICA_APTA_SNAPSHOT_04D1`.
- Margen estático 2x: `MARGEN_ESTATICO_2X_INSUFICIENTE_04D1`.
- Producción: `PRODUCCION_NO_AUTORIZADA_04D1`.

04D-1 no cambia el veredicto económico de 04C-2. Su objetivo fue identificar blockers de ejecución y capital antes de cualquier PAPER operativo o LIVE.

## Liquidez pública

Se congelaron ex ante notionals de USD 500, 5,000, 25,000 y 100,000 por activo. Se simuló un round-trip en el mismo snapshot público: compra Spot + venta USD-M y cierre inverso, sin enviar órdenes.

Fricción estimada del libro, en bps:

| Activo | $500 | $5k | $25k | $100k |
|---|---:|---:|---:|---:|
| BTCUSDT | 0.0142 | 0.0142 | 0.0528 | 0.1985 |
| ETHUSDT | 0.1888 | 0.5102 | 1.8500 | 3.4182 |

Máximo observado: **3.4182 bps**, por debajo del gate congelado de **10 bps**. Por tanto la profundidad observable actual de BTC/ETH no es el blocker principal en estas escalas.

Limitación: es un snapshot puntual, no una distribución histórica de slippage. El runner de GitHub pudo usar el host público alternativo de Spot, pero `fapi.binance.com` respondió HTTP 451 por geofencing. El snapshot final se obtuvo mediante las herramientas públicas conectadas de Binance y quedó fijado en `backend/economia/data/liquidity_snapshot_04d1.json`.

## Stress histórico de margen

Lower bound deliberadamente favorable, sin maintenance margin, fees ni mark/index basis:

| Activo/año | Excursión adversa mark | Capital total mínimo lower-bound |
|---|---:|---:|
| BTC 2022 | 3.57% | 1.0357x |
| BTC 2023 | 167.96% | **2.6796x** |
| BTC 2024 | 154.15% | **2.5415x** |
| BTC 2025 | 34.11% | 1.3411x |
| ETH 2022 | 4.99% | 1.0499x |
| ETH 2023 | 104.22% | **2.0422x** |
| ETH 2024 | 79.49% | 1.7949x |
| ETH 2025 | 44.92% | 1.4492x |

La referencia 04C-2 de 2x capital (1x Spot + 1x margen Futures) queda falsada como arquitectura estática segura por BTC 2023, BTC 2024 y ETH 2023.

## Implicación económica decisiva

04C-2 ya fallaba el gate de producción con 2x de capital committed:

- media anual committed: 4.6882% < 5%;
- peor año committed: 0.6207% < 2%.

El lower bound histórico demuestra que en algunos episodios el capital de riesgo necesario es **mayor que 2x**. Si el denominador de capital aumenta para mantener el hedge vivo, la rentabilidad sobre capital committed solo empeora. Por tanto, sin cambiar los gates de producción ni usar leverage adicional, obtener maintenance brackets exactos no puede convertir retrospectivamente 04C-2 en candidato de producción.

Esto no falsifica la prima económica. Falsifica el paso directo de esa prima a producción bajo los gates actuales y una arquitectura prudente de capital.

## Metadata todavía no disponible

Para un diseño futuro más preciso siguen siendo útiles, pero ya no son necesarias para decidir que 04C-2 no pasa producción bajo el protocolo actual:

- fee tier real Spot y USD-M;
- leverage brackets y maintenance margin;
- collateral ratios/haircuts de Multi-Assets/Portfolio Margin;
- margin mode y capacidad real de top-up.

La conexión Binance disponible en este entorno expone market data público, no endpoints privados de cuenta para esos campos. No se introducirán credenciales reales en CI ni se inventarán valores.

## Cierre

`04C-2`: edge económico demostrado, **no candidato a producción**.

`04D-1`: liquidez pública suficiente en el snapshot hasta $100k, pero **capital/margen es el blocker estructural**.

No se habilita PAPER operativo, LIVE ni Render. No se abre 2026. No se recalibran gates de 04C-2.
