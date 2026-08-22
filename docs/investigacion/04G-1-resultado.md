# BOT 2.0 — 04G-1 Resultado contenido/semántica order flow multi-quote

## Veredicto

`DATASET_OF_DESAGREGADO_APTO_04G1`

Los datos públicos de Binance Vision permiten reconstruir de forma consistente order flows **desagregados por quote currency** para el universo líquido 2022-2025, usando la definición `ln(buyer)-ln(seller)` y rolling de 30 días, sin credenciales ni retornos futuros.

## Resultado real

Workflow `research-04g1` #1, run `32553716171`, HEAD `0258341ba52c748ceff44a13f1ebe835c2f9c620`:

- pair listings: 280/280 completos;
- archivos mensuales descargados: **6.192**;
- barras diarias: **186.515**;
- tamaño comprimido: **0,00986 GiB**;
- archivos con errores de contenido: **0**;
- meses objetivo: 48;
- bases válidas por mes, mínimo: **19/20**;
- bases válidas por mes, máximo: **20/20**;
- razones de rechazo global: ninguna.

El gate predeclarado exigía, por pair-month:

1. >=90% de días calendario con kline válido;
2. >=90% de días observados con buyer y seller estrictamente positivos;
3. >=90% de días con OF estandarizado válido usando una ventana completa de 30 días;
4. >=2 quotes válidos por base/mes;
5. >=15/20 bases válidas en cada mes.

El resultado conserva 19-20 bases en los 48 meses.

## Sobre los mínimos diagnósticos del log

El runner también reporta `positive_min=0.870967...` y `std_min=0.0`. Estos valores son mínimos observados en pair-months que alcanzan etapas intermedias del diagnóstico, **incluidos pair-months posteriormente descartados** por no superar los gates individuales. No representan la calidad mínima de los pairs que finalmente cuentan como válidos.

El gate final usa únicamente quotes que superan cobertura, positividad y OF estandarizado. Después de esas exclusiones quedan 19-20 bases, por lo que el estado apto no contradice esos mínimos diagnósticos.

## Correspondencia semántica

En Binance Spot kline:

- buyer-initiated quote volume = `taker_buy_quote_volume`;
- seller-initiated quote volume = `quote_volume - taker_buy_quote_volume`.

No se permite `log(0)`, clipping ni epsilon artificial. Los timestamps 2025 en microsegundos y anteriores en milisegundos se normalizan por magnitud.

## Relación con el paper

El artículo *Order flow and cryptocurrency returns* usa para sus modelos ML los **order flows internacionales desagregados** y retorno rezagado. El desempeño ML no depende de construir primero el agregado world: los portfolio sorts ML de la sección 5.2.2 condicionan en los order flows internacionales.

Por tanto, la ambigüedad de unidad del agregado world no bloquea una futura réplica de la parte ML con features desagregadas. 04G seguirá sin presentar nuestro proxy Binance como réplica exacta de las 11 monedas del dataset CryptoCompare.

## Evidencia técnica

- methodology locks: success;
- tests específicos: 5/5 passed;
- CI general #146: success;
- artifact: `world-orderflow-content-audit-04g1`;
- artifact ID: `9470841126`;
- SHA256: `2044593d7b730f9225dc254163504bde9b5048d8c007aede8ba1b50badc8bec9`.

## Candados preservados

No se realizó:

- world order flow agregado;
- conversión FX inventada;
- entrenamiento ML;
- retorno futuro;
- PnL;
- selección de quote por rentabilidad;
- credenciales;
- imputación;
- PAPER operativo;
- LIVE;
- Render;
- apertura de 2026.

## Decisión

04G puede avanzar a una auditoría de **matriz fija de features**. La selección de quotes deberá basarse exclusivamente en cobertura histórica ya observada, no en poder predictivo.

Regla natural pre-PnL para la siguiente etapa: partir de los quotes que en 04G-0 tuvieron cobertura global en 48/48 meses (`USDT`, `EUR`, `BRL`, `TRY`, `UAH`) y verificar cuántas bases conservan simultáneamente esas cinco features desagregadas sin imputación.
