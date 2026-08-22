# BOT 2.0 — 04E-1 Resultado Spot + short USD-M quarterly

## Veredicto

- `SPOT_QUARTERLY_ECONOMICAMENTE_FALSADO_04E1`
- `SPOT_QUARTERLY_NO_CANDIDATO_PRODUCCION_04E1`

04E-1 fue predeclarado antes de observar PnL. No se modificaron retrospectivamente horizonte, coste, selector, signo ni gates.

## Protocolo congelado

- Activos: BTCUSDT y ETHUSDT.
- Periodo: 2022-2025; 2026 cerrado.
- 4 vencimientos trimestrales por año; 32 oportunidades totales.
- Entrada: exactamente 28 días antes de delivery.
- Estrategia: long Spot + short USD-M quarterly.
- Selector: `entry_basis - 0.006 > 0`.
- Coste conservador: 60 bps por round-trip completo de ambas patas.
- Sin leverage adicional, imputación, cambio retrospectivo de signo o optimización de horizonte/coste.
- Capital 1x usado solo como cota optimista de screening, no como afirmación de viabilidad de margin/collateral.

## Datos y ejecución

- Inputs históricos: 32/32.
- Errores: 0.
- Cobertura horaria de stress: >=99.8512% en todas las oportunidades y 100% en la mayoría.
- Oportunidades elegibles: 9/32.
- Win rate de trades elegibles: 66.6667%.

## Retorno anual del portafolio

| Año | Retorno |
|---|---:|
| 2022 | 0.0000% |
| 2023 | -0.2870% |
| 2024 | 1.1195% |
| 2025 | -0.0507% |

Métricas agregadas:

- Media anual: 0.1955%.
- Peor año: -0.2870%.
- Sharpe trimestral: 0.4538.
- Max drawdown: 0.2870%.
- Peor stress intratrade: -1.3457%.

## Rechazos económicos

- `NO_4_DE_4_ANIOS_POSITIVOS`.
- `SHARPE_ECONOMICO_INSUFICIENTE`.

## Rechazos para producción

- `GATE_ECONOMICO_NO_SUPERADO`.
- `MEDIA_ANUAL_MENOR_5PCT`.
- `PEOR_ANIO_MENOR_2PCT`.
- `SHARPE_PRODUCCION_MENOR_1_5`.

## Evidencia reproducible

Workflow `research-04e1`: success.

- Locks metodológicos: success.
- Tests específicos: 4/4 passed.
- Réplica histórica fija: success técnico.
- Artifact: `spot-quarterly-04e1-2022-2025`.
- Artifact ID: `9460620999`.
- SHA256: `97a39d8cacd3be4a13c2029cf986cb8ae3c943d3de3c31b17775d9494ff817e7`.
- CI general del commit pre-resultado: success, incluida suite Python, compileall y frontend build.

## Interpretación

Eliminar el funding de la pata perpetual de 04C-3 no rescata la familia de basis trimestral. El quarterly-Spot basis observado a 28 días no aporta una prima neta suficientemente grande ni estable después del coste predeclarado de 60 bps.

El hecho de que 04E-1 falle incluso bajo capital 1x optimista hace innecesario un audit de margin/collateral para esta hipótesis concreta: mejorar la arquitectura de collateral no puede convertir estas métricas económicas en los gates exigidos sin cambiar metodología o añadir otra fuente de yield.

No se deben probar retrospectivamente otros horizontes, bajar costes, excluir años ni añadir leverage para rescatar 04E-1. Cierre: investigación falsada; no mergear a `main`, no PAPER operativo y no LIVE.
