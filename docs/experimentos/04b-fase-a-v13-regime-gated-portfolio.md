# BOT 2.0-04B-v13 — Portfolio con gate semanal de régimen

## Estado

**Resultado: `V13_SIN_SENAL`.**

El gate de régimen y los seis factores MOM/RMOM quedaron falsados bajo el
protocolo predeclarado. 2026 permaneció cerrado. No se modificó `main`, trading
productivo, RiskEngine, EconomicGate, LIVE ni Render.

## Protocolo

- Dataset: Spot 4h, 2022-01-01 a 2025-12-31.
- Observaciones: semanales, mismas MOM/RMOM de v11-v12.
- Gate ON: mediana cross-sectional de MOM3 > 0; cero o negativo = cash.
- Top-5 equal-weight cuando gate ON.
- Benchmark equal-weight sujeto al mismo gate.
- Hurdle: 25 bps por semana activa.
- Años: 2022, 2023, 2024, 2025.
- Gate/factor solo sobrevive con al menos 3/4 años aptos.

## Validación técnica

CI run `32400575861`, HEAD `82712a1fcaa15a6b72ec534411300c13c519a752`:

- 1012 tests passed.
- `python -m compileall backend`: OK.
- frontend build: OK, 841 módulos.
- locks v13: `DESARROLLO_2026_ABIERTO_V13=False` y `TEST_MAY_JUL_ABIERTO_V13=False`.
- workflows legacy de research: `skipped`; no abrieron 2026.
- runner v13 y artifact: OK.

## Gate de mercado

| Año | Semanas activas | Retorno calendar medio | Retorno activo medio | Hit-rate activo | Meses + | Folds + | Apto |
|---|---:|---:|---:|---:|---:|---:|---|
| 2022 | 16 | -110,70 bps | -339,01 bps | 43,75% | 2 | 1 | No |
| 2023 | 25 | +20,64 bps | +43,75 bps | 48,00% | 5 | 2 | No |
| 2024 | 26 | +77,16 bps | +154,32 bps | 46,15% | 2 | 2 | No |
| 2025 | 15 | +11,41 bps | +38,80 bps | 33,33% | 4 | 2 | No |

Resultado agregado: `GATE_REGIMEN_SIN_SENAL_V13`, `0/4` años aptos.

El gate no falla solo por cobertura: incluso en 2023-2024, donde la media es
positiva, la frecuencia y estabilidad temporal son insuficientes. En 2022 el
gate además permanece expuesto a semanas fuertemente negativas.

## Selección dentro del gate

Los seis factores terminaron con `anios_aptos=0/4`. Ninguno agregó alpha
estable sobre el benchmark sujeto al mismo gate.

Ejemplos:

- MOM1 2024: portfolio activo +302,09 bps y exceso +147,77 bps, pero exceso
  positivo solo 53,85% de semanas, 6 meses y 1 fold; no es estable.
- RMOM1 2025: portfolio activo +88,56 bps y exceso +49,76 bps, pero solo 15
  semanas activas, 4 meses positivos y 2 folds; no supera los criterios.
- RMOM3 2023: portfolio activo +74,37 bps y exceso +30,62 bps, pero hit-rates de
  44%/40% y estabilidad insuficiente.

## Conclusión

v11-v13 muestran que cambiar top-1 por top-5 y añadir un gate basado en el
mismo momentum de precio no resuelve el problema. La familia precio/momentum
puro queda cerrada: no se probarán retrospectivamente otros top-k ni umbrales
MOM3 para rescatarla.

## Siguiente dirección permitida

La siguiente hipótesis deberá introducir una fuente de información realmente
nueva y disponible antes de la decisión. Candidatos a verificar contra fuentes
oficiales de Binance: posicionamiento/derivados (funding, open interest, basis o
flujo) y/o microestructura histórica. Antes de programar v14 se confirmará
qué datos históricos públicos existen y su granularidad/cobertura.
