# BOT 2.0 — 04D-3 resultado

## Veredicto final

`CARRY_NO_RESCATABLE_SIN_LEVERAGE_04D3`

04C-2 conserva una prima económica, pero **no puede superar los gates productivos vigentes sin cambiar la estrategia o permitir borrowing/leverage adicional**.

## Prueba

Inputs heredados y congelados de 04C-2:

- retorno neto 2022 sobre notional: **1.2413%**;
- gate de producción para peor año sobre capital committed: **>=2.00%**;
- no excluir retrospectivamente 2022;
- no leverage/borrowing adicional.

Para mantener la pata long Spot sin borrowing, el capital cash requerido es al menos `1.0x` el notional Spot.

En el límite más favorable imaginable para collateral compartido, suponiendo **cero capital marginal** requerido por la pata short Futures:

`retorno_committed_max_2022 = 1.2413% / 1.0 = 1.2413%`

Como `1.2413% < 2.00%`, el gate de peor año es matemáticamente imposible de superar bajo 04C-2 sin leverage o una fuente adicional de retorno.

Maintenance margin, fees, haircuts y buffers reales no pueden mejorar esta cota; solo pueden mantenerla o empeorarla.

## CI

Workflow `research-04d3`:

- methodology locks: success;
- unit test: 1/1 passed;
- capital-bound proof: success;
- artefacto: `capital-bound-proof-04d3`;
- artifact ID: `9460342859`;
- SHA256 ZIP: `f4460f669603d51da642258ca0b0b11ea48fa01ef2760b607f1deafa7ff89b10`.

Salida auditada:

- notional 2022: 1.2413%;
- capital mínimo: 1.0000x;
- retorno committed máximo: 1.2413%;
- gate: 2.00%;
- `gate_superable=False`.

## Consecuencias

1. 04D-2 ya no bloquea el veredicto productivo de 04C-2. Metadata de cuenta sigue siendo útil para ingeniería futura, pero no puede rescatar este gate sin leverage.
2. No se debe seguir optimizando 04C-2 ni cambiar su denominator para presentarlo como producción apta.
3. Cualquier siguiente estrategia debe añadir **una fuente de retorno nueva y predeclarada** o pertenecer a otra familia económica; no puede ser un ajuste retrospectivo de 04C-2.
4. PAPER operativo y LIVE permanecen cerrados.
5. 2026 permanece cerrado.
