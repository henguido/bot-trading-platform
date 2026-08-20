# BOT 2.0-04B-v16 — Auditoría Futures Perpetual 1d

## Objetivo

Después de falsar `premiumIndex` como proxy económico en v15, v16 verifica la calidad del precio Futures USD-M perpetual real antes de calcular un basis Spot−Perp.

v16 no estima edge y no abre 2026.

## Fuente

- `data.binance.vision/data/futures/um/monthly/klines`
- contrato: símbolo USD-M perpetual estándar (`BTCUSDT`, `ETHUSDT`, etc.)
- intervalo: 1d
- periodo: 2022-01-01 a 2025-12-31
- universo: 20 activos del proyecto
- 960 archivos mensuales esperados

## Criterios predeclarados

- >=15 símbolos con cobertura individual >=95%;
- >=95% de días globales con >=15 símbolos;
- >=90% de días por año con >=15 símbolos;
- sin forward-fill ni datos inventados.

## Resultado real

GitHub Actions run `32411147914` sobre HEAD `cc9c0a059446eae0dcb6b46f889f62e74d24b21f`:

- `1042 passed`;
- `compileall` OK;
- frontend `841 modules transformed`;
- locks v16 OK, 2026 cerrado;
- 960/960 archivos válidos;
- 0 HTTP 404;
- 0 errores;
- 20/20 símbolos aptos;
- 1.456/1.461 días con >=15 símbolos;
- cobertura cross-sectional total `0.9965776865160848733744010951`.

Cobertura anual:

| Año | Días completos | Total | Fracción | Apto |
|---|---:|---:|---:|---|
| 2022 | 360 | 365 | 98,6301% | Sí |
| 2023 | 365 | 365 | 100% | Sí |
| 2024 | 366 | 366 | 100% | Sí |
| 2025 | 365 | 365 | 100% | Sí |

13 símbolos tienen 1.461/1.461 días. FIL, LTC, NEAR, SOL, TRX, XLM y XRP tienen 1.456 días, con dos gaps y máximo de 3 días; aun así cada uno conserva 99,6578% de cobertura.

## Conclusión

`DATASET_PERP_APTO_V16`.

La infraestructura permite calcular un **perpetual basis** más literal:

`basis_perp(t) = (SpotClose(t) - FuturesClose(t)) / FuturesClose(t)`

Esto no debe confundirse con el basis current-quarter de la literatura académica. El current-quarter histórico sí existe para BTC/ETH, pero no para suficiente parte del universo (por ejemplo BNBUSDT no acepta ese contract type), por lo que no es adecuado para nuestro análisis cross-sectional de 20 activos.

## Seguridad

- PAPER únicamente.
- 2026 cerrado.
- LIVE cerrado.
- Render sin cambios.
- `main` sin cambios.
