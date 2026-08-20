# BOT 2.0-04B-v9 — diagnóstico factorial 24h

## Alcance

Diagnóstico sin entrenamiento sobre desarrollo 2022-2025. 2026 permaneció cerrado.

Factores probados:
- rank retorno 4h;
- rank retorno 24h;
- rank sorpresa volumen 4h.

Cada factor se evaluó en dos orientaciones: momentum (alto) y reversión (bajo), con horizonte 24h y hurdle económico de 25 bps.

## Validación técnica

- 977 tests passed;
- compileall backend OK;
- frontend build OK (841 módulos);
- 20/20 símbolos útiles;
- 174.360 observaciones;
- DESARROLLO_2026_OPEN=False;
- TEST_MAY_JUL_OPEN=False.

## Resultado

Status: `SIN_FACTORES_PROMETEDORES_V9`.

Ninguno de los tres factores mostró una relación monotónica suficiente y estable con el retorno de las siguientes 24h.

### rank retorno 4h

- IC Spearman medio: -0,00497;
- spread alto-bajo medio: +4,54 bps;
- momentum top-1 neto: -3,96 bps;
- reversión top-1 neto: -48,70 bps.

### rank retorno 24h

- IC Spearman medio: -0,03080;
- spread alto-bajo medio: +3,69 bps;
- momentum top-1 neto: -10,90 bps;
- reversión top-1 neto: -38,47 bps.

### rank sorpresa volumen 4h

- IC Spearman medio: -0,04104;
- spread alto-bajo medio: -8,23 bps;
- momentum top-1 neto: -28,28 bps;
- reversión top-1 neto: -24,08 bps.

Las seis orientaciones fallaron retorno/hit-rate y/o estabilidad temporal. No se modifican los thresholds después del resultado.

## Conclusión

v9 falsifica la hipótesis de que estas tres features simples, por sí solas y de forma monotónica, justifican selección long spot a 24h. No corresponde aplicar un modelo más complejo sobre las mismas variables esperando fabricar edge.

La siguiente hipótesis debe aportar información nueva. v10 probará, predeclaradamente y solo en régimen long no negativo:
- momentum ajustado por volatilidad;
- máximo retorno de barra reciente;
- posición del cierre dentro del rango;
- presión compradora basada en taker-buy quote volume.

2026 continúa cerrado.