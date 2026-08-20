# BOT 2.0-04B-v14 — Auditoría histórica de derivados

## Objetivo

Verificar, antes de diseñar una señal económica nueva, que el `premiumIndex` diario de Binance USD-M sea históricamente reproducible y suficientemente completo para el universo Spot de 20 activos usado por el proyecto.

v14 **no estima edge**, no autoriza operaciones y no abre 2026.

## Fuente y periodo

- Fuente: `data.binance.vision/data/futures/um/monthly/premiumIndexKlines`
- Intervalo: `1d`
- Periodo: 2022-01-01 a 2025-12-31
- Universo: 20 símbolos USDT versionados previamente
- Tareas mensuales esperadas: 20 × 48 = 960

## Reglas de integridad predeclaradas

Cada ZIP/CSV se valida antes de agregarse:

- un único archivo por ZIP;
- timestamps diarios alineados a medianoche UTC;
- timestamps en milisegundos o microsegundos normalizados defensivamente;
- ausencia de duplicados;
- OHLC finito y coherente;
- sin interpolación, forward-fill ni ceros inventados.

El dataset solo se considera apto si:

- al menos 15 símbolos tienen cobertura individual >= 95%;
- al menos 95% de los días del periodo tienen >= 15 símbolos contemporáneos;
- cada año tiene al menos 90% de sus días con >= 15 símbolos.

## Resultado real

GitHub Actions run `32401719194` sobre HEAD `71aeebfc1f5c58ce4d162b32476f0603f06ad2c1` terminó completamente en verde.

Checkpoint técnico:

- `1020 passed`;
- `compileall` OK;
- frontend build OK (`841 modules transformed`);
- `DESARROLLO_2026_ABIERTO_V14=False`;
- `TEST_MAY_JUL_ABIERTO_V14=False`.

Auditoría real:

- 960/960 archivos mensuales válidos;
- 0 HTTP 404;
- 0 errores;
- 20/20 símbolos aptos;
- 1.459 de 1.461 días con cross-section >= 15 símbolos;
- cobertura cross-sectional total: `0.9986310746064339493497604381`;
- ningún gap individual supera 1 día.

Cobertura por año:

| Año | Días cross-section completa | Días calendario | Fracción | Apto |
|---|---:|---:|---:|---|
| 2022 | 364 | 365 | 99,7260% | Sí |
| 2023 | 364 | 365 | 99,7260% | Sí |
| 2024 | 366 | 366 | 100% | Sí |
| 2025 | 365 | 365 | 100% | Sí |

Los 20 símbolos muestran coberturas individuales entre 99,8631% y 99,9316%.

## Conclusión

`DATASET_DERIVADOS_APTO_V14`.

v14 habilita investigación económica posterior con `premiumIndex`; **no demuestra rentabilidad** y no convierte el premium en expected edge.

La siguiente fase debe mantener separadas estas dos preguntas:

1. ¿el `premiumIndex` contiene información predictiva cross-sectional sobre retornos Spot futuros?;
2. si la contiene, ¿esa información sobrevive costes, estabilidad temporal y comparación contra un benchmark contemporáneo?

## Seguridad

- PAPER únicamente.
- 2026 cerrado.
- LIVE cerrado.
- Render sin cambios.
- `main` sin cambios.
