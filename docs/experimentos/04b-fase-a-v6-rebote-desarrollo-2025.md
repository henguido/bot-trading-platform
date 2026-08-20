# BOT 2.0-04B-v6 — Diagnóstico de rebote en desarrollo 2025

## Veredicto

**04B-v6 queda falsada en desarrollo.**

v6 probó una hipótesis distinta de v2-v5: mantener exactamente las señales
cost-aware heredadas de v5, pero cambiar la salida fija a 8 h por un bracket
conservador para comprobar si el MFE intrahorizonte permitía capturar rebotes.

Resultado ejecutado:

```text
REBOTE_V6_FALSADO_DESARROLLO
configuraciones aptas: 0/4
```

No se ajustan stop, target ni hurdle después de observar este resultado.

## Protocolo predeclarado

```text
horizonte: 8 h
coste round-trip: 20 bps
margen de seguridad: 5 bps
hurdle económico: 25 bps
stop bruto: -50 bps
target bruto: +175 bps
máximo señales por timestamp: 1
```

Después de coste + margen:

```text
stop aproximado: -75 bps
target aproximado: +150 bps
reward/risk neto aproximado: 2:1
```

Si stop y target aparecían dentro de la misma ventana observable con velas 4 h,
se aplicó **STOP prioritario / peor caso**, porque OHLC no permite demostrar el
orden intrabar.

## Alcance temporal

- datos descargados/evaluados: 2022-01-01 a 2025-12-31;
- folds de diagnóstico: 2025-Q1..Q4;
- enero-abril 2026: **no abierto por v6**;
- mayo-julio 2026: **cerrado**;
- sin LIVE, Render, GPT, RiskEngine ni órdenes.

## Validación técnica

Draft PR:

```text
#6 — WIP: validar BOT 2.0-04B v6 rebote conservador
```

Head ejecutado:

```text
2342480133e054f1a4f8d35c00476611fdde4341
```

GitHub Actions:

```text
run: 32382236431
job: 96468011432
conclusion: success
```

Verificaciones:

- pytest: **956 passed**;
- warnings: 1391;
- compileall backend: OK;
- frontend build: OK, 841 módulos;
- candados v6 de 2026: OK;
- diagnóstico offline v6: OK;
- artifact generado y subido.

Artifact:

```text
name: edge-rebote-v6-desarrollo-2025
id: 9411592134
digest: sha256:f74be1003b6a06232ff3c57e5a2fdf4dd67b6005d2e48d0add1367ad729b9ca3
```

El log verificable confirma `utiles=20` y `configs_aptas=0/4`. No se documentan
aquí métricas por configuración porque no fueron recuperadas de forma fiable en
esta sesión; no se inventan cifras ausentes.

## Interpretación

v2-v5 ya mostraban que la familia relativa identifica principalmente activos que
pueden perder menos que el mercado. v6 probó si una salida intrahorizonte
conservadora podía convertir esas señales defensivas en un payoff long spot
robusto. No ocurrió: ninguna de las cuatro variantes heredadas superó los
criterios predeclarados.

Esto cierra la vía de seguir ajustando la misma familia de 8 h mediante filtros,
hurdles o brackets. Cambiar ahora stop/target sería optimización retrospectiva.

## Siguiente dirección

Antes de construir otro predictor, medir en desarrollo 2022-2025 la **base-rate
de oportunidad absoluta** a horizontes más largos (24/48/72 h):

- retorno absoluto futuro;
- probabilidad de superar 25 bps;
- MFE/MAE;
- comportamiento por régimen de mercado;
- estabilidad mensual/trimestral.

Solo si existe suficiente movimiento absoluto se justificará una nueva familia
04B-v7 de menor turnover. Mayo-julio 2026 sigue reservado como holdout final.
