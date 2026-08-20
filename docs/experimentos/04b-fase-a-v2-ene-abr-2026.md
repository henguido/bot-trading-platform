# BOT 2.0-04B — Fase A v2: validacion relativa enero-abril 2026

## Veredicto

**VALIDACION CON FAMILIA ROBUSTA, pero todavia no autorizada para 04C ni para
trading.**

La familia v2 de Expected Edge, basada en features relativas/cross-sectional,
supero los criterios predeclarados de validacion enero-abril 2026 para un solo
horizonte robusto: **8 h**. El efecto encontrado es positivo pero pequeno; por
tanto se conserva como evidencia para la siguiente revision metodologica, no
como permiso para conectar el modelo a ejecucion, GPT, RiskEngine, PAPER o LIVE.

El holdout final **mayo-julio 2026 permanece cerrado**.

## Ejecucion auditada

- Draft PR: `#2` — `WIP: validar BOT 2.0-04B v2 edge relativo`.
- Rama: `agent/bot-2.0-04b2-edge-relativo`.
- Head validado: `52e7066c1888d3cd8b042add55fb6b8ba73b2711`.
- `main` solo recibio infraestructura CI en `ca31e7fda2bbcf76d42f32de7b77d0cd229c9f4d`
  para exigir build completo antes de correr la validacion v2.
- Workflow remoto: `research-04b-v2`, run `32086920378`, conclusion `success`.
- Artefacto remoto: `edge-validation-v2-jan-apr-2026`, id `9307171209`,
  digest `sha256:0195d3f42fe617a30fff81ad05128f7e8ca98997ec50704a584cebc42bf08184`.
- La primera corrida v2, iniciada antes del ajuste de CI, fue cancelada y no se
  usa como evidencia.

Orden verificado del workflow corregido:

```text
pytest
compile backend
Node 20
frontend dependencies
frontend build
holdout lock
validacion enero-abril 2026
```

## Candados de datos

- Dataset usado: `2022-01-01T00:00:00Z` a
  `2026-04-30T23:59:59.999Z`.
- Test final empieza: `2026-05-01T00:00:00Z`.
- `test_may_jul_open`: `false`.
- El runner contiene `end_ms = VALIDACION_HASTA_MS`.
- El runner no referencia `TEST_HASTA_MS`.
- `VALIDACION_HASTA_MS < TEST_DESDE_MS`.
- Mayo-julio 2026 no aparece en folds ni en el dataset de validacion.

## Dataset

- Intervalo: 4 h.
- Universo predeclarado: 20 pares USDT.
- Simbolos utiles: **20/20**.
- Observaciones relativas pre-test: **188.760**.
- Fuente efectiva: `api.binance.com`.
- Descargas incompletas: **0**.
- Survivorship bias: **pendiente/declarado**; esta fase valida una familia
  relativa bajo universo fijo, no una rentabilidad final libre de sesgo.

Simbolos utiles:

```text
AAVEUSDT, ADAUSDT, ATOMUSDT, AVAXUSDT, BCHUSDT, BNBUSDT, BTCUSDT,
DOGEUSDT, DOTUSDT, ETCUSDT, ETHUSDT, FILUSDT, LINKUSDT, LTCUSDT,
NEARUSDT, SOLUSDT, TRXUSDT, UNIUSDT, XLMUSDT, XRPUSDT
```

## Features v2 validadas

No se agregaron indicadores discrecionales despues de observar v1. Las features
congeladas fueron:

1. `rank_retorno_4h`
2. `rank_retorno_24h`
3. `rank_sorpresa_volumen_4h`
4. `mediana_retorno_24h_mercado`

La sorpresa de volumen compara el volumen actual 4 h contra la mediana de las
42 barras anteriores del mismo simbolo. La barra actual queda fuera de su propio
baseline.

Cada timestamp necesita al menos **15 simbolos**; si no los tiene, se descarta
completo.

## Resultado del grid

- Configuraciones predeclaradas: **64**.
- Configuraciones que superan minimos: **4/64**.
- Configuraciones robustas de grid: **4/64**.
- Horizontes robustos: **8 h**.
- Cobertura de las configuraciones robustas: **1,0**.

Configuracion preferida por selector no-performance:

| Campo | Valor |
|---|---:|
| horizonte | 8 h |
| rank_bins | 3 |
| regimen_bins | 3 |
| min_muestras | 30 |
| max_radio | 0 |
| min_symbols | 3 |
| min_timestamps | 20 |
| min_symbols_por_timestamp | 15 |

Metricas de la familia robusta:

| Metrica | Valor |
|---|---:|
| uplift cross-section medio | 0,0003411755004224986 |
| fraccion timestamps con uplift positivo | 0,5154061624649860 |
| meses positivos | 3 |
| folds positivos | 3 |
| cobertura | 1,0 |

Conversion aproximada: `0,000341` equivale a **3,41 bps** brutos.

Las 4 configuraciones robustas comparten el mismo nucleo economico:

```text
horizonte=8h
rank_bins=3
regimen_bins=3
min_muestras=30 o 60
max_radio=0 o 1
```

## Motivos de rechazo

Conteo sobre las 64 configuraciones:

| Motivo | Conteo |
|---|---:|
| `UPLIFT_CROSS_SECTION_INESTABLE_FOLDS` | 52 |
| `UPLIFT_CROSS_SECTION_INESTABLE_MENSUAL` | 52 |
| `CROSS_SECTION_INESTABLE_TIMESTAMPS` | 48 |
| `SIN_UPLIFT_CROSS_SECTION` | 32 |

La lectura correcta es estrecha: v2 encontro una familia robusta, pero la mayor
parte del grid sigue fallando por estabilidad temporal/cross-sectional. No hay
evidencia para ampliar el resultado a otros horizontes.

## Correcciones de tests sinteticos

Durante la preparacion de v2 se corrigieron dos fixtures sinteticos sin debilitar
produccion:

1. El caso de cluster positivo ahora usa soporte compatible con el minimo real
   del modelo: **3 simbolos** con `min_symbols=3`.
2. El caso de soporte insuficiente ahora permite ajustar el modelo y fuerza que
   falle solo la celda consultada: train total suficiente, soporte local
   insuficiente.

Estas correcciones evitan falsos negativos de test sin bajar umbrales
productivos ni relajar el criterio de soporte.

## Lectura economica

La senal relativa v2 mejora el fallo central de v1: ya no intenta explicar el
activo por niveles absolutos, sino ordenar activos que compiten en el mismo
timestamp. Eso produjo una familia robusta en 8 h.

La magnitud, sin embargo, es pequena: unos **3,41 bps brutos** de uplift
cross-sectional medio. Antes de cualquier decision operativa, 04A obliga a
comparar esa senal contra fees, spread, slippage, tamano minimo, costo IA y
riesgo de ejecucion. Con esta evidencia, el resultado habilita mas analisis,
no trading.

## Lo que NO se hara

- No abrir mayo-julio 2026.
- No bajar criterios por ver el resultado.
- No escoger configuracion por mayor retorno observado.
- No conectar v2 a `main.py`, scanner, GPT, RiskEngine ni ejecucion PAPER/LIVE.
- No tocar Render.
- No convertir el draft PR en merge sin una decision explicita.

## Pendientes

1. Revisar manualmente PR `#2` con este resultado documentado.
2. Decidir si la siguiente fase sera una revision metodologica 04B-v2b o la
   apertura controlada del test final mayo-julio 2026.
3. Si se autoriza abrir mayo-julio, hacerlo una sola vez, con protocolo escrito
   antes de ejecutar y dejando constancia del SHA exacto.
4. Tratar aparte las vulnerabilidades npm reportadas por GitHub; no forman parte
   de la validacion 04B-v2.
