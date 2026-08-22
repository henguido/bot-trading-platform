# BOT 2.0 — 04G-1a Matriz fija de order-flow features

## Objetivo

Comprobar si podemos construir una matriz **complete-case y de dimensión fija** para una futura réplica ML, sin seleccionar monedas por rentabilidad y sin imputar order flows ausentes.

04G-1 ya demostró que la semántica de OF desagregado es apta y conserva 19–20 bases por mes cuando se permiten cualesquiera dos quotes válidos. Esa flexibilidad no basta para un modelo con columnas fijas, por lo que 04G-1a endurece la prueba.

## Selección de quotes PRE-PnL

La regla se fija exclusivamente usando el inventario 04G-0, no retornos:

> incluir todos los quotes predeclarados que tuvieron presencia global en **48/48 meses** para al menos una base.

La regla produce exactamente:

`USDT, EUR, BRL, TRY, UAH`.

No se probarán subconjuntos 2/3/4/5 quotes para elegir el que deje mejor rendimiento.

## Feature row

Para una base y día `t`, una fila completa necesita:

1. OF estandarizado USDT en `t`;
2. OF estandarizado EUR en `t`;
3. OF estandarizado BRL en `t`;
4. OF estandarizado TRY en `t`;
5. OF estandarizado UAH en `t`;
6. retorno Spot-USDT conocido de `t-1` a `t`.

El OF usa `ln(buy)-ln(sell)` y `of_t/std(of_{t-29:t})`, igual que 04G-1. No se usa retorno `t+1`.

## Por qué mínimo 10 bases

El paper reporta robustez específica al restringir la evaluación a las **top-10 monedas por market cap**. Con esa sección, los modelos OF no lineales mantienen R² OOS positivo; SGB y NL-Mean continúan siendo los mejores. Para la cartera económica de top-10 forman terciles de tres monedas.

Por ello 04G-1a exige al menos **10 bases complete-case por día**, en vez de inventar un umbral a partir de nuestra cobertura.

## Gates

Periodo de features: 2022-01-01 a 2025-12-31. Diciembre 2021 es solo warm-up de 30 días.

Un día es utilizable si conserva >=10 bases complete-case.

Aprobación exige simultáneamente:

- >=95% de todos los días 2022-2025 utilizables;
- >=90% de días utilizables **en cada año** 2022, 2023, 2024 y 2025.

Aprobación:

`MATRIZ_OF_FIJA_APTA_04G1A`

Fallo:

`MATRIZ_OF_FIJA_NO_APTA_04G1A`

## Candados

- quote selection por performance: no;
- imputación: no;
- retorno rezagado: sí, conocido en t;
- retorno futuro: no;
- ML: no;
- PnL: no;
- credenciales: no;
- PAPER operativo: no;
- LIVE: no;
- Render: no;
- 2026 cerrado.

Si esta matriz pasa, recién entonces puede predeclararse el esquema OOS de entrenamiento/validación/test publicado. Si falla, no se eliminará retrospectivamente UAH/EUR/etc. para rescatarla; cualquier representación variable de quotes tendría que abrirse como hipótesis metodológica nueva.
