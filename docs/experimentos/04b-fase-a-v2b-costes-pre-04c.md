# BOT 2.0-04B — Fase A v2b: diagnostico de costes antes de 04C

## Veredicto

**NO avanzar a 04C operativo con la familia v2 tal como esta.**

04B-v2 encontro una familia robusta en horizonte **8 h**, pero su uplift
cross-sectional medio es de solo **3,41 bps brutos**. Antes de tocar un
EconomicGate, ese edge debe sobrevivir a los costes de 04A:

```text
fee entrada
+ fee salida
+ spread round-trip
+ slippage entrada/salida
+ coste IA asignado
+ margen de seguridad
```

Con 3,41 bps brutos, el presupuesto economico es demasiado pequeno. Incluso si
spread, slippage, IA y margen fueran cero, la fee taker maxima tolerable seria:

```text
3,411755 bps / 2 = 1,705877 bps por lado
```

Cualquier fee por lado superior a ese valor deja el edge neto negativo antes de
sumar spread, slippage o IA.

## Alcance

Este documento no abre mayo-julio 2026, no usa datos nuevos de holdout final y
no conecta nada al trading loop. Es una revision aritmetica sobre el resultado
ya validado de enero-abril 2026.

Se agrego una utilidad pura:

```text
backend/economia/diagnostico_edge_costes.py
```

Su funcion es comparar edge bruto contra una `EstimacionCostes` de 04A. No
importa red, BD, scanner, RiskEngine, LLM, Binance ni `main.py`.

## Resultado base usado

De 04B-v2:

| Campo | Valor |
|---|---:|
| status | `FAMILIA_ROBUSTA_VALIDACION_V2` |
| horizonte robusto | 8 h |
| configuraciones robustas | 4 |
| uplift cross-section medio | 0,0003411755004224986 |
| uplift en bps | 3,411755004224986 |
| fraccion timestamps positivos | 0,5154061624649860 |
| meses positivos | 3 |
| folds positivos | 3 |

El resultado es estadisticamente mejor que v1, pero economicamente estrecho.

## Diagnostico contra costes

### Caso minimo: solo fee taker

Supuesto deliberadamente favorable:

```text
spread = 0
slippage = 0
costo IA = 0
margen seguridad = 0
fee_taker = 10 bps por lado
```

Resultado:

| Campo | Valor |
|---|---:|
| coste total | 20,000 bps |
| edge bruto | 3,411755 bps |
| edge neto | -16,588245 bps |
| diagnostico | `NO_CUBRE_COSTES` |

Este escenario no afirma que esa sea la fee actual de una cuenta especifica.
Solo demuestra sensibilidad: una fee por lado comun en el orden de 10 bps deja
el edge muy por debajo del break-even.

### Caso 04A de ejemplo completo

Escenario ya cubierto por tests de 04A:

```text
notional = 10 USDT
spread = 10 bps
fee_taker = 10 bps por lado
slippage = 5 bps por lado
costo IA = 0,0084475 USD
```

Resultado:

| Campo | Valor |
|---|---:|
| coste total | 48,447500 bps |
| edge bruto | 3,411755 bps |
| edge neto | -45,035745 bps |
| diagnostico | `NO_CUBRE_COSTES` |

En este caso la IA suma 8,4475 bps sobre 10 USDT. En notionals mayores pesa
menos, pero la fee round-trip sigue dominando.

### Caso ultra favorable

Supuesto extremo:

```text
spread = 1 bps
slippage = 0
costo IA = 0
margen seguridad = 0
fee_taker = 1 bps por lado
```

Resultado:

| Campo | Valor |
|---|---:|
| coste total | 3,000 bps |
| edge bruto | 3,411755 bps |
| edge neto | +0,411755 bps |
| diagnostico | `CUBRE_COSTES` |

Este caso ilustra el tamano del problema: v2 solo tiene espacio bajo supuestos
extraordinariamente favorables y sin margen de seguridad.

## Implicacion metodologica

04B-v2 queda como evidencia de que las features relativas pueden ordenar mejor
que v1, pero no como evidencia economica suficiente para operar. Pasar a 04C con
este edge obligaria a crear un gate que casi siempre rechaza todo o a relajar
costes/margen de seguridad, lo cual seria metodologicamente incorrecto.

La decision correcta es:

```text
04B-v2 = senal estadistica pequena, documentada
04B-v2b = no viable economicamente bajo costes round-trip normales
04C operativo = no autorizado todavia
```

## Lo que NO se hara

- No abrir mayo-julio 2026 para rescatar o confirmar v2.
- No conectar v2 a `main.py`, scanner, GPT, RiskEngine ni PAPER/LIVE.
- No reducir costes desconocidos a cero.
- No escoger otro horizonte por performance.
- No declarar rentabilidad neta con retornos brutos.

## Siguientes opciones

1. **04B-v3**: disenar una nueva familia con edge bruto bastante mayor antes de
   abrir holdout final.
2. **04C-sombra**: construir un EconomicGate solo en modo sombra/offline que
   rechace candidatos y mida cobertura, sin trading y sin abrir mayo-julio.
3. **Abrir mayo-julio**: posible solo con autorizacion explicita, pero no es la
   recomendacion actual porque el resultado enero-abril ya muestra que el margen
   economico es muy estrecho.

## Verificacion

Pruebas enfocadas:

```text
tests/test_diagnostico_edge_costes.py
tests/test_fuentes_coste_existentes.py
tests/test_fuentes_coste_04a1.py
```

Resultado local:

```text
37 passed
```
