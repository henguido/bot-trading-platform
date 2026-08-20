# BOT 2.0-04B-v4 - Resultado enero-abril 2026

Estado: falsada.

Commit de protocolo prevalidacion:

```text
d66b4d3 feat(economia): predeclara regimen absoluto v4
```

Validacion ejecutada despues de que pasaran las pruebas locales y el build.

## Alcance

- periodo usado: enero-abril 2026;
- mayo-julio 2026: cerrado;
- modo: offline/PAPER;
- fuente: datos historicos publicos Spot;
- sin GPT, sin scanner, sin RiskEngine, sin ordenes y sin LIVE.

## Protocolo

v4 conserva el cluster robusto heredado de v3:

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

Filtro agregado:

```text
mediana_retorno_24h_mercado * 10000 >= 0
```

Costes:

```text
coste round-trip minimo: 20 bps
margen de seguridad: 5 bps
hurdle predicho: 25 bps
```

## Resultado

```text
SIN_CONFIGURACIONES_REGIMEN_COST_AWARE_V4
```

- simbolos utiles: 20/20;
- observaciones relativas: 188.760;
- observaciones pre-test evaluadas: 188.760;
- configuraciones: 4;
- configuraciones aptas: 0/4.

Metricas comunes a las 4 configuraciones:

```text
predicciones de entrada: 7.140
predicciones sin regimen: 0
predicciones con regimen aprobado: 3.320
timestamps de entrada: 357
timestamps con regimen aprobado: 166
cobertura regimen timestamps: 46.49859943977591036414565826%
timestamps con senal: 0
senales: 0
```

El filtro de regimen no fallo por falta de cobertura: aprobo casi la mitad de
los timestamps. El fallo fue economico: despues de aplicar el regimen absoluto,
ninguna prediccion supero el hurdle predeclarado de 25 bps.

Motivos de rechazo en las 4 configuraciones:

- `SIN_SENALES_REGIMEN_COST_AWARE`;
- `COBERTURA_TOTAL_SENALES_INSUFICIENTE`;
- `RETORNO_NETO_NO_CUBRE_COSTES`;
- `SIN_UPLIFT_BRUTO_COST_AWARE`;
- `NETO_INESTABLE_TIMESTAMPS`;
- `UPLIFT_INESTABLE_TIMESTAMPS`;
- `COBERTURA_MENSUAL_SENALES_INSUFICIENTE`;
- `NETO_INESTABLE_MENSUAL`;
- `COBERTURA_FOLDS_SENALES_INSUFICIENTE`;
- `NETO_INESTABLE_FOLDS`.

## Interpretacion

04B-v4 no rescata la familia relativa/cost-aware. La senal bruta que aparecio
en v2 y el uplift parcial de v3 no se convierten en una regla long-only que
cubra costes minimos bajo un filtro de mercado simple.

No se debe bajar el hurdle, optimizar el umbral de regimen contra enero-abril ni
abrir mayo-julio para rescatar esta familia. Mayo-julio queda reservado como
test final solo si aparece una hipotesis nueva predeclarada con suficiente
justificacion.

## Pendiente

Antes de operar sigue faltando una familia que demuestre edge neto robusto.
Mientras v4 este falsada, 04C no debe conectarse a decisiones de entrada.
