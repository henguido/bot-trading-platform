# BOT 2.0 — Resultado 04C-2

## Veredicto

**CARRY_ECONOMICAMENTE_APTO_04C2**

**CARRY_NO_CANDIDATO_PRODUCCION_04C2**

04C-2 confirma que el carry long Spot + short USD-M perpetual BTC/ETH contiene una prima económica robusta en 2022-2025 bajo el protocolo congelado, pero no alcanza el gate mínimo de producción sobre el capital de referencia 2x. No se modifica ningún threshold y no se autoriza PAPER operativo ni LIVE.

## Integridad de datos

- BTCUSDT: 4,383/4,383 settlements alineados, cobertura 100%, cero gaps.
- ETHUSDT: 4,383/4,383 settlements alineados, cobertura 100%, cero gaps.
- Funding interval: 8h en los 4,383 settlements por activo de esta muestra.
- El fallback diario oficial de `markPriceKlines` recuperó exclusivamente las horas faltantes detectadas por la auditoría temporal.
- Sin interpolación, imputación, API keys, 2026 ni selección por signo de funding.

## Resultados anuales por activo

| Año | BTC neto notional | BTC committed 2x | ETH neto notional | ETH committed 2x |
|---|---:|---:|---:|---:|
| 2022 | 2.1646% | 1.0823% | 0.3180% | 0.1590% |
| 2023 | 14.0836% | 7.0418% | 12.2957% | 6.1478% |
| 2024 | 18.8252% | 9.4126% | 18.0084% | 9.0042% |
| 2025 | 5.1331% | 2.5666% | 4.1823% | 2.0912% |

## Portafolio BTC+ETH equal-weight

| Año | Neto notional | Neto sobre capital 2x | Funding |
|---|---:|---:|---:|
| 2022 | 1.2413% | 0.6207% | 1.8432% |
| 2023 | 13.1897% | 6.5948% | 13.9683% |
| 2024 | 18.4168% | 9.2084% | 18.9049% |
| 2025 | 4.6577% | 2.3289% | 5.2443% |

Resumen:

- media anual neta sobre notional: **9.3764%**;
- media anual sobre capital de referencia 2x: **4.6882%**;
- peor año committed: **0.6207%**;
- Sharpe diario neto: **10.3481**;
- max drawdown diario neto: **0.8881%**;
- peor día: **-0.3028%**;
- días positivos: **76.80%**.

## Gate económico

Superado:

- 4/4 años net-positive;
- media anual neta >0;
- Sharpe >=1;
- drawdown <=10%;
- funding agregado >0.

Por tanto: **CARRY_ECONOMICAMENTE_APTO_04C2**.

## Gate de producción

No superado por exactamente dos razones predeclaradas:

1. media committed 4.6882% < 5%;
2. peor año committed 0.6207% < 2%.

Sharpe y drawdown sí superaron sus requisitos con margen amplio.

No se reducen thresholds, no se añade leverage y no se elimina 2022.

## Interpretación para la siguiente etapa

El cuello de botella no es la existencia de edge; es convertirlo en una estructura con rentabilidad suficiente sobre capital efectivo sin elevar de forma inaceptable riesgo de liquidación, margen, pata incompleta o exchange.

Reducir únicamente el margen Futures no puede rescatar 2022: aun con capital Futures hipotéticamente cero, el notional Spot mínimo seguiría dejando al portafolio 2022 en 1.2413%, por debajo del gate de 2%.

Por eso la siguiente investigación no debe modificar retrospectivamente 04C-2. Debe probar una estructura económicamente distinta con mejor eficiencia de capital y carry propio, manteniendo BTC/ETH y Binance: un calendar spread entre perpetual y futuro trimestral es el candidato 04C-3.

## Estado de seguridad

- `main` permanece intacto.
- PR de investigación temporal; cerrar sin merge.
- PAPER operativo no autorizado.
- LIVE cerrado.
- Render sin cambios.
- 2026 holdout cerrado.
