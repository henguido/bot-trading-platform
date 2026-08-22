# BOT 2.0 — 04G-0 Factibilidad de world-order-flow proxy

## Por qué esta línea

La selección se hace **antes de observar PnL nuevo** y después de cerrar low-volatility por gate de datos.

La evidencia externa más fuerte encontrada es Anastasopoulos et al., *Journal of Financial Markets* (2026), "Order flow and cryptocurrency returns". El paper estudia 84 criptomonedas con order flows denominados en 11 monedas, construye world order flow y encuentra:

- relación predictiva positiva entre order flow rezagado y retorno futuro aun controlando retorno rezagado;
- efecto más fuerte a frecuencia semanal que diaria;
- modelos lineales con desempeño OOS débil/negativo;
- modelos no lineales (RF, stochastic gradient boosting, redes neuronales y combinaciones) con desempeño OOS positivo;
- cartera long-only del forecast combinado no lineal con Sharpe anualizado reportado ~1,98;
- break-even transaction cost reportado ~1,07% para la cartera long-only;
- robustez frente a short-selling constraints y transaction costs.

Esto es materialmente diferente de v24. v24 utilizó **una sola fuente Spot-USDT**, un OFI agregado de un lunes, residualización lineal contra retorno contemporáneo y selección top-25% a horizonte 7 días. v24 no entrenó un modelo no lineal ni construyó world order flow multi-moneda.

## Advertencia de réplica

Binance no proporciona el dataset internacional exacto de 11 fiat currencies del paper. Por tanto, 04G no llamará "world order flow" a un USDT-only signal.

Antes de construir un modelo, 04G-0 verifica si los archivos públicos de Binance permiten un **proxy multi-quote** suficientemente amplio sobre los 20 activos líquidos ya fijados en v24.

Si la cobertura multi-quote no pasa, esta línea se detiene o se redefine mediante un protocolo nuevo; no se sustituye silenciosamente por USDT-only.

## Universo

Se heredan exactamente los 20 activos de v24/v23b:

BTC, ETH, BNB, XRP, ADA, DOGE, SOL, LTC, BCH, LINK, TRX, ETC, XLM, DOT, ATOM, AVAX, UNI, AAVE, FIL y NEAR.

No se seleccionan por resultado 04G.

## Quotes predeclarados

Por categoría fiat/stable, no por cobertura observada:

`USDT, BUSD, USDC, TUSD, FDUSD, EUR, GBP, AUD, BRL, TRY, RUB, UAH, BIDR, IDRT`.

BTC/ETH no se usan como quote porque esta etapa intenta aproximar la dimensión de flujos denominados en monedas/estables del paper.

## Fuente y periodo

Binance Vision público, Spot monthly klines `1d`, enero 2022 a diciembre 2025.

04G-0 enumera solo metadata S3. No descarga ZIP/CSV.

## Gate predeclarado

Para que un base/mes sea "multi-quote" debe tener al menos **2 quote pairs** con archivo mensual `1d` no vacío.

Cada uno de los 48 meses debe conservar al menos **15 de los 20 activos** con cobertura multi-quote.

Aprobación:

`DATASET_MULTIQUOTE_ORDERFLOW_APTO_04G0`

Fallo:

`DATASET_MULTIQUOTE_ORDERFLOW_NO_APTO_04G0`

## Candados

04G-0 no permite:

- descargar contenido de klines;
- calcular buyer/seller order flow;
- estandarizar order flow;
- entrenar ML;
- calcular retorno futuro;
- calcular PnL;
- usar credenciales;
- imputar quotes faltantes;
- PAPER operativo;
- LIVE;
- Render;
- abrir 2026.

## Si pasa

La siguiente etapa no será todavía un backtest. 04G-1 validará contenido real y semántica de `quote_volume` / `taker_buy_quote_volume` para reconstruir buyer-initiated y seller-initiated volume sin AggTrades, además de fijar la normalización multi-quote.

Solo después se podrá predeclarar una única réplica no lineal long-only.
