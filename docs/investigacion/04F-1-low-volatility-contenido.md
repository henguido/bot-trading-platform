# BOT 2.0 — 04F-1 Contenido y elegibilidad low-volatility

## Objetivo

Validar el contenido real de klines `1d` y demostrar que existe un universo **económicamente elegible** antes de calcular volatilidad o retorno futuro.

**04F-1 NO CALCULA VOLATILIDAD, RANKING LOW-VOL, RETORNO FUTURO NI PnL.**

04F-0 ya confirmó que el archivo histórico tiene 302–421 pares Spot-USDT con tres meses previos + mes de holding disponibles. 04F-1 endurece la prueba con contenido real y reglas de elegibilidad conocidas antes de cada entrada.

## Periodo y calendario congelados

- holdings: enero 2022 a diciembre 2025;
- formación: exactamente 3 meses inmediatamente anteriores;
- holding futuro eventual: 1 mes;
- 48 rebalanceos;
- 2026 cerrado.

No se ejecutará después un grid de ventanas 1/2/3 meses para escoger la que mejor rinda.

## Fuente

Binance Vision Spot monthly klines `1d`, obtenidos desde prefixes históricos. `exchangeInfo` actual sigue prohibido como constructor del universo.

04F-1 puede descargar los ZIP diarios/mensuales necesarios porque la finalidad es validar **contenido conocido hasta la entrada**, no observar retornos de cartera.

## Validación por fila

Cada ZIP debe:

- contener exactamente un CSV;
- tener 12 columnas por kline;
- aceptar header opcional;
- aceptar timestamps Spot ms o µs y normalizarlos por magnitud;
- abrir exactamente a 00:00 UTC;
- mantener las fechas dentro del mes nominal;
- no duplicar días;
- mantener días ordenados;
- presentar OHLC positivo/coherente, quote volume no negativo, trades no negativos y taker quote volume no negativo.

Un archivo inválido no se imputa.

## Exclusiones categóricas PRE-PnL

Se excluyen de una futura cartera:

1. bases fiat/stable predeclaradas (`USDC`, `BUSD`, `TUSD`, `USDP`, `DAI`, `PAX`, `FDUSD`, `USDS`, `USD1`, `PYUSD`, `USDE`, `USUAL`, `SUSD`, `USDJ`, `XUSD`, `VAI`, `UST`, `USTC`, `EUR`, `AEUR`, `EURI`, `EURT`, `GBP`, `AUD`, `BRL`, `BIDR`, `IDRT`, `TRY`, `RUB`, `UAH`, `NGN`, `BVND`);
2. Binance Leveraged Tokens históricos identificados por una **lista explícita de tickers BLVT**, no por sufijos genéricos.

Estas exclusiones son por tipo de instrumento, no por resultado histórico.

### Corrección de clasificación antes del resultado

Durante la ejecución inicial, pero **antes de que el auditor produjera su primer resultado real**, se detectó que la regla preliminar `base.endswith("UP")` podía excluir erróneamente un activo normal como `JUP`. Esa regla se retiró antes de interpretar datos.

Se sustituyó por la lista explícita de 40 tickers BLVT del periodo (`1INCHUP/DOWN`, `XLMUP/DOWN`, `SUSHIUP/DOWN`, `AAVEUP/DOWN`, `BCHUP/DOWN`, `YFIUP/DOWN`, `FILUP/DOWN`, `SXPUP/DOWN`, `UNIUP/DOWN`, `LTCUP/DOWN`, `XRPUP/DOWN`, `DOTUP/DOWN`, `TRXUP/DOWN`, `EOSUP/DOWN`, `XTZUP/DOWN`, `BNBUP/DOWN`, `LINKUP/DOWN`, `ADAUP/DOWN`, `ETHUP/DOWN`, `BTCUP/DOWN`).

La corrección no cambia cobertura, liquidez, número mínimo de activos, periodo, ventana, ni usa retorno/PnL. El primer run queda técnicamente supersedido por el run que contenga esta corrección, aunque el primero llegue a completar.

## Gate de cobertura PREDECLARADO

Para cada rebalanceo, un símbolo debe tener al menos **95%** de los días calendario de los tres meses de formación presentes.

No se rellenan días ausentes y no se usa información posterior a la entrada para mejorar la cobertura.

## Gate de liquidez PREDECLARADO

Se usan únicamente los 30 días calendario inmediatamente anteriores al día de entrada:

- al menos 27 días con kline válido;
- mediana de `quote_volume` diaria ≥ **5.000.000 USDT**.

El umbral se fija antes de descargar contenido y busca evitar que una eventual anomalía dependa de microcaps difíciles de ejecutar. No se reducirá después de observar cuántos símbolos sobreviven.

## Comprobación de entrada

Después de cobertura y liquidez, el símbolo debe tener kline en el primer día UTC del mes de holding. Esta comprobación ocurre en el instante de entrada y no usa información del resto del mes.

Un futuro backtest deberá manejar una posible delistación durante el mes sin excluirla retrospectivamente.

## Gate cross-sectional

Cada uno de los 48 meses debe conservar al menos **50 activos elegibles** después de:

- exclusiones categóricas;
- cobertura ≥95%;
- liquidez ≥5M de mediana 30d;
- barra disponible en el día de entrada.

50 activos permiten una futura construcción por quintiles con al menos 10 activos en cada extremo sin que este gate observe la volatilidad.

Aprobación:

`DATASET_LOW_VOL_ELEGIBILIDAD_APTO_04F1`

Fallo:

`DATASET_LOW_VOL_ELEGIBILIDAD_NO_APTO_04F1`

## Candados

- volatilidad: no calcular;
- ranking low-vol: no calcular;
- retorno futuro: no calcular;
- PnL: no calcular;
- no current-universe survivorship;
- no imputación;
- no credenciales;
- sin PAPER operativo;
- sin LIVE;
- sin Render;
- 2026 cerrado.

Si 04F-1 pasa, la siguiente etapa podrá predeclarar la **única** hipótesis económica low-volatility, costos y gates de estabilidad antes de leer PnL.
