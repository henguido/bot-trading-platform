# BOT 2.0 — 04D-3: cota de capital del carry 04C-2

## Objetivo

Cerrar una duda que 04D-2 no necesita resolver con metadata privada: ¿puede una arquitectura de collateral compartido rescatar 04C-2 bajo los gates productivos actuales **sin borrowing/leverage adicional**?

## Inputs heredados y no ajustables

De 04C-2:

- retorno neto del portafolio BTC+ETH sobre notional en 2022: **1.2413%**;
- gate productivo de peor año committed: **>=2%**;
- 2022 no puede excluirse retrospectivamente;
- no se permite leverage adicional.

## Cota

Para ejecutar `long Spot + short perpetual` sin borrowing de la pata Spot, comprar Spot cash exige al menos el mismo capital que su notional:

`capital_committed >= 1.0 * notional`

Aun suponiendo el caso imposiblemente favorable de que la pata short Futures requiriera **cero capital marginal**, el retorno committed máximo de 2022 sería:

`1.2413% / 1.0 = 1.2413%`

Eso es estrictamente menor que el gate de 2%.

Cualquier maintenance margin, haircut, fee, buffer o capital Futures positivo solo aumenta el denominador y reduce el retorno committed.

## Implicación

Cross Margin, Multi-Assets Mode o Portfolio Margin pueden resolver el problema de supervivencia de la pata short al reconocer collateral compartido. Sin embargo, **no pueden elevar el retorno económico de 2022 por encima del retorno notional** sin introducir borrowing/leverage o una fuente adicional de yield.

Por tanto, bajo la estrategia 04C-2 tal como fue definida y los gates vigentes:

`CARRY_NO_RESCATABLE_SIN_LEVERAGE_04D3`

## Qué no demuestra

- No dice que funding carry no tenga prima económica.
- No dice que collateral compartido no sea técnicamente útil.
- No impide estudiar otra estrategia que añada una fuente de retorno independiente, siempre que se predeclare como hipótesis nueva.
- No autoriza excluir 2022, bajar el gate o añadir leverage para salvar 04C-2.

## Consecuencia para 04D-2

La metadata privada de fees/brackets/margin mode sigue siendo útil si en el futuro se quiere implementar un carry distinto o un PAPER shadow exploratorio. Pero **ya no es necesaria para decidir si 04C-2 pasa producción**: matemáticamente no puede superar el gate de peor año sin cambiar la estrategia o permitir leverage.

## Seguridad

- sin credenciales;
- sin red;
- sin órdenes;
- sin PAPER operativo;
- sin LIVE;
- sin Render;
- 2026 cerrado.
