# BOT 2.0-04B-v12 — Basket top-5 vs mercado

## Estado

**Resultado: `SIN_PORTFOLIOS_PROMETEDORES_V12`.**

2026 permaneció cerrado. No se modificó `main`, trading productivo, RiskEngine,
EconomicGate, LIVE ni Render.

## Protocolo predeclarado

- Dataset: Spot 4h, 2022-01-01 a 2025-12-31.
- Observaciones: semanales, mismas MOM/RMOM de v11.
- Factores: MOM1, MOM2, MOM3, RMOM1, RMOM2 y RMOM3.
- Portfolio: top-5 equal-weight por factor (cuartil superior de 20 activos).
- Benchmark: equal-weight del universo contemporáneo.
- Hurdle: 25 bps por semana tanto para basket como benchmark.
- Un año exige rentabilidad neta absoluta y exceso estable contra benchmark.
- Un factor solo sobrevive con al menos 3 de 4 años aptos.

## Validación técnica

CI run `32399708541`, HEAD `70b23635e0c4c908a0a78afbb8da7cfc1d683043`:

- 1008 tests passed.
- `python -m compileall backend`: OK.
- frontend build: OK, 841 módulos.
- locks v12: `DESARROLLO_2026_ABIERTO_V12=False` y `TEST_MAY_JUL_ABIERTO_V12=False`.
- 20/20 símbolos útiles.
- 4.100 observaciones semanales históricas.

## Resultado agregado

Todos los factores terminaron con `anios_aptos=0/4`:

| Factor | Años aptos |
|---|---:|
| MOM1 | 0/4 |
| MOM2 | 0/4 |
| MOM3 | 0/4 |
| RMOM1 | 0/4 |
| RMOM2 | 0/4 |
| RMOM3 | 0/4 |

No se cambia top-k, hurdle ni umbrales después del resultado.

## Lectura económica

El patrón separa beta de selección:

- En 2022 el benchmark neto medio fue -172,58 bps/semana y en 2025 -102,76 bps/semana. Los baskets top-5 también fueron negativos aunque algunos generaron exceso positivo relativo.
- En 2023 el benchmark fue +141,70 bps/semana y en 2024 +203,48 bps/semana. Muchos baskets fueron positivos, pero el exceso contra mercado no fue estable.
- RMOM3 ilustra la diferencia: en 2022 su exceso fue +30,69 bps y la parte de exceso cumplió los criterios, pero el basket absoluto perdió -141,89 bps. En 2023 el basket absoluto pasó (+225,09 bps), pero el exceso falló estabilidad/frecuencia. En 2024 el basket ganó +187,70 bps pero quedó por debajo del benchmark. En 2025 volvió a perder -68,94 bps.

Conclusión: diversificar top-1 a top-5 reduce idiosincrasia, pero no convierte MOM/RMOM en alpha estable. La rentabilidad absoluta sigue muy condicionada por el régimen general del mercado.

## Siguiente hipótesis permitida

v13 probará una construcción distinta, no otro top-k:

- régimen semanal conocido en t mediante mediana cross-sectional de MOM3;
- si régimen <= 0: cash / no trade;
- si régimen > 0: basket top-5;
- benchmark equal-weight sujeto al mismo gate;
- comparar por separado valor del gate de régimen y valor agregado del selector.

2026 seguirá cerrado durante el desarrollo de v13.
