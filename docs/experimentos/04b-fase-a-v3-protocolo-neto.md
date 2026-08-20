# BOT 2.0-04B - Fase A v3: protocolo cost-aware pre-04C

## Objetivo

04B-v2 encontro una senal relativa robusta, pero el uplift bruto medio fue
demasiado pequeno frente a costes normales. 04B-v3 no cambia el bot operativo:
define una prueba offline para responder una pregunta mas estricta:

```text
Si solo tomamos senales cuyo edge predicho supera costes + margen,
el resultado observado sigue siendo neto positivo y estable?
```

## Candados

- No abre mayo-julio 2026.
- No usa datos posteriores al 30 de abril de 2026.
- No importa scanner, GPT, RiskEngine, PAPER, LIVE ni Render.
- No descarga datos privados ni usa credenciales.
- No selecciona configuracion por mayor retorno observado.

## Familia predeclarada

v3 no expande la busqueda. Usa el cluster robusto de v2:

```text
horizonte = 8h
rank_bins = 3
regimen_bins = 3
min_muestras = 30 / 60
max_radio = 0 / 1
```

Total: 4 configuraciones.

## Hurdle economico

Se fija antes de ejecutar v3:

```text
coste total minimo operable = 20 bps
margen de seguridad         = 5 bps
hurdle predicho             = 25 bps
```

La evaluacion solo considera como senal una prediccion con:

```text
edge predicho >= 25 bps
```

Por timestamp se elige como maximo una senal, la de mayor edge predicho.

## Criterios minimos

Una configuracion v3 debe cumplir:

- cobertura del modelo >= 50 %;
- senales en >= 5 % de timestamps evaluables;
- retorno neto despues de margen > 0 bps;
- uplift bruto contra baseline contemporaneo > 0 bps;
- fraccion de timestamps con neto despues de margen positivo >= 50 %;
- fraccion de timestamps con uplift positivo >= 50 %;
- senales en los 4 meses enero-abril 2026;
- >= 3 meses con neto despues de margen positivo;
- senales en los 4 folds;
- >= 3 folds con neto despues de margen positivo.

La familia v3 solo se considera robusta si al menos 2 de las 4 configuraciones
superan criterios. Una unica configuracion apta queda como aislada.

## Implicacion

Si v3 falla, el siguiente paso no es 04C operativo. Habria que buscar una nueva
familia de edge o reducir costes reales antes de abrir el holdout final.

Si v3 pasa, todavia no autoriza operacion real. El orden correcto seguiria
siendo:

```text
04B-v3 validacion enero-abril
04B TEST final mayo-julio, solo con autorizacion explicita
04C sombra/offline
PAPER prolongado
LIVE, solo despues de controles operativos completos
```
