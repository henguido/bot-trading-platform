# BOT 2.0-04B-v5 - Protocolo diagnostico de desarrollo

Estado: diagnostico predeclarado antes de ejecutar datos 2025.

## Proposito

04B-v2 encontro uplift relativo bruto, pero 04B-v3 y 04B-v4 no produjeron una
familia operable despues de costes. v4 ademas mostro que, en enero-abril 2026,
el filtro de regimen no era el problema principal: dentro de regimen aprobado no
hubo senales sobre el hurdle de 25 bps.

Antes de inventar una v5 operativa, este diagnostico responde una pregunta mas
basica usando solo desarrollo:

```text
La familia v3/v4 tiene capacidad de generar predicciones >= 25 bps
en datos previos a 2026?
```

Y, si las tiene:

```text
esas predicciones aparecen en regimen de mercado no negativo
o solo en regimenes negativos?
```

## Periodo

Dataset:

```text
2022-01-01 a 2025-12-31
```

Folds de diagnostico:

```text
2025-Q1
2025-Q2
2025-Q3
2025-Q4
```

Candados:

- enero-abril 2026 no se abre para este diagnostico;
- mayo-julio 2026 sigue cerrado como holdout final;
- agosto 2026 no participa;
- sin LIVE, sin Render, sin GPT y sin ordenes.

## Familia evaluada

Se reusa exclusivamente la familia v4:

```text
horizonte: 8h
rank_bins: 3
regimen_bins: 3
min_muestras: 30 / 60
max_radio: 0 / 1
```

No hay grilla nueva.

## Metricas

Para cada configuracion:

- distribucion de edge predicho en bps: p50, p75, p90, p95, p99, max;
- numero de predicciones >= 25 bps;
- numero de predicciones >= 25 bps en regimen no negativo;
- numero de predicciones >= 25 bps en regimen negativo;
- cost-aware sin filtro de regimen;
- cost-aware con regimen no negativo;
- cobertura de modelo;
- cobertura de senales;
- retorno neto despues de coste y margen;
- meses/folds con senal y estabilidad.

## Interpretacion permitida

Este diagnostico puede justificar una decision de direccion:

- si no hay capacidad de hurdle ni siquiera en desarrollo, no seguir exprimiendo
  esta familia;
- si solo hay capacidad en regimenes negativos, la familia parece describir
  activos que pierden menos que el mercado, no oportunidades long spot;
- si hay capacidad consistente en regimen no negativo, entonces se puede
  predeclarar una v5 real antes de volver a usar enero-abril 2026.

No esta permitido:

- bajar el hurdle de 25 bps;
- optimizar el umbral de regimen contra 2026;
- abrir mayo-julio 2026;
- conectar 04C, PAPER operativo o LIVE con esta evidencia.
