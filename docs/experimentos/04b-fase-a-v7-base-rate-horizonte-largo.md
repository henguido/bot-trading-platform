# BOT 2.0-04B-v7 — Diagnóstico base-rate de horizonte largo

Estado: diagnóstico completado.

## Veredicto

```text
PRESUPUESTO_PARA_SELECCION_V7
```

Ninguno de los horizontes 24/48/72 h produjo un baseline long equal-weight
neto y estable. Sin embargo, los tres cumplieron los criterios predeclarados de
`SELECCION_POTENCIAL`: el mejor activo ex-post por timestamp tuvo holgura muy
superior al hurdle y la dispersión cross-sectional fue amplia.

La regla predeclarada eligió **24 h** por ser el horizonte más corto entre los
que pertenecen a la misma clase.

Este resultado NO demuestra que exista un predictor capaz de escoger el activo
correcto. El oracle top-1 es un techo ex-post, no una estrategia.

## Ejecución auditada

- Rama: `agent/bot-2.0-04b7-base-rate-horizonte-largo`.
- Head: `5428c2d5af51fd75878c465c9de998ac334c7094`.
- CI run: `32383447997`.
- CI: success.
- Artifact: `edge-base-rate-v7-desarrollo-2025`, id `9412056161`.
- Digest: `sha256:aecbdf91efe52dc73bc4ca8ee5fbd13b9b441a462be8314fae4b16025f739d6c`.
- Dataset: 2022-01-01 a 2025-12-31.
- Símbolos útiles: 20/20.
- Observaciones relativas: 174.120.
- Enero-abril 2026: no usado por v7.
- Mayo-julio 2026: cerrado.

## Resultado 24 h — régimen no negativo

| Métrica | Valor |
|---|---:|
| observaciones | 14.100 |
| timestamps | 705 |
| retorno bruto medio | +4,1567 bps |
| retorno neto medio después de 25 bps | **-20,8433 bps** |
| fracción observaciones que cubren hurdle | 44,65 % |
| MFE p50 | +209,97 bps |
| MAE p50 | -223,44 bps |
| baseline timestamp neto medio | **-20,8433 bps** |
| timestamps baseline neto positivo | 47,52 % |
| meses 2025 baseline neto positivo | 5/12 |
| folds 2025 baseline neto positivo | 1/4 |
| oracle top-1 neto medio | **+642,76 bps** |
| timestamps oracle neto positivo | **88,79 %** |
| meses 2025 oracle neto positivo | 12/12 |
| dispersión mediana p75-p25 | **211,58 bps** |

## Lectura económica

La evidencia descarta una estrategia de comprar el mercado de forma amplia. El
promedio long no paga el hurdle. Pero el diferencial entre activos dentro del
mismo timestamp es mucho mayor que los costes asumidos: existe un gran techo de
selección ex-post.

Eso justifica una pregunta nueva y más difícil:

```text
¿podemos predecir cuál activo, entre los disponibles en t,
tiene probabilidad y retorno esperado suficientes para superar 25 bps a 24 h?
```

No justifica:

- escoger retrospectivamente el oracle;
- bajar costes;
- abrir 2026;
- conectar 04C;
- operar PAPER/LIVE.

## Próximo experimento permitido

04B-v8 debe ser una familia **selectiva** a 24 h y predecir directamente una
variable económicamente alineada, no solo ranking relativo:

- retorno absoluto esperado a 24 h;
- probabilidad de retorno bruto > 25 bps;
- máximo una señal por timestamp;
- abstención si no hay soporte o probabilidad/edge suficiente.

2025 ya fue observado durante v1-v7 y por tanto forma parte de desarrollo. El
único holdout final no observado sigue siendo mayo-julio 2026.
