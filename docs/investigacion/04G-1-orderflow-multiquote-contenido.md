# BOT 2.0 — 04G-1 Contenido y semántica de order flow multi-quote

## Objetivo

Validar, **antes de cualquier retorno futuro o ML**, que los klines Spot `1d` de Binance Vision permiten reconstruir de forma consistente order flows desagregados por quote currency con la definición publicada en *Order flow and cryptocurrency returns* (Journal of Financial Markets, 2026).

04G-0 ya confirmó 48/48 meses con 19–20 de los 20 activos cubiertos por al menos dos quotes. 04G-1 descarga el contenido real de todos los pair-months disponibles del universo/quotes predeclarados.

## Definición publicada que sí se replica

Para cada activo, quote y día:

`of_t = ln(buyer_initiated_quote_volume_t) - ln(seller_initiated_quote_volume_t)`

Luego:

`OF_t = of_t / std(of_{t-29:t})`

La ventana contiene el día actual y los 29 días previos; nunca utiliza información futura. Diciembre de 2021 se permite exclusivamente como warm-up para enero de 2022.

El artículo describe `sigma(of_{t-29:t})` sin especificar el divisor de varianza; esta auditoría usa desviación estándar muestral únicamente para verificar **constructibilidad**, no para medir edge.

## Correspondencia con Binance

Los klines Spot públicos exponen:

- `quote_volume`;
- `taker_buy_quote_volume`.

Por semántica de agresor:

- buyer-initiated quote volume = `taker_buy_quote_volume`;
- seller-initiated quote volume = `quote_volume - taker_buy_quote_volume`.

04G-1 exige `0 <= taker_buy_quote_volume <= quote_volume` y no permite `log(0)`, clipping ni epsilon artificial.

## Agregado world BLOQUEADO

El paper define world order flow agregando los buy-volumes y sell-volumes de sus 11 monedas antes de aplicar log y estandarización. El texto accesible no explicita una conversión FX/unidad común previa a esa suma.

Por tanto, 04G-1 **no inventa una conversión entre USDT, EUR, BRL, TRY, etc.** y no calcula world order flow.

Los order flows desagregados sí son comparables tras el log-ratio/estandarización porque cada serie usa buyer y seller denominados en la misma quote.

## Universo y quotes

Mismos 20 activos líquidos heredados de v24 y los 14 quotes fijados en 04G-0:

`USDT, BUSD, USDC, TUSD, FDUSD, EUR, GBP, AUD, BRL, TRY, RUB, UAH, BIDR, IDRT`.

No se añaden o eliminan monedas según el resultado.

## Validación de contenido

Cada ZIP debe:

- contener un solo CSV;
- aceptar header opcional;
- tener 12 columnas;
- normalizar timestamps Spot ms/µs;
- abrir el kline diario a 00:00 UTC;
- mantener el día dentro del mes nominal;
- no duplicar ni desordenar días;
- presentar quote volume no negativo;
- presentar taker-buy quote no negativo y no superior al total;
- número de trades no negativo.

No hay imputación.

## Gates PRE-PnL

Un pair-month es utilizable si:

1. tiene al menos **90%** de días calendario con kline válido;
2. al menos **90%** de los días observados tienen buyer y seller estrictamente positivos;
3. al menos **90%** de los días calendario pueden producir OF estandarizado con una ventana completa de 30 días y desviación estándar >0.

Una base/mes necesita al menos **2 quotes utilizables**.

Cada uno de los 48 meses 2022–2025 necesita al menos **15 de los 20 activos** válidos.

Aprobación:

`DATASET_OF_DESAGREGADO_APTO_04G1`

Fallo:

`DATASET_OF_DESAGREGADO_NO_APTO_04G1`

## Candados

- descarga de kline content: sí, solo para semántica;
- OF desagregado: sí;
- world OF: no;
- conversión FX inventada: no;
- ML: no;
- retorno futuro: no;
- PnL: no;
- credenciales: no;
- imputación: no;
- PAPER operativo: no;
- LIVE: no;
- Render: no;
- 2026: cerrado.

Si 04G-1 pasa, la siguiente decisión será resolver formalmente el agregado world o, si no es reproducible, evaluar si la información desagregada por quotes justifica una hipótesis separada sin presentarla como réplica exacta del paper.
