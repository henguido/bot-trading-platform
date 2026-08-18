# BOT 2.0-04B-v5 - Diagnostico desarrollo 2025

Estado: diagnostico completado.

Commit de protocolo prediagnostico:

```text
1a8ad09 feat(economia): diagnostica hurdle en desarrollo
```

## Alcance

- dataset descargado: 2022-01-01 a 2025-12-31;
- folds evaluados: 2025-Q1, 2025-Q2, 2025-Q3, 2025-Q4;
- enero-abril 2026: no abierto para este diagnostico;
- mayo-julio 2026: cerrado;
- modo: offline/PAPER;
- sin GPT, sin scanner operativo, sin RiskEngine, sin ordenes, sin LIVE y sin
  Render.

## Resultado

```text
SENALES_HURDLE_SOLO_EN_REGIMENES_NO_APROBADOS_DESARROLLO
```

- simbolos utiles: 20/20;
- observaciones relativas: 174.360;
- configuraciones: 4;
- configuraciones con senal cost-aware sin filtro de regimen: 4/4;
- configuraciones con senal cost-aware despues de regimen no negativo: 0/4.

## Metricas comunes a las 4 configuraciones

Modelo:

```text
folds disponibles: 4/4
objetivo: 21.840
estimadas: 21.840
cobertura: 1
uplift cross-section medio: -0.00004939775302443341459882139190
fraccion timestamps uplift positivo: 0.4835164835164835164835164835
meses cross-section: 12
meses uplift positivo: 5
```

Distribucion de edge predicho:

```text
predicciones: 21.840
regimen no negativo: 10.940
regimen negativo: 10.900
predicciones >= 25 bps: 824
predicciones >= 25 bps en regimen no negativo: 0
predicciones >= 25 bps en regimen negativo: 824
p50 predicho: 2.149617808028871219373610843 bps
p75 predicho: 9.552971409158982644898971991 bps
p90 predicho: 17.13154110293738048622093306 bps
p95 predicho: 23.71991086609197741363790105 bps
p99 predicho: 31.60868915388569681351720419 bps
max predicho: 35.84679571053696656182352586 bps
max predicho en regimen no negativo: 17.81243543331298650392464829 bps
max predicho en regimen negativo: 35.84679571053696656182352586 bps
```

Cost-aware sin filtro de regimen:

```text
timestamps evaluables: 1.092
timestamps con senal: 353
senales: 353
cobertura timestamps senal: 32.32600732600732600732600733%
retorno bruto medio senales: 7.056339665805600669434548470 bps
retorno neto despues de margen: -17.94366033419439933056545153 bps
baseline bruto mismo timestamp: 2.589200612579295939296180487 bps
uplift bruto vs baseline: 4.467139053226304730138367980 bps
timestamps neto positivo despues de margen: 45.89235127478753541076487252%
meses con senal: 12
meses netos positivos: 5
```

Cost-aware con regimen no negativo:

```text
timestamps de entrada: 1.092
timestamps con regimen aprobado: 547
cobertura regimen: 50.09157509157509157509157509%
timestamps con senal: 0
senales: 0
```

## Interpretacion

El diagnostico no apoya una v5 basada en seguir filtrando la familia v2-v4. La
familia relativa no esta encontrando oportunidades long spot operables en
regimen no negativo. Cuando predice >= 25 bps, lo hace exclusivamente en
regimenes negativos, y aun sin el filtro de regimen el retorno neto despues de
coste y margen queda en -17.94 bps.

La lectura mas conservadora es:

```text
esta familia identifica activos que pueden perder menos que el mercado,
pero no una ventaja absoluta suficiente para comprar spot long.
```

## Decision

No procede una 04B-v5 que solo baje umbrales, cambie el corte de regimen o
agregue filtros encima de v2-v4. Eso seria optimizacion retrospectiva.

Para seguir en 04B se necesita una hipotesis realmente distinta y predeclarada,
por ejemplo:

- cambiar el label hacia retorno absoluto neto esperado;
- separar explicitamente mercado alcista, lateral y bajista desde desarrollo;
- modelar probabilidad de superar costes, no solo retorno medio;
- incorporar riesgo adverso MFE/MAE como parte del objetivo;
- estudiar si el bot debe abstenerse en spot cuando el edge relativo solo
  equivale a defensa contra caidas.

Mayo-julio 2026 sigue cerrado.

## Implicacion operativa

No hay autorizacion para 04C operativo con la familia v2-v4. Antes de operar
falta demostrar una familia con edge neto robusto y luego pasar por test final,
shadow/PAPER, costes reales, slippage, profundidad, limites de riesgo y
monitoreo.
