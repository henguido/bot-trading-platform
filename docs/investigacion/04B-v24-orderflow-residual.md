# BOT 2.0 — 04B-v24 Order Flow Spot residual

## Estado

**PREDECLARADO — no se ha descargado el calendario v24 ni observado su resultado económico.**

v23 confirmó disponibilidad histórica de AggTrades; v23a validó esquema, timestamps y semántica `isBuyerMaker`; v23b fijó un calendario de 96 lunes con 1.920/1.920 ZIP disponibles y 7.617537 GiB comprimidos. v24 usa exactamente ese calendario, sin sustituir fechas.

## Hipótesis única

En el cross-section de criptoactivos, una presión compradora agresiva Spot alta **después de descontar la parte asociada al retorno del propio lunes** puede contener información incremental y anticipar retorno relativo positivo durante los siete días posteriores.

No se prueba la señal opuesta dentro de v24.

## Ventana y datos

Por cada primer y tercer lunes UTC de cada mes entre 2022 y 2025:

1. Se procesa el AggTrades Spot completo del lunes `T`.
2. `isBuyerMaker=false` se clasifica como comprador agresor/taker buy.
3. `isBuyerMaker=true` se clasifica como vendedor agresor/taker sell.
4. Se suma por lado `precio × cantidad` en moneda quote.
5. Se calcula:

`OFI = (buy_quote - sell_quote) / (buy_quote + sell_quote)`

No se winsoriza, clippea ni imputa.

## Control por movimiento contemporáneo

El retorno contemporáneo se define como:

`r0 = open(T+1 día) / open(T) - 1`

Para cada fecha se estima una regresión OLS cross-sectional simple, con intercepto:

`OFI_i = alpha + beta * r0_i + epsilon_i`

La feature de v24 es `epsilon_i`, el residual de OFI. No se reutiliza información de fechas posteriores para estimar `alpha` o `beta`.

## Señal y ejecución de investigación

- mínimo 15 activos elegibles por fecha;
- ranking descendente por residual OFI;
- desempate determinístico por símbolo ascendente;
- selección: top 25% del cross-section elegible;
- la ventana de feature termina antes de la entrada;
- entrada: `open(T+1 día)`, martes 00:00 UTC;
- salida: `open(T+8 días)`, martes siguiente 00:00 UTC;
- horizonte: siete días;
- las observaciones del calendario están separadas al menos dos semanas, por lo que los horizontes no se solapan.

## Baselines

Se reportan tres controles contemporáneos usando exactamente los mismos activos elegibles y horizonte:

1. equal-weight de todo el universo elegible;
2. top 25% por retorno contemporáneo `r0` — baseline de momentum de precio;
3. top 25% por OFI crudo — diagnóstico para saber si la residualización aporta frente a usar flujo sin controlar precio.

El baseline OFI crudo se reporta pero no es gate de aprobación. v24 sí debe superar al universo y al price-only.

## Hurdle

- coste round trip: 20 bps;
- margen de seguridad: 5 bps;
- hurdle total: **25 bps**.

`retorno_neto = retorno_bruto_señal - 25 bps`

## Gate de datos

Si falla cualquiera de estos puntos, el resultado es `DATOS_INSUFICIENTES_V24`, no falsación económica:

- al menos 95% de los 1.920 AggTrades objetivo descargados y parseados completamente;
- al menos 15 series Spot de precios completas;
- 100% de las 96 fechas conserva al menos 15 activos con feature y precios válidos;
- sin imputación.

Se permite un solo reintento de transporte para AggTrades fallidos. No se reemplazan fechas ni símbolos por otros.

## Gate económico predeclarado

Para aprobar v24 debe cumplirse simultáneamente:

- al menos 80 timestamps con señal;
- al menos 42 meses con señal;
- los 4 años representados;
- media neta después de 25 bps > 0;
- al menos 50% de timestamps con retorno neto > 0;
- al menos 28 meses con retorno neto > 0;
- al menos 3/4 años con retorno neto > 0;
- uplift medio vs universo > 0;
- uplift medio vs price-only > 0;
- al menos 3/4 años con uplift positivo vs universo;
- al menos 3/4 años con uplift positivo vs price-only.

El resultado OFI crudo se conserva como diagnóstico, no como criterio que permita rescatar la hipótesis residual.

## Candados

- no invertir signo;
- no ajustar top quartile tras ver resultados;
- no cambiar calendario;
- no cambiar horizonte;
- no cambiar hurdle;
- no winsorizar ni clippear;
- no imputar;
- no Futures;
- no OI;
- no funding;
- no GPT;
- no scanner;
- no RiskEngine;
- no PAPER operativo;
- no LIVE;
- no Render;
- 2026 cerrado;
- mayo-julio 2026 cerrado.

## Interpretación

Si v24 falla con datos suficientes, se considera falsada esta formulación exacta de **presión compradora Spot residual al movimiento contemporáneo**. No se probará inmediatamente el signo contrario ni se moverán percentiles/horizontes dentro de la misma versión.
