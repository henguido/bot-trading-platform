# BOT 2.0-04B-v4 - Protocolo regimen absoluto

Estado: predeclarado antes de ejecutar la corrida v4.

## Motivo

04B-v2 encontro una familia robusta bruta en enero-abril 2026, pero 04B-v3
mostro que ese edge no cubre costes operables minimos:

- coste round-trip minimo: 20 bps;
- margen de seguridad: 5 bps;
- hurdle predicho: 25 bps;
- resultado v3 enero-abril: 0/4 configuraciones aptas.

v3 tambien mostro que el ranking relativo podia tener uplift bruto frente al
baseline del timestamp, pero aun quedar negativo despues de costes. v4 prueba una
hipotesis mas estrecha: operar long solo cuando el mercado, medido con una
feature ya conocida en el timestamp, no esta en regimen bajista absoluto.

## Advertencia de limpieza experimental

Enero-abril 2026 ya fue observado por v2 y v3. Por eso esta corrida v4 es una
validacion informada/diagnostica, no un holdout limpio para inventar umbrales.

Mayo-julio 2026 sigue cerrado como test final. No se usa para disenar v4, no se
descarga como validacion v4 y no aparece en el runner.

## Regla de regimen

Feature usada:

```text
mediana_retorno_24h_mercado
```

Esta feature pertenece a `EstadoRelativoV2` y se calcula con retornos 24h ya
conocidos en el timestamp. No usa etiquetas futuras.

Umbral unico:

```text
regimen_mercado_minimo_bps = 0
```

Una prediccion solo puede pasar al evaluador cost-aware si:

```text
mediana_retorno_24h_mercado * 10000 >= 0
```

Si falta regimen para una prediccion, se descarta. No se rellena con cero.

## Configuraciones

Se conserva exclusivamente el cluster robusto heredado de v3:

```text
horizonte: 8h
rank_bins: 3
regimen_bins: 3
min_muestras: 30 / 60
max_radio: 0 / 1
```

Total:

```text
4 configuraciones
```

No se agregan indicadores, no se cambia universo, no se optimiza el umbral de
regimen y no se busca ganador por retorno.

## Criterios minimos

Para que una configuracion sea apta:

- cobertura del modelo >= 50%;
- 4/4 folds de enero-abril disponibles;
- cobertura de regimen aprobado >= 20% de timestamps de entrada;
- cobertura total de timestamps con senal >= 5%;
- retorno neto despues de coste y margen > 0 bps;
- uplift bruto contra baseline del timestamp > 0 bps;
- fraccion de timestamps con neto positivo >= 50%;
- fraccion de timestamps con uplift positivo >= 50%;
- senales en 4 meses y 4 folds;
- al menos 3 meses netos positivos;
- al menos 3 folds netos positivos.

Para que la familia v4 sea robusta:

```text
al menos 2 de 4 configuraciones aptas
```

## Limites

Esto no autoriza 04C operativo. Incluso si v4 pasara, antes de operar faltarian:

- abrir mayo-julio 2026 solo con autorizacion explicita;
- documentar el resultado del test final;
- conectar 04C como gate en shadow/PAPER, no LIVE;
- validar costes reales, slippage, profundidad, limites de riesgo y monitoreo;
- sostener ejecucion PAPER antes de cualquier decision LIVE.
