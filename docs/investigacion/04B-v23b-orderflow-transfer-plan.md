# BOT 2.0 — 04B-v23b dimensionamiento de transferencia Order Flow

## Estado

**CERRADO — `PLAN_TRANSFERENCIA_APTO_CI_V23B`.**

v23 confirmó cobertura mensual de AggTrades y v23a validó contenido real. v23b no probó rentabilidad ni descargó trades: dimensionó exactamente cuánto pesa el calendario candidato para una futura hipótesis económica v24.

## Calendario fijado antes del resultado

- mercado: Spot;
- universo: los 20 símbolos fijos heredados de 04B-v2;
- periodo: 2022-01-01 a 2025-12-31;
- fechas: primer y tercer lunes UTC de cada mes;
- 96 fechas;
- 20 símbolos por fecha;
- 1.920 ZIP diarios objetivo.

Las fechas no se sustituyeron según tamaño, actividad, volatilidad o disponibilidad posterior.

## Gate predeclarado

El plan era técnicamente apto únicamente si:

- los 20 listados S3 terminaban completamente;
- al menos 95% de los 1.920 archivos objetivo estaban presentes;
- las 96 fechas conservaban al menos 15 símbolos cada una;
- no existían objetos duplicados para el mismo símbolo/fecha;
- ningún objeto objetivo tenía tamaño cero.

Antes de observar tamaños se fijó además un máximo de **15 GiB comprimidos** para permitir una futura descarga completa dentro del job estándar de CI. El presupuesto nunca autorizó modificar el calendario.

## Resultado remoto

Resultado: **`PLAN_TRANSFERENCIA_APTO_CI_V23B`**.

- listados S3 completos: **20/20**;
- ZIP diarios presentes: **1.920/1.920**;
- fechas aptas: **96/96**;
- símbolos por fecha: **20–20**, por lo que todas las fechas tienen el universo completo;
- tamaño comprimido exacto del calendario: **7.617537 GiB**;
- presupuesto CI predeclarado: **15 GiB**;
- entra en CI: **sí**;
- motivos de rechazo: **ninguno**.

La ejecución solo leyó metadatos de S3. No descargó el contenido de los ZIP, no calculó imbalance y no observó retornos.

## Incidencia de ingeniería

El primer run falló antes de producir datos por `ModuleNotFoundError: No module named 'backend'` al ejecutar directamente el runner dentro de `scripts/`. Se corrigió únicamente la inserción de la raíz del repositorio en `sys.path`, usando el patrón ya existente en otros runners del proyecto. No se modificó ninguna fecha, símbolo, gate ni presupuesto.

El segundo run, con exactamente el mismo protocolo, terminó correctamente.

## Evidencia de CI

- workflow `research-04b-v23b` run #2: **success**;
- artifact: `orderflow-transfer-plan-v23b-2022-2025`;
- artifact id: `9452276151`;
- digest: `sha256:93fc8bda4d16c694534fa3fdac5051cc88ba2f263a9a56678d10536a0914f4e9`;
- CI general #87: **success**;
- pytest: **1131 passed**;
- `compileall backend`: OK;
- frontend Vite: **841 módulos**;
- auditoría v20.1: revalidada y apta.

## Prohibiciones mantenidas

- no contenido AggTrades;
- no imbalance;
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

v23b habilita técnicamente predeclarar v24 con el mismo calendario fijo. v24 deberá fijar antes de descargar contenido: feature exacta de order flow, control por retorno contemporáneo, horizonte, selección cross-sectional, baseline, hurdle total y criterios temporales de estabilidad.
