# BOT 2.0-04B-v11 — Momentum semanal 1–3 semanas

## Estado

**Resultado v11: `SIN_FACTORES_PROMETEDORES_V11`.**

**Resultado v11b: `RMOM3_REPLICA_NO_CONSISTENTE` — 0/3 años aptos.**

2026 permaneció cerrado. No se modificó `main`, trading productivo, RiskEngine,
EconomicGate, LIVE ni Render.

## Protocolo predeclarado

- Dataset descargado: 2022-01-01 a 2025-12-31, velas Spot 4h.
- Clasificación v11: únicamente timestamps semanales de 2025.
- Rebalanceo: cierre del domingo, límite lunes 00:00 UTC.
- Horizonte futuro: 7 días / 168h.
- Hurdle económico: 25 bps por operación round-trip.
- Universo: 20 pares USDT versionados previamente.
- Factores: MOM1, MOM2, MOM3, RMOM1, RMOM2 y RMOM3.
- Dirección probada: solo ALTA.
- RMOM: media de retornos diarios / desviación estándar muestral diaria, rf=0.

## Validación técnica

Primera corrida v11: CI `32395599155`, HEAD `76376a0352c2b1dd2eb9a1a108cbfd7138d8d6ea`.

Corrida final con réplica v11b: CI `32396346083`, HEAD `6a2b6f34297b3b053f0f70d88b8e896d796d43a4`:

- 1004 tests passed.
- `python -m compileall backend`: OK.
- frontend build: OK, 841 módulos.
- locks v11: `DESARROLLO_2026_ABIERTO_V11=False` y `TEST_MAY_JUL_ABIERTO_V11=False`.
- 20/20 símbolos útiles.
- 4.100 observaciones semanales históricas construidas.
- 51 timestamps de decisión en 2025.

La API primaria de Binance quedó restringida por ubicación en el runner; el
fallback público market-data-only `data-api.binance.vision` completó las 20
series con 8.766 velas cada una.

## Resultados v11 — 2025

| Factor | IC medio | Spread alto-bajo (bps) | Semanas spread + | Top-1 neto medio (bps) | Hit-rate top-1 | Meses top-1 + | Folds top-1 + |
|---|---:|---:|---:|---:|---:|---:|---:|
| MOM1 | 0,0321 | 91,32 | 49,02% | **+3,71** | 39,22% | 5/12 | 2/4 |
| MOM2 | 0,0307 | 81,34 | 47,06% | -147,58 | 47,06% | 6/12 | 2/4 |
| MOM3 | 0,0170 | 30,51 | 50,98% | -116,58 | 45,10% | 6/12 | 2/4 |
| RMOM1 | 0,0550 | 129,26 | 54,90% | -191,30 | 33,33% | 5/12 | 1/4 |
| RMOM2 | 0,0215 | 57,56 | 52,94% | -172,86 | 43,14% | 6/12 | 2/4 |
| RMOM3 | 0,0155 | 43,21 | **54,90%** | **+29,93** | **50,98%** | **9/12** | **3/4** |

Ningún factor cumplió simultáneamente spread y top-1.

RMOM3 fue el único factor que combinó retorno top-1 neto positivo, 9/12 meses y
3/4 folds positivos. No se promovió: falló los dos umbrales de frecuencia que
estaban congelados antes del resultado:

- fracción de semanas con spread positivo: `54,90% < 55%`;
- hit-rate top-1 neto positivo: `50,98% < 55%`.

No se redondeó 54,90% a 55% y no se rebajaron thresholds.

## Réplica v11b — RMOM3 en 2022, 2023 y 2024

Antes de mirar estos resultados se fijó:

- factor: RMOM3 únicamente;
- orientación: ALTA;
- horizonte: 168h;
- hurdle: 25 bps;
- mismos thresholds de v11;
- evaluación independiente por año;
- regla agregada: solo seguir como candidato si al menos 2 de 3 años son aptos.

| Año | Semanas | Spread medio (bps) | Semanas spread + | Meses spread + | Folds spread + | Top-1 neto medio (bps) | Hit-rate top-1 | Meses top-1 + | Folds top-1 + | Apto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2022 | 49 | 83,35 | 61,22% | 9/12 | 3/4 | +62,26 | 48,98% | 5/12 | 2/4 | No |
| 2023 | 53 | 106,91 | 45,28% | 7/12 | 3/4 | +134,76 | 52,83% | 8/12 | 2/4 | No |
| 2024 | 52 | 43,39 | 51,92% | 7/12 | 3/4 | +274,31 | 55,77% | 5/12 | 3/4 | No |

### Motivos de rechazo

**2022**: spread apto, pero top-1 rechazado por hit-rate, estabilidad mensual y
estabilidad trimestral.

**2023**: spread rechazado por frecuencia semanal y meses; top-1 rechazado por
hit-rate y estabilidad trimestral.

**2024**: top-1 supera retorno, hit-rate y folds, pero falla estabilidad mensual;
el spread falla frecuencia semanal y meses.

Resultado agregado: `0/3` años aptos; `replica_consistente=False`.

## Conclusión

RMOM3 queda falsificado como selector **top-1** bajo este protocolo. Las medias
netas positivas de 2022-2025 no bastan: el beneficio está demasiado concentrado
en semanas o meses concretos y no cumple la estabilidad fijada de antemano.

No se abre 2026 y no se ajustan thresholds.

La siguiente investigación permitida debe cambiar la construcción de portfolio,
no rescatar RMOM3 con filtros retrospectivos: evaluar baskets long-only del
cuartil superior contra un benchmark equal-weight del mismo universo para saber
si la señal cross-sectional puede capturarse reduciendo riesgo idiosincrático y,
a la vez, aportar algo más que simple beta de mercado.
