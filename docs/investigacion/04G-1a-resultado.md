# BOT 2.0 — 04G-1a Resultado matriz fija order flow

## Veredicto

`MATRIZ_OF_FIJA_NO_APTA_04G1A`

La representación complete-case con cinco columnas fijas (`USDT`, `EUR`, `BRL`, `TRY`, `UAH`) no es viable sobre Binance 2022-2025, aunque esas cinco quotes tengan presencia global durante 48/48 meses a nivel de universo.

## Resultado real

Workflow `research-04g1a` #1, run `32554058167`, HEAD `2dfbbd684499fff264a623d2559cf10337308e11`:

- pair listings: 100/100 completos;
- archivos mensuales: **3.408**;
- barras diarias: **103.538**;
- errores de contenido: **0**;
- días objetivo: **1.461**;
- días con >=10 bases complete-case: **0**;
- fracción utilizable total: **0,0%**;
- 2022: 0,0%;
- 2023: 0,0%;
- 2024: 0,0%;
- 2025: 0,0%;
- bases complete-case por día: mínimo **1**, máximo **4**.

Gates congelados antes del run:

- cinco OF fijos seleccionados por cobertura, no performance;
- >=10 bases complete-case por día;
- >=95% días utilizables total;
- >=90% días utilizables por año.

El fallo es estructural y no económico. No se observó retorno futuro, ML ni PnL.

## Decisión metodológica

No se eliminará retrospectivamente `UAH`, `EUR`, `BRL` o `TRY`, ni se probarán subconjuntos 2/3/4 quotes para hallar una matriz que pase. Eso convertiría disponibilidad observada en selección post hoc.

04G-1a cierra únicamente la representación **de columnas fijas complete-case**. No invalida 04G-0/04G-1, que demostraron que 19-20 de los 20 activos conservan al menos dos OF desagregados válidos por mes cuando las quotes disponibles pueden variar.

Cualquier representación variable deberá abrirse como hipótesis metodológica nueva, predeclarada antes de observar retorno futuro. La motivación permitida es exclusivamente manejar missing-by-market-availability, no mejorar performance.

## Evidencia

- methodology locks: success;
- tests específicos: 3/3 passed;
- CI general #148: success;
- artifact `orderflow-fixed-matrix-04g1a`;
- artifact ID `9470924524`;
- SHA256 `620b1be60044b92e655934adf1b62e7fd7966a70bc1ecef96b9853db30d83a08`.

## Candados preservados

No se realizó:

- selección de quote por performance;
- imputación;
- retorno futuro;
- ML;
- PnL;
- credenciales;
- PAPER operativo;
- LIVE;
- Render;
- apertura de 2026.
