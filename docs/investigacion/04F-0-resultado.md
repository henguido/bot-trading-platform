# BOT 2.0 — 04F-0 Resultado auditoría low-volatility

## Veredicto

`ARCHIVO_LOW_VOL_INVENTARIO_APTO_04F0`

La infraestructura histórica pública es suficientemente amplia para continuar a una auditoría de contenido/elegibilidad sin usar la lista actual de símbolos.

## Resultado real

- prefixes Spot históricos: **3.695**;
- prefixes terminados en USDT: **723**;
- listados USDT completos: **723/723**;
- ZIP mensuales `1d` en octubre 2021–diciembre 2025: **19.027**;
- tamaño comprimido agregado de esos ZIP: **0,030498 GiB**;
- meses de holding auditados: **48/48**;
- candidatos con 3 meses de formación + mes de holding: **mínimo 302, máximo 421**;
- gate predeclarado: mínimo 100 en cada mes;
- motivos de rechazo: **ninguno**.

No se consultó `exchangeInfo` actual para construir el universo. Por tanto, los conteos no eliminan automáticamente símbolos históricos que fueron delistados después.

## Qué se observó y qué no

04F-0 leyó únicamente metadata S3.

No se descargó contenido de klines, no se calculó volatilidad, no se calculó retorno futuro, no se formó ninguna cartera y no se observó PnL.

Por ello este resultado no demuestra que la anomalía low-volatility exista en el proyecto. Solo elimina el riesgo de que la prueba sea inviable por falta de amplitud histórica.

## Evidencia

- workflow `research-04f0` run #1: **success**;
- tests específicos: **5/5 passed**;
- CI general #134: **success**;
- artifact: `low-vol-data-audit-04f0`;
- artifact ID: `9468681154`;
- artifact SHA256: `a224973ba2821483eb2870f0181ef013db758542b4b53e21f9951781ce842622`.

## Siguiente gate

04F-1 deberá seguir sin PnL de cartera y resolver antes de cualquier ranking económico:

1. cobertura diaria real dentro de los ZIP;
2. timestamps/unidades y ausencia de duplicados;
3. reglas explícitas para stablecoins y tokens apalancados/no comparables;
4. filtro de liquidez calculado únicamente con información anterior al rebalanceo;
5. cantidad de símbolos que sobreviven por mes;
6. tamaño de transferencia necesario para una eventual réplica económica.

No se reducirá retrospectivamente la ventana de 3 meses, el holding de 1 mes ni el periodo 2022-2025 para rescatar cobertura.

Cierre previsto: sin merge, sin PAPER operativo, sin LIVE, sin Render y con 2026 cerrado.
