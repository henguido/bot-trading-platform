# BOT 2.0-04B-v18 — auditoría histórica de funding USD-M

## Resultado

**APROBADA como infraestructura de datos. No demuestra edge.**

La primera ejecución intentó `fapi.binance.com/fapi/v1/fundingRate` desde GitHub Actions. Las 20 descargas fallaron en la primera petición aun cuando el endpoint público devolvía funding histórico mediante el conector de Binance. Se trató como fallo de transporte, no como ausencia de datos ni falsación económica.

Sin alterar universo, periodo, thresholds ni ninguna hipótesis de retorno, la adquisición se cambió a los archivos mensuales de Binance Vision `futures/um/monthly/fundingRate`.

## Protocolo congelado

- Universo: 20 símbolos heredados de `UNIVERSO_VALIDACION_V2`.
- Periodo: 2022-01-01 UTC a 2026-01-01 UTC exclusivo.
- 2026 permanece cerrado.
- Fuente final: Binance Vision, archivos mensuales USD-M fundingRate.
- Se conservan `calc_time`, `funding_interval_hours` y `last_funding_rate`.
- No se presupone una cadencia fija de 8h.
- No se rellenan eventos ausentes.
- Un 404 cuenta como ausencia histórica visible y lo decide la cobertura.
- Un error distinto de 404 bloquea técnicamente el dataset.
- Cobertura mínima por símbolo: 95% de días con al menos un evento.
- Mínimo de símbolos aptos: 15/20.
- Cross-section: al menos 15 símbolos por día, >=95% global y >=90% por año.

## Validación real

GitHub Actions `ci` run `32418355181`:

- Python 3.13: **1070 tests passed**.
- `compileall backend`: OK.
- Frontend Vite: **841 módulos** transformados, build OK.
- Locks: `DESARROLLO_2026_ABIERTO_V18=False`, `TEST_MAY_JUL_ABIERTO_V18=False`.
- Tareas mensuales: **960**.
- Meses válidos: **960/960**.
- 404: **0**.
- Errores técnicos: **0**.
- Eventos funding: **87,735**.
- Símbolos aptos: **20/20**.
- Fracción de días con cross-section >=15 símbolos: **1.0 (100%)**.
- Estado: `DATASET_FUNDING_APTO_V18`.

Artifact: `funding-data-audit-v18-2022-2025`, ID `9424786276`.

## Qué permite y qué NO permite

v18 demuestra que podemos reconstruir de forma reproducible un panel histórico de funding Binance USD-M suficientemente completo para 2022–2025.

No demuestra que funding prediga retornos, no determina todavía un tamaño de posición y no modifica scanner, RiskEngine, PAPER/LIVE, base de datos ni ejecución.

## Handoff a v19

La hipótesis económica deberá declararse antes de observar retornos. Para comparar días con distinto número/intervalo de settlements, la variable diaria candidata será la **suma de los funding rates efectivamente publicados durante el día**. Esa suma representa la presión/carry acumulada observada y evita inventar settlements.
