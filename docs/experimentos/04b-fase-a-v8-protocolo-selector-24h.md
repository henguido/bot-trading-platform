# BOT 2.0-04B-v8 — Dirección metodológica pre-selector 24 h

Estado: predeclarado antes de ejecutar cualquier evaluación v8.

## Motivación

v7 mostró que el baseline long 24 h no cubre el hurdle económico de 25 bps,
pero sí existe dispersión cross-sectional amplia y un techo oracle ex-post muy
superior a costes. Por tanto v8 no intentará predecir dirección del mercado ni
comprar una cesta amplia. Intentará seleccionar como máximo un activo por
timestamp y abstenerse cuando la evidencia no sea suficiente.

## Periodo

Toda evaluación v8 previa al holdout usará únicamente 2022-2025. El año 2025
ya fue observado durante v1-v7 y se considera desarrollo, no validación limpia.

```text
enero-abril 2026: NO usar en v8 de desarrollo
mayo-julio 2026: HOLDOUT FINAL CERRADO
agosto 2026: fuera del experimento
```

## Horizonte

Fijo por v7 antes de construir el predictor:

```text
24 h
```

No se volverá a comparar 24/48/72 después de ver resultados v8.

## Objetivo económico

Para cada activo/timestamp se medirán dos targets futuros a 24 h:

```text
retorno bruto esperado
P(retorno bruto > 25 bps)
```

El hurdle mantiene:

```text
20 bps costes round-trip
+ 5 bps margen de seguridad
= 25 bps
```

## Features permitidas

Solo información disponible en t:

1. rank retorno 4 h;
2. rank retorno 24 h;
3. rank sorpresa de volumen 4 h;
4. mediana retorno 24 h del mercado;
5. dispersión IQR contemporánea del retorno 24 h del mercado.

La quinta feature está justificada directamente por v7: el experimento mostró
que el presupuesto económico está en la dispersión entre activos, no en el
baseline long medio.

No se añadirán RSI, MACD, noticias, GPT ni indicadores adicionales durante v8.

## Selector

La familia deberá ser determinística, empírica y abstencionista.

Una celda solo será candidata si simultáneamente:

```text
retorno bruto medio estimado > 25 bps
P(retorno bruto > 25 bps) >= 0.55
soporte mínimo suficiente
```

Por timestamp se escogerá como máximo una señal: mayor retorno bruto medio
estimado; empate por mayor probabilidad y luego símbolo ascendente.

## Criterios para considerar v8 prometedora en desarrollo

La evaluación será no solapada a 24 h y cost-aware. Para que la familia merezca
un único test final posterior deberá cumplir, sin cambiar criterios:

```text
>= 100 señales en desarrollo 2025
retorno neto medio después de hurdle > 0
>= 55 % señales con retorno neto > 0
señales en 12/12 meses de 2025
>= 8/12 meses con retorno neto medio > 0
señales en 4/4 folds trimestrales de 2025
>= 3/4 folds con retorno neto medio > 0
```

Además no se aceptará una configuración aislada: la robustez deberá aparecer en
una familia local de parámetros de soporte/discretización predeclarados.

## Lo que no se hará

- no abrir 2026 durante desarrollo v8;
- no bajar el hurdle de 25 bps;
- no escoger el horizonte por performance v8;
- no seleccionar la configuración con mayor retorno observado;
- no conectar el modelo a `main.py`, scanner, GPT, RiskEngine, PAPER o LIVE;
- no tocar Render.
