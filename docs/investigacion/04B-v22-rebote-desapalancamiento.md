# BOT 2.0 — 04B-v22 rebote por desapalancamiento -> Spot 8h

## Hipótesis predeclarada

Después de que v21 falsó la continuación simple basada en presión taker compradora + open interest creciente, v22 formuló una hipótesis materialmente distinta, orientada a cascadas de venta/desapalancamiento:

> Una caída Spot relativa fuerte durante las 8h previas, acompañada por contracción de open interest y predominio de venta taker, puede anticipar un rebote Spot durante las 8h siguientes.

Regla fija:

- universo: 20 símbolos versionados;
- periodo de desarrollo: 2022-01-01 a 2025-12-31;
- 2026 cerrado;
- mayo-julio 2026 cerrado;
- ventanas de señal en T = 00:00, 08:00 y 16:00 UTC;
- retorno Spot previo: `open(T) / open(T-8h) - 1`;
- retorno Spot futuro: `open(T+8h) / open(T) - 1`;
- mínimo 15 activos por timestamp;
- shock de precio: bottom 25% cross-sectional del retorno Spot previo 8h;
- confirmación 1: `cambio_oi < 0`;
- confirmación 2: media geométrica de `sum_taker_long_short_vol_ratio < 1`;
- un candidato bottom-quartile que no confirma OI+taker se elimina y no se reemplaza;
- entrada Spot `open(T)`, salida `open(T+8h)`;
- hurdle económico: 25 bps = 20 bps round-trip + 5 bps de margen;
- benchmark 1: equal-weight contemporáneo de todo el cross-section;
- benchmark 2: simple bottom-quartile de retorno previo, sin filtros OI/taker;
- para aprobar, la señal debe ser neto-positiva y agregar valor frente a ambos controles;
- no funding, basis, top-trader ratio ni GPT;
- no imputación;
- si falla, no se invierte el signo ni se ajustan retrospectivamente percentil, OI, taker u horizonte.

## Gate de datos

Antes de emitir un veredicto económico se exigió:

- inventario completo para los 20 símbolos;
- al menos 95% de archivos diarios de métricas completos;
- al menos 15 símbolos Spot completos;
- sin imputación de huecos.

Resultado:

- listados: 20/20;
- archivos objetivo: 29,218;
- archivos metrics completos: 28,724/29,218 = 98.3093%;
- features válidas: 78,350;
- Spot: 20/20 símbolos completos;
- etiquetas Spot 8h: 87,660.

El gate de transporte pasó, por lo que el resultado permite una falsación económica.

## Validación técnica

HEAD de implementación evaluada: `1c73fcd46651beac3557e441e41f8ab0ef730c6b`.

CI general #83:

- 1114 tests passed;
- 1391 warnings;
- `compileall backend` OK;
- frontend build OK, 841 módulos transformados;
- reauditoría v20.1 volvió a resultar `DATASET_POSICIONAMIENTO_APTO_V20A`;
- `TRADING_MODE=PAPER`;
- `ALLOW_LIVE_TRADING` vacío.

Workflow aislado `research-04b` #71:

- job `deleveraging-v22` OK;
- locks metodológicos v22 OK;
- credenciales Binance vacías;
- diagnóstico offline completado;
- artifact `desapalancamiento-v22-desarrollo-2022-2025` generado.

## Resultado económico

Estado: `REBOTE_DESAPALANCAMIENTO_FALSADO_V22`.

Métricas globales:

- timestamps con señal: 3,403;
- meses con señal: 45;
- años con señal: 4;
- caída Spot previa media de los seleccionados: **-143.0539 bps**;
- retorno bruto medio posterior: **+4.5381 bps**;
- retorno neto medio después del hurdle: **-20.4619 bps**;
- baseline equal-weight contemporáneo: **+4.9812 bps**;
- baseline bottom-quartile price-only: **+3.7870 bps**;
- uplift medio frente al universo: **-0.4431 bps**;
- uplift medio frente a price-only: **+0.7511 bps**;
- fracción de timestamps neto-positivos: **44.1669%**;
- meses neto-positivos: **8/45**;
- años neto-positivos: **0/4**;
- años con uplift positivo vs universo: **2/4**;
- años con uplift positivo vs price-only: **2/4**.

### Por año

| Año | Timestamps | Neto medio | Uplift vs universo | Uplift vs price-only | Neto positivo |
|---|---:|---:|---:|---:|---|
| 2022 | 621 | -22.2400 bps | +10.0151 bps | +5.2139 bps | No |
| 2023 | 948 | -17.4654 bps | -2.0640 bps | -2.1876 bps | No |
| 2024 | 867 | -21.1848 bps | -6.8500 bps | -0.5151 bps | No |
| 2025 | 967 | -21.6094 bps | +0.1741 bps | +1.9014 bps | No |

Motivos de rechazo predeclarados activados:

- `MEDIA_NETA_NO_POSITIVA`;
- `FRACCION_TIMESTAMPS_NETO_POSITIVO_INSUFICIENTE`;
- `MESES_NETO_POSITIVO_INSUFICIENTES`;
- `ANIOS_NETO_POSITIVO_INSUFICIENTES`;
- `UPLIFT_VS_UNIVERSO_NO_POSITIVO`;
- `ANIOS_UPLIFT_VS_UNIVERSO_INSUFICIENTES`;
- `ANIOS_UPLIFT_VS_PRECIO_ONLY_INSUFICIENTES`.

`UPLIFT_VS_PRECIO_ONLY_NO_POSITIVO` no se activó globalmente porque el uplift medio contra price-only fue +0.7511 bps, pero esa mejora fue demasiado pequeña e inestable: solo 2 de 4 años tuvieron uplift positivo frente a ese control.

## Interpretación

El filtro identifica shocks reales: los activos seleccionados habían caído en promedio ~143 bps durante las 8h previas. Sin embargo, el rebote posterior medio fue únicamente ~4.54 bps, insuficiente frente al hurdle de 25 bps.

Más importante aún, OI descendente + predominio taker vendedor no demostraron valor incremental robusto sobre una simple reversión por precio. El uplift contra price-only fue apenas +0.75 bps en promedio y solo positivo en 2 de 4 años. Contra el universo completo, la señal fue incluso ligeramente peor en promedio (-0.44 bps).

Por tanto, v22 no justifica integración con scanner, EconomicGate, RiskEngine ni PAPER operativo. Tampoco justifica modificar retrospectivamente el bottom quartile, los umbrales de OI/taker, el horizonte ni invertir la dirección.

## Conclusión

v22 queda falsada en desarrollo 2022-2025.

La evidencia no respalda que añadir contracción de OI y presión taker vendedora a una señal simple de mean reversion genere un edge económicamente suficiente y estable. La próxima hipótesis, si se continúa 04B, debe ser materialmente distinta y predeclarada; no debe convertirse en una búsqueda de parámetros dentro de v22.

## Seguridad

- 2026 cerrado;
- mayo-julio 2026 cerrado;
- PAPER sin integración operativa de v22;
- LIVE cerrado;
- Render sin cambios;
- GPT no usado para señal;
- sin merge a `main`.
