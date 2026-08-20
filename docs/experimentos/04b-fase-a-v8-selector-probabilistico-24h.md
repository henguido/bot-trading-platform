# BOT 2.0-04B-v8 — Selector probabilístico 24 h

Estado: **falsado en desarrollo**.

## Veredicto

```text
SELECTOR_V8_FALSADO_DESARROLLO
```

v8 intentó convertir el presupuesto de selección detectado por v7 en una regla
empírica y abstencionista a 24 h. Cada celda estimaba simultáneamente:

```text
retorno bruto medio esperado a 24 h
P(retorno bruto > 25 bps)
```

Una observación solo podía ser candidata si:

```text
retorno esperado > 25 bps
P(retorno > 25 bps) >= 0.55
soporte suficiente en muestras/símbolos/timestamps
```

Se evaluaron 32 configuraciones predeclaradas. **0/32** superaron todos los
criterios y **0/32** formaron una familia robusta.

## Ejecución auditada

- Rama: `agent/bot-2.0-04b8-selector-probabilistico-24h`.
- Head evaluado: `99e620149fb485968b23398d3b0b7884c879c819`.
- Draft PR: `#8`.
- CI run: `32386685403`, conclusión `success`.
- Suite: **974 passed**, 1391 warnings.
- `compileall backend`: OK.
- Frontend build: OK, 841 módulos.
- Artifact: `selector-v8-desarrollo-2025`, id `9413436197`.
- Digest: `sha256:47d78c4af43ff9541ea0614928ca27cc931f426945f2a70d4f0c516f59691e1d`.
- Dataset: 2022-01-01 a 2025-12-31.
- Símbolos útiles: 20/20.
- Observaciones selector: 174.360.
- Enero-abril 2026: no usado por v8.
- Mayo-julio 2026: cerrado.

## Grid

```text
rank_bins:       3 / 4
regimen_bins:    3 / 4
dispersion_bins: 3 / 4
min_muestras:    60 / 120
max_radio:       0 / 1
```

Total: **32 configuraciones**.

## Resultado agregado

| Métrica | Valor |
|---|---:|
| configuraciones | 32 |
| superan todos los criterios | 0 |
| robustas | 0 |
| retorno neto medio mínimo | aprox. -99,53 bps |
| retorno neto medio mediano | aprox. -44,28 bps |
| retorno neto medio máximo | aprox. +33,45 bps |
| señales mínimas | 0 |
| señales medianas | 67 |
| señales máximas | 140 |
| hit-rate mínimo | 37,5 % |
| hit-rate mediano | aprox. 46,0 % |
| hit-rate máximo | **54,545 %** |
| configs con media neta > 0 | 3 |
| configs con >=100 señales | 8 |
| configs con hit-rate >=55 % | **0** |
| configs con >=8 meses netos positivos | 1 |
| configs con >=3 folds netos positivos | **0** |

## Motivos de rechazo

Conteo sobre las 32 configuraciones:

| Motivo | Configuraciones |
|---|---:|
| `HIT_RATE_INSUFICIENTE` | **32** |
| `ESTABILIDAD_FOLDS_INSUFICIENTE` | **32** |
| `ESTABILIDAD_MENSUAL_INSUFICIENTE` | 31 |
| `RETORNO_NETO_NO_POSITIVO` | 29 |
| `SENALES_INSUFICIENTES` | 24 |
| `COBERTURA_MENSUAL_INSUFICIENTE` | 12 |
| `COBERTURA_FOLDS_INSUFICIENTE` | 11 |

## Las tres configuraciones con media neta positiva

### A

```text
rank_bins=3
regimen_bins=3
dispersion_bins=3
min_muestras=120
max_radio=0
```

- 8 señales;
- retorno neto medio aprox. +33,45 bps;
- hit-rate 37,5 %;
- 2 meses positivos;
- 1 fold positivo.

La muestra es demasiado pequeña e inestable.

### B — la más cercana a los criterios

```text
rank_bins=3
regimen_bins=4
dispersion_bins=4
min_muestras=60
max_radio=0
```

- 66 señales;
- retorno neto medio aprox. **+24,92 bps**;
- hit-rate **54,545 %**;
- cobertura 12/12 meses;
- 9 meses netos positivos;
- cobertura 4/4 folds;
- solo **2/4 folds** netos positivos.

No se permite cambiar retrospectivamente:

```text
100 señales -> 66
55 % hit-rate -> 54,545 %
3 folds positivos -> 2
```

para rescatar esta configuración.

### C

```text
rank_bins=3
regimen_bins=4
dispersion_bins=3
min_muestras=120
max_radio=1
```

- 57 señales;
- retorno neto medio aprox. +14,47 bps;
- hit-rate 52,63 %;
- 6 meses positivos;
- 2 folds positivos.

## Interpretación

v7 demostró que existe dispersión cross-sectional suficiente para selección,
pero v8 demuestra que la discretización por celdas de las features actuales no
la captura de forma estable. El problema no parece ser simplemente el threshold:

- todas las configuraciones fallan hit-rate;
- todas fallan estabilidad trimestral;
- 29/32 pierden dinero neto;
- ninguna configuración aprobada tiene vecinos robustos porque ninguna aprueba.

La siguiente investigación no debe ampliar el grid ni añadir un modelo más
complejo inmediatamente. Primero debe medir si cada feature individual tiene
una relación monotónica y estable con el retorno futuro a 24 h.

## Siguiente experimento permitido

04B-v9: diagnóstico de factores simples, sin predictor entrenado.

Para cada factor contemporáneo:

```text
rank retorno 4 h
rank retorno 24 h
rank sorpresa de volumen 4 h
```

se medirán:

- IC cross-sectional por timestamp;
- spread de retorno futuro top-vs-bottom;
- estrategia top-1 por factor en orientación alta y baja;
- estabilidad mensual/trimestral;
- resultado neto después del hurdle de 25 bps.

El objetivo es determinar si existe momentum, reversión o ninguna señal
monotónica. Si ninguna feature es estable, un modelo más complejo sobre las
mismas variables probablemente solo aprendería ruido.

Mayo-julio 2026 permanece cerrado.
