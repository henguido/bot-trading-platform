# BOT 2.0 — 04B-v21 OI + taker flow -> Spot 8h

## Hipótesis predeclarada

Después de que v20.1 validó la disponibilidad histórica de `sum_open_interest` y `sum_taker_long_short_vol_ratio`, v21 probó una sola hipótesis económica antes de observar retornos:

> Presión compradora agresiva elevada en futuros USD-M durante las 8h previas, confirmada por crecimiento de open interest, anticipa retorno Spot positivo durante las 8h siguientes.

Regla fija:

- universo: 20 símbolos versionados;
- periodo de desarrollo: 2022-01-01 a 2025-12-31;
- 2026 cerrado;
- ventanas de features no solapadas: `[00,08)`, `[08,16)`, `[16,24)` UTC;
- mínimo 90% de los 96 snapshots 5m esperados;
- `presion_taker`: media geométrica de `sum_taker_long_short_vol_ratio` positivo y válido;
- `cambio_oi`: último `sum_open_interest` / primero - 1;
- mínimo 15 activos por timestamp;
- selección: top 25% cross-sectional por presión taker;
- dentro de ese top, señal solo si `cambio_oi > 0`;
- un activo top con OI no positivo se elimina y no se reemplaza por el siguiente del ranking;
- entrada Spot `open(T)`, salida `open(T+8h)`;
- hurdle económico: 25 bps = 20 bps round-trip + 5 bps de margen;
- benchmark: equal-weight del mismo cross-section y timestamp;
- no price momentum, funding, basis, `count_long_short_ratio` ni GPT;
- no imputación;
- si falla, no se invierte el signo ni se ajustan umbrales dentro de v21.

## Gate de datos

Antes de emitir un veredicto económico se exigió:

- inventario completo del archivo para los 20 símbolos;
- al menos 95% de los ZIP diarios descargados/parseados correctamente;
- al menos 15 símbolos Spot completos.

Resultado:

- listados: 20/20;
- archivos objetivo: 29,218;
- archivos metrics completos: 28,724/29,218 = 98.3093%;
- features válidas: 78,350;
- Spot: 20/20 símbolos completos;
- etiquetas Spot 8h: 87,660.

Por tanto el gate de datos pasó y el resultado sí permite una falsación económica.

## Validación técnica

HEAD de investigación: `a4ef260e41f1f5a6d8a036fe62253f6c35ed8908`.

CI general #81:

- 1109 tests passed;
- 1391 warnings;
- `compileall` OK;
- frontend build OK, 841 módulos transformados;
- reauditoría v20.1 volvió a resultar `DATASET_POSICIONAMIENTO_APTO_V20A`.

Workflow aislado `research-04b` #69:

- locks v21 OK;
- credenciales Binance vacías;
- PAPER;
- diagnóstico completado y artifact generado.

## Resultado económico

Estado: `SENAL_OI_TAKER_FALSADA_V21`.

Métricas globales:

- timestamps con señal: 3,718;
- meses con señal: 45;
- años con señal: 4;
- retorno bruto medio: **+6.5704 bps**;
- retorno neto medio después del hurdle: **-18.4296 bps**;
- baseline equal-weight contemporáneo: **+3.1038 bps**;
- uplift medio frente al baseline: **+3.4666 bps**;
- fracción de timestamps neto-positivos: **43.7063%**;
- meses neto-positivos: **7/45**;
- años neto-positivos: **0/4**;
- años con uplift positivo: **3/4**.

### Por año

| Año | Timestamps | Neto medio | Uplift vs baseline | Neto positivo |
|---|---:|---:|---:|---|
| 2022 | 663 | -28.0933 bps | +0.9706 bps | No |
| 2023 | 1,033 | -13.2766 bps | +4.8676 bps | No |
| 2024 | 975 | -6.3988 bps | +8.0249 bps | No |
| 2025 | 1,047 | -28.5979 bps | -0.5800 bps | No |

Motivos de rechazo predeclarados activados:

- `MEDIA_NETA_NO_POSITIVA`;
- `FRACCION_TIMESTAMPS_NETO_POSITIVO_INSUFICIENTE`;
- `MESES_NETO_POSITIVO_INSUFICIENTES`;
- `ANIOS_NETO_POSITIVO_INSUFICIENTES`.

## Interpretación

La combinación top-quartile taker pressure + OI creciente contiene una pequeña señal relativa: el portfolio seleccionado superó en promedio al equal-weight por ~3.47 bps y ese uplift fue positivo en 3 de 4 años. Sin embargo, el efecto absoluto es demasiado pequeño para superar el hurdle económico de 25 bps. Incluso el mejor año, 2024, quedó en -6.40 bps netos medios; 2025 perdió además el uplift relativo.

Por tanto v21 no justifica integración con scanner, EconomicGate, RiskEngine ni PAPER. Tampoco justifica ajustar retrospectivamente el percentil, el filtro de OI, el horizonte o el signo.

## Conclusión

v21 queda falsada en desarrollo 2022-2025. El resultado sugiere que el flujo/posicionamiento puede aportar información como factor auxiliar, pero no funciona por sí solo con esta regla simple como generador long Spot económicamente suficiente.

El siguiente experimento, si se continúa, debe formular una hipótesis materialmente distinta y predeclarada; no debe ser una búsqueda de umbral dentro de la familia v21.

## Seguridad

- 2026 cerrado;
- mayo-julio 2026 cerrado;
- PAPER sin integración;
- LIVE cerrado;
- Render sin cambios;
- GPT no usado para señal;
- `main` sin cambios.