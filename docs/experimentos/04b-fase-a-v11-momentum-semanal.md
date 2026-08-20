# BOT 2.0-04B-v11 — Momentum semanal 1–3 semanas

## Estado

**Resultado: `SIN_FACTORES_PROMETEDORES_V11`.**

2026 permaneció cerrado. No se modificó `main`, trading productivo, RiskEngine,
EconomicGate, LIVE ni Render.

## Protocolo predeclarado

- Dataset descargado: 2022-01-01 a 2025-12-31, velas Spot 4h.
- Clasificación: únicamente timestamps semanales de 2025.
- Rebalanceo: cierre del domingo, límite lunes 00:00 UTC.
- Horizonte futuro: 7 días / 168h.
- Hurdle económico: 25 bps por operación round-trip.
- Universo: 20 pares USDT versionados previamente.
- Factores: MOM1, MOM2, MOM3, RMOM1, RMOM2 y RMOM3.
- Dirección probada: solo ALTA.
- RMOM: media de retornos diarios / desviación estándar muestral diaria, rf=0.

## Validación técnica

CI run `32395599155`, HEAD `76376a0352c2b1dd2eb9a1a108cbfd7138d8d6ea`:

- 1001 tests passed.
- `python -m compileall backend`: OK.
- frontend build: OK, 841 módulos.
- locks v11: `DESARROLLO_2026_ABIERTO_V11=False` y `TEST_MAY_JUL_ABIERTO_V11=False`.
- 20/20 símbolos útiles.
- 4.100 observaciones semanales históricas construidas.
- 51 timestamps de decisión en 2025.

La API primaria de Binance quedó restringida por ubicación en el runner; el
fallback público market-data-only `data-api.binance.vision` completó las 20
series con 8.766 velas cada una.

## Resultados 2025

| Factor | IC medio | Spread alto-bajo (bps) | Semanas spread + | Top-1 neto medio (bps) | Hit-rate top-1 | Meses top-1 + | Folds top-1 + |
|---|---:|---:|---:|---:|---:|---:|---:|
| MOM1 | 0,0321 | 91,32 | 49,02% | **+3,71** | 39,22% | 5/12 | 2/4 |
| MOM2 | 0,0307 | 81,34 | 47,06% | -147,58 | 47,06% | 6/12 | 2/4 |
| MOM3 | 0,0170 | 30,51 | 50,98% | -116,58 | 45,10% | 6/12 | 2/4 |
| RMOM1 | 0,0550 | 129,26 | 54,90% | -191,30 | 33,33% | 5/12 | 1/4 |
| RMOM2 | 0,0215 | 57,56 | 52,94% | -172,86 | 43,14% | 6/12 | 2/4 |
| RMOM3 | 0,0155 | 43,21 | **54,90%** | **+29,93** | **50,98%** | **9/12** | **3/4** |

Ningún factor cumplió simultáneamente spread y top-1.

## Hallazgo que sí merece réplica

RMOM3 fue el único factor que combinó retorno top-1 neto positivo, 9/12 meses y
3/4 folds positivos. No se promueve: falló los dos umbrales de frecuencia que
estaban congelados antes del resultado:

- fracción de semanas con spread positivo: `54,90% < 55%`;
- hit-rate top-1 neto positivo: `50,98% < 55%`.

No se redondea 54,90% a 55% y no se rebajan thresholds después de observar los
datos.

## Siguiente prueba permitida

Una sola réplica histórica de RMOM3 en 2022, 2023 y 2024, por año, manteniendo:

- definición RMOM3 intacta;
- dirección ALTA;
- horizonte semanal;
- hurdle 25 bps;
- mismos umbrales de promoción.

La réplica no se tratará como holdout final del proyecto. Su único objetivo es
comprobar si el casi-resultado de 2025 se repite temporalmente antes de decidir
si RMOM3 merece una validación futura realmente fuera de muestra.
