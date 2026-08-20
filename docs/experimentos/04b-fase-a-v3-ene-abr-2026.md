# BOT 2.0-04B - Fase A v3: resultado cost-aware enero-abril 2026

## Veredicto

**04B-v3 queda falsada para operacion.**

La familia v3 hizo una pregunta mas estricta que v2: tomar solamente senales
cuyo edge predicho superara un hurdle economico fijo de **25 bps**:

```text
20 bps coste round-trip minimo
+ 5 bps margen de seguridad
= 25 bps hurdle predicho
```

El resultado fue:

```text
SIN_CONFIGURACIONES_COST_AWARE_V3
```

Ninguna de las 4 configuraciones predeclaradas supero los criterios netos.

## Candados cumplidos

- Mayo-julio 2026 sigue cerrado.
- Dataset hasta: 2026-04-30T23:59:59.999Z.
- Test final desde: 2026-05-01T00:00:00Z.
- `test_may_jul_open=false`.
- Sin Claude.
- Sin LIVE.
- Sin Render.
- Sin ordenes.
- Sin RiskEngine.
- Sin GPT/OpenAI.
- Solo datos publicos Spot.

## Dataset

| metrica | valor |
| --- | ---: |
| simbolos utiles | 20/20 |
| observaciones relativas | 188.760 |
| observaciones pre-test | 188.760 |
| configuraciones evaluadas | 4 |
| configuraciones aptas | 0 |

## Familia evaluada

La familia v3 no expandio la busqueda. Uso el cluster robusto v2:

| parametro | valores |
| --- | --- |
| horizonte | 8h |
| rank_bins | 3 |
| regimen_bins | 3 |
| min_muestras | 30 / 60 |
| max_radio | 0 / 1 |
| coste total | 20 bps |
| margen | 5 bps |
| hurdle predicho | 25 bps |
| senales por timestamp | 1 |

## Resultado comun de las 4 configuraciones

Las 4 variantes dieron el mismo resumen cost-aware:

| metrica | valor |
| --- | ---: |
| timestamps evaluables | 357 |
| timestamps con senal | 54 |
| senales | 54 |
| cobertura de senal | 15,126 % |
| retorno bruto medio de senales | -14,791807 bps |
| retorno neto medio, solo costes | -34,791807 bps |
| retorno neto medio despues de margen | -39,791807 bps |
| baseline bruto mismo timestamp | -26,926081 bps |
| uplift bruto vs baseline | +12,134274 bps |
| timestamps neto despues de margen positivo | 42,593 % |
| timestamps con uplift positivo | 55,556 % |
| meses con senal | 4 |
| meses netos positivos | 2 |
| folds con senal | 4 |
| folds netos positivos | 2 |

## Motivos de rechazo

Cada configuracion fallo por los mismos 4 motivos:

```text
RETORNO_NETO_NO_CUBRE_COSTES
NETO_INESTABLE_TIMESTAMPS
NETO_INESTABLE_MENSUAL
NETO_INESTABLE_FOLDS
```

Conteo:

| motivo | configs |
| --- | ---: |
| `RETORNO_NETO_NO_CUBRE_COSTES` | 4 |
| `NETO_INESTABLE_TIMESTAMPS` | 4 |
| `NETO_INESTABLE_MENSUAL` | 4 |
| `NETO_INESTABLE_FOLDS` | 4 |

## Interpretacion

v3 confirma algo importante: el modelo puede mejorar la seleccion relativa en
ciertos timestamps, porque el uplift contra el baseline contemporaneo fue
positivo. Pero eso no basta para operar.

El caso principal fue:

```text
baseline del timestamp      -26,93 bps
senal seleccionada          -14,79 bps
uplift relativo             +12,13 bps
neto despues de costes      -34,79 bps
neto despues de margen      -39,79 bps
```

Es decir: el selector perdio menos que el mercado contemporaneo, pero siguio
perdiendo. Un EconomicGate operativo basado en esta familia rechazaria la
mayoria de oportunidades o aceptaria senales con esperanza neta negativa.

## Decision

No avanzar a 04C operativo.

No abrir mayo-julio 2026 para rescatar v3.

No conectar v3 a `main.py`, scanner, GPT, RiskEngine ni PAPER/LIVE.

## Siguiente investigacion

El fallo apunta a que el problema no es solo ranking cross-sectional. Hace falta
evitar operar cuando el regimen de mercado deja retorno absoluto negativo.

El siguiente diseno deberia volver a desarrollo historico y predeclarar una
familia nueva, por ejemplo:

```text
04B-v4 = edge relativo + filtro de regimen absoluto
```

Ese filtro debe disenarse sin abrir mayo-julio 2026. Tambien conviene evitar
usar enero-abril 2026 como terreno de ajuste fino, porque ya fue observado en
v2/v3.
