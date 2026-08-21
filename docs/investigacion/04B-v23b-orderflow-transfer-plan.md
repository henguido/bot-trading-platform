# BOT 2.0 — 04B-v23b dimensionamiento de transferencia Order Flow

## Estado

**PREDECLARADO — tamaños remotos todavía no observados al fijar este protocolo.**

v23 confirmó cobertura mensual de AggTrades y v23a validó contenido real. v23b no prueba rentabilidad ni descarga trades: dimensiona exactamente cuánto pesa el calendario candidato para una futura hipótesis económica v24.

## Calendario fijado

- mercado: Spot;
- universo: los 20 símbolos fijos heredados de 04B-v2;
- periodo: 2022-01-01 a 2025-12-31;
- fechas: primer y tercer lunes UTC de cada mes;
- 96 fechas;
- 20 símbolos por fecha;
- 1.920 ZIP diarios objetivo.

Las fechas no se sustituyen por otras según tamaño, actividad, volatilidad o disponibilidad posterior. Si el plan supera el presupuesto de CI, se conserva el mismo calendario y solo cambia el mecanismo de adquisición/caché.

## Gate de cobertura

El plan es técnicamente apto únicamente si:

- los 20 listados S3 terminan completamente;
- al menos 95% de los 1.920 archivos objetivo están presentes;
- las 96 fechas conservan al menos 15 símbolos cada una;
- no existen objetos duplicados para el mismo símbolo/fecha;
- ningún objeto objetivo tiene tamaño cero.

## Presupuesto de ingeniería

Antes de observar tamaños se fija un máximo de **15 GiB comprimidos** para ejecutar una futura descarga completa dentro del job estándar de CI.

El presupuesto no es un gate de datos. Si cobertura/calidad pasan pero el total excede 15 GiB, el resultado será `PLAN_TRANSFERENCIA_APTO_FUERA_CI_V23B`: v24 deberá materializar/cachar por lotes sin cambiar calendario.

Si cobertura/calidad pasan y el total cabe en 15 GiB, el resultado será `PLAN_TRANSFERENCIA_APTO_CI_V23B`.

## Prohibiciones

- no descargar contenido AggTrades;
- no calcular imbalance;
- no retornos;
- no labels;
- no correlaciones;
- no ranking económico;
- no selección de fechas post hoc;
- no imputación;
- no GPT;
- no scanner;
- no RiskEngine;
- no PAPER operativo;
- no LIVE;
- no Render;
- 2026 cerrado;
- mayo-julio 2026 cerrado.

## Decisión posterior

Solo si v23b pasa cobertura se podrá predeclarar v24. v24 deberá fijar antes de descargar contenido: feature exacta de order flow, neutralización/control por retorno contemporáneo, horizonte, selección cross-sectional, baseline, hurdle total y criterios temporales de estabilidad.
