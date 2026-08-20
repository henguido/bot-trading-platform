# BOT 2.0 — 04B-v20: auditoría de datos de posicionamiento USD-M

## Estado

**NO APTO bajo el protocolo estricto v20**, exclusivamente por orden temporal físico de filas.

v20 no evaluó retornos ni una hipótesis económica. Su único objetivo fue determinar si el archivo histórico público `metrics` de Binance Vision era suficientemente reproducible para investigar open interest y posicionamiento sin inventar datos.

## Protocolo predeclarado

- universo: 20 símbolos de `UNIVERSO_VALIDACION_V2`;
- periodo: 2022-01-01 .. 2025-12-31;
- cobertura: listado S3 completo de archivos diarios;
- contenido: un archivo mediano determinístico por símbolo/mes, sin mirar previamente su contenido;
- objetivo de contenido: 960 muestras (20 símbolos × 48 meses);
- no rellenar huecos, NaN ni ceros;
- core OI evaluado separadamente de ratios opcionales;
- cualquier timestamp no ascendente en las muestras rechazaba v20;
- 2026 y holdout final cerrados.

## Ejecución reproducida

CI #77, commit `917ea80f20f2259541f16fb12f764aa10e48a5ab`:

- 1096 tests passed;
- `compileall` backend: OK;
- frontend: 841 módulos transformados;
- listados S3: 20/20 completos;
- archivos diarios listados: 29,218;
- muestras parseadas: 941/960 = 98.02%;
- filas inspeccionadas en muestras válidas: 271,008;
- cadencia de deltas válidos: 100% a 5 minutos;
- duplicados en las muestras válidas: 0;
- timestamps no ascendentes en orden físico de CSV: 756;
- cross-section global: 100%;
- 2022: 365/365 días con >=15 símbolos;
- 2023: 365/365;
- 2024: 366/366;
- 2025: 365/365.

Dos símbolos tienen un único archivo diario ausente en el periodo y siguen muy por encima del umbral de cobertura:

- XLMUSDT: 1460/1461 días, 99.9316%;
- NEARUSDT: 1460/1461 días, 99.9316%.

## Calidad por campo

| Campo | Fracción válida | Fracción positiva | Usable según v20 |
|---|---:|---:|---|
| `sum_open_interest` | 100% | 100% | Sí |
| `sum_open_interest_value` | 100% | 100% | Sí |
| `count_toptrader_long_short_ratio` | 78.7460% | 78.7460% | No |
| `sum_toptrader_long_short_ratio` | 78.7460% | 78.7460% | No |
| `count_long_short_ratio` | 97.8746% | 97.8746% | Sí |
| `sum_taker_long_short_vol_ratio` | 91.4848% | 91.4781% | Sí |

Por tanto, la disponibilidad de datos descarta de futuras pruebas los dos ratios `toptrader`, pero deja técnicamente prometedores como variables históricas:

1. `sum_open_interest`;
2. `sum_open_interest_value`;
3. `count_long_short_ratio`;
4. `sum_taker_long_short_vol_ratio`.

Esta selección se basa exclusivamente en disponibilidad/calidad, no en retornos.

## Anomalías observadas

El único motivo de rechazo global de v20 fue:

`TIMESTAMPS_NO_ASCENDENTES_EN_MUESTRA`

Se observaron 756 inversiones de orden físico, sin timestamps duplicados en las muestras válidas. Ordenar esas filas habría hecho desaparecer ese defecto de representación, pero v20 había predeclarado que cualquier no-ascendencia era motivo de rechazo; por tanto no se modifica retroactivamente.

Adicionalmente, 19/20 símbolos fallaron exactamente en la muestra `2024-04-16` porque al menos una fila contenía `create_time` fuera de la fecha nominal del archivo. Es una anomalía transversal del archivo. El archivo no se recortó ni se rellenó; fue rechazado completo.

La existencia de defectos de continuidad en `metrics` también ha sido reportada públicamente contra objetos y checksums oficiales de Binance Vision. Referencias:

- https://github.com/binance/binance-public-data/issues/484
- https://github.com/binance/binance-public-data/issues/287

## Decisión

v20 conserva su resultado `DATASET_POSICIONAMIENTO_NO_APTO_V20`; no se cambia el protocolo después de observar los datos.

La siguiente pieza será **v20.1**, todavía sin retornos, con una política de normalización predeclarada:

- el orden físico de filas no tendrá significado económico;
- se ordenará canónicamente por `create_time` antes del análisis;
- los timestamps deberán seguir siendo únicos;
- cualquier archivo con duplicados se descartará completo;
- cualquier archivo con timestamps UTC fuera de su fecha nominal se descartará completo;
- no se imputarán snapshots ni ratios;
- se conservarán los mismos umbrales de cobertura, parseo, cadencia y calidad de campos de v20.

Solo si v20.1 demuestra que el core normalizado es reproducible se podrá diseñar una hipótesis v21. Ningún resultado de precios o retornos se utilizará para decidir esta normalización.

## Seguridad

v20 fue exclusivamente investigación offline. No modificó scanner productivo, Expected Edge, RiskEngine, sizing, PAPER/LIVE, Render ni GPT.
