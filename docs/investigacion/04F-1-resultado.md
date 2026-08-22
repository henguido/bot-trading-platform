# BOT 2.0 — 04F-1 Resultado contenido/elegibilidad low-volatility

## Veredicto

`DATASET_LOW_VOL_ELEGIBILIDAD_NO_APTO_04F1`

04F-1 queda falsado como dataset productivo bajo los gates predeclarados, **antes de calcular volatilidad, ranking low-vol, retorno futuro o PnL**.

## Resultado real definitivo

Workflow final válido `research-04f1` #7, run `32547365434`, HEAD `4479947e2e653fcb5805727055e0bffcf943db8a`:

- prefixes históricos: 3.695;
- pares USDT: 723;
- listings completos: 723/723;
- archivos descargados: 18.124;
- barras diarias válidas: 545.937;
- contenido con errores: 0 archivos;
- tamaño comprimido: 0,029088 GiB;
- stable/fiat excluidos: 20;
- leveraged tokens explícitamente excluidos: 40;
- meses de holding: 48;
- elegibles mínimos por mes: **40**;
- elegibles máximos por mes: 237;
- único rechazo: `ELIGIBLES_2023_01_MENOR_50`.

Gate congelado: al menos 50 activos elegibles en **cada** uno de los 48 meses después de cobertura >=95%, al menos 27/30 días de liquidez, mediana de quote volume 30d >=5M USDT y barra disponible en el día de entrada.

## Robustez del fallo

La versión final usa una lista explícita de 40 BLVT históricos conocidos. Se detectó antes del primer resultado válido que una heurística por sufijo podía confundir `JUP` con un token `UP`; se corrigió antes de aceptar el resultado.

La lista explícita puede ser **más permisiva** que la exclusión histórica perfecta si faltara algún BLVT retirado. Por tanto, el conteo de 40 en enero de 2023 es una **cota superior** de elegibilidad: excluir correctamente cualquier BLVT adicional solo podría mantener o reducir ese número. No existe una corrección de clasificación que pueda elevarlo hasta 50.

Consecuencia: el fallo del gate no se rescata refinando la lista de leveraged tokens.

## Evidencia

- methodology locks: success;
- tests específicos: 4/4 passed;
- auditoría de contenido: success técnico;
- CI general del HEAD: success;
- artifact `low-vol-content-audit-04f1`;
- artifact ID `9469031649`;
- SHA256 `c625a37c68f83479ddd452ccb866d18559901f4e811353ae3c34e0cd109952a9`.

## Candados preservados

No se realizó:

- cálculo de volatilidad;
- ranking low-vol;
- retorno futuro;
- PnL;
- cambio del mínimo de 50 a 40;
- reducción del umbral de liquidez de 5M USDT;
- imputación;
- uso de `exchangeInfo` actual como universo;
- credenciales;
- PAPER operativo;
- LIVE;
- Render;
- apertura de 2026.

## Decisión

04F-2 **no se abre**. Low-volatility queda cerrada bajo este estándar de amplitud y liquidez sin observar rendimiento económico.

La siguiente metodología debe seleccionarse de nuevo con evidencia externa y factibilidad de producción, evitando variantes post hoc de low-volatility.
