# BOT 2.0 — Resultado 04G-2 Consensus Order Flow + SGB

## Veredicto

`CONSENSUS_OF_SGB_FALSADO_04G2`

La hipótesis predeclarada no supera los gates económicos OOS. La falsación es económica, no de transporte ni cobertura.

## Ejecución válida

- branch: `agent/bot-2.0-04g2-nonlinear-consensus-orderflow`
- HEAD ejecutado: `a5f5a75a9ea2494d1571b26b384afc5eed594e13`
- workflow: `research-04g2`
- run #2: `32569590569`
- CI general #151: success
- candados metodológicos: OK
- tests 04G-2: 5/5
- 2026: cerrado
- credenciales: no usadas
- PAPER operativo/LIVE/Render: no usados

El run #1 no llegó a datos ni PnL: falló únicamente por el bootstrap de imports del runner (`ModuleNotFoundError: backend`). Se corrigió el `sys.path` sin modificar hipótesis, features, grid, costos, fechas o gates.

## Datos OOS

- filas construidas: 29.047
- días OOS esperados: 730
- días OOS utilizables: 730/730 (100%)
- razones de insuficiencia de datos: ninguna

Por tanto, `DATOS_INSUFICIENTES_04G2` no aplica.

## Hiperparámetros seleccionados exclusivamente con validation 2023

- `n_estimators = 100`
- `learning_rate = 0.03`
- `max_depth = 2`
- `loss = huber`
- `subsample = 0.5`
- `min_samples_leaf = 20`
- `random_state = 42`

2024–2025 no participaron en la selección.

## Resultado OOS 2024–2025

### Capacidad predictiva

- R² OOS contra forecast cero: **-0.004919057151081319**

El modelo empeora el error cuadrático frente a pronosticar retorno cero.

### Cartera long-only top 20% — costo primario 25 bps × turnover

- media diaria neta: **-11.288468 bps**
- Sharpe anualizado neto: **-0.5841**
- meses netos positivos: **7/24**
- años netos positivos: **0/2**
- uplift de media neta vs equal-weight: **-20.450945 bps**
- uplift de media neta vs sort directo por consensus OF: **-10.691542 bps**

### Stress 50 bps × turnover

- media diaria neta: **-30.954564 bps**
- Sharpe anualizado neto: **-1.6018**

## Gates rechazados

- `R2_OOS_NOT_POSITIVE`
- `NET_MEAN_25_NOT_POSITIVE`
- `SHARPE_25_BELOW_GATE`
- `POSITIVE_MONTHS_25_BELOW_GATE`
- `POSITIVE_YEARS_25_BELOW_GATE`
- `NO_UPLIFT_VS_EQUAL_WEIGHT`
- `NO_UPLIFT_VS_CONSENSUS`
- `NET_MEAN_50_NOT_POSITIVE`
- `SHARPE_50_BELOW_GATE`

No se incumplió ningún gate de datos; se incumplieron todos los gates económicos.

## Artefacto

- nombre: `consensus-orderflow-sgb-04g2`
- artifact ID: `9475007161`
- SHA256 ZIP: `1b70cd8e852403ce91865316ec2f0f0b7fa875431cf9b5690455566a0da9d930`
- tamaño: 2.852 bytes

## Interpretación

04G-2 falsifica **esta adaptación Binance-only** del order flow internacional. No falsifica el paper original: nuestra fuente pública no reproduce su panel fijo internacional y la compresión `consensus_of` es una representación nueva.

No hay justificación metodológica para rescatar 04G-2 cambiando a posteriori grid, features, quotes, signo, costos o umbrales. La línea 04G se cierra aquí salvo que en el futuro exista una fuente externa que permita replicar de manera mucho más fiel el panel internacional original.
