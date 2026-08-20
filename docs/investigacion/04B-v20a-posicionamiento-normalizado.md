# BOT 2.0 — 04B-v20.1 Posicionamiento histórico normalizado

## Objetivo

Validar si el histórico público USD-M `daily/metrics` de Binance Vision puede utilizarse de forma reproducible entre 2022-01-01 y 2025-12-31 después del hallazgo estricto de v20: algunos CSV contienen filas físicamente fuera de orden aunque `create_time` sea válido.

v20.1 no estima retornos, no busca edge, no formula una señal y no autoriza operaciones. 2026 permanece cerrado.

## Regla predeclarada

- `create_time` es la autoridad temporal.
- Se permite ordenar canónicamente las filas por `create_time` antes de medir cadencia.
- Timestamps duplicados: fail-closed.
- Timestamps UTC fuera de la fecha nominal del archivo: fail-closed.
- Payload/ZIP/CSV inválido: fail-closed.
- No se imputan huecos, NaN, ratios ni ceros.
- Se conservan exactamente los umbrales de cobertura/calidad de v20.

## Resultado CI

Ejecución CI #79, commit `c6a6750914b01326147dae146e06284a08efa9ed`:

- Estado: `DATASET_POSICIONAMIENTO_APTO_V20A`.
- Motivos de rechazo: ninguno.
- Tests: 1099 passed, 1391 warnings.
- `compileall`: OK.
- Frontend: build OK, 841 módulos transformados.
- 2026 cerrado y sin imputación: locks OK.
- Listados completos: 20/20 símbolos.
- Archivos históricos listados: 29,218.
- Muestras parseadas: 941/960 (98.02%).
- Filas inspeccionadas: 271,008.
- Cadencia de 5 minutos: 100% en muestras válidas.
- Filas que requirieron reorden canónico: 756.
- Duplicados: 0.

### Campos utilizables

- `sum_open_interest`: válido 100%, positivo 100%, usable.
- `sum_open_interest_value`: válido 100%, positivo 100%, usable.
- `count_long_short_ratio`: válido 97.8746%, usable.
- `sum_taker_long_short_vol_ratio`: válido 91.4848%, usable.

### Campos descartados por disponibilidad

- `count_toptrader_long_short_ratio`: válido 78.7460%, no usable.
- `sum_toptrader_long_short_ratio`: válido 78.7460%, no usable.

## Interpretación

v20 estricto queda correctamente falsado por el orden físico de filas. v20.1 demuestra que esa anomalía es normalizable de manera explícita y reproducible usando `create_time`, sin imputar información ni relajar los umbrales de calidad.

La aprobación de v20.1 solo autoriza usar los cuatro campos declarados como fuentes candidatas para investigación económica posterior. No implica predictibilidad ni rentabilidad.

## Siguiente gate

Diseñar una única hipótesis v21 antes de observar retornos, con hurdle económico de 25 bps y estabilidad temporal predeclarada. No abrir 2026, no integrar scanner/RiskEngine y no tocar PAPER/LIVE/Render/GPT.