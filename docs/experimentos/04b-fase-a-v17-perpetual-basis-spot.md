# BOT 2.0-04B-v17 — Perpetual basis cross-sectional -> Spot

## Hipótesis predeclarada

v16 demostró que el histórico USD-M perpetual 1d era suficientemente completo. v17 probó una sola hipótesis económica antes de observar retornos:

`basis_perp(t) = (SpotClose(t) - FuturesClose(t)) / FuturesClose(t)`

- dirección: basis más alto = candidato long Spot;
- selección: top-5 cross-sectional;
- señal al cierre de t;
- entrada Spot al open de t+1;
- salida Spot al close de t+1;
- hurdle conservador: 25 bps round-trip;
- promoción: al menos 3 de 4 años aptos;
- no se prueba automáticamente la dirección contraria.

Los criterios anuales reutilizaron el motor estadístico v15: retorno neto medio y mediano positivos, estabilidad mensual/trimestral, exceso medio y mediano positivos frente al equal-weight contemporáneo, y spread top-basis menos bottom-basis medio y mediano positivos con estabilidad.

Este factor es **perpetual basis**, no el current-quarter basis usado en la literatura académica.

## Validación técnica

GitHub Actions run `32411661268` sobre HEAD `a2c8068e227f74e0522b5dab327a526b527d7c3b`:

- `1049 passed`;
- `compileall` OK;
- frontend build OK (`841 modules transformed`);
- locks v17 OK: 2026 cerrado;
- Futures: 960/960 archivos mensuales válidos;
- Spot: 20/20 símbolos válidos;
- 29.165 observaciones alineadas;
- workflows legacy de research quedaron `skipped`;
- sin GPT, LIVE ni Render.

## Resultado

`BASIS_SIN_SENAL_V17` — **0/4 años aptos**.

| Año | Días | Top-basis neto medio | Mediana | Hit-rate | Benchmark neto medio | Exceso medio | Exceso mediano | Spread top-bottom medio | Spread mediano | Meses portfolio + | Folds portfolio + | Apto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2022 | 360 | -49,76 bps | -41,37 bps | 45,28% | -54,81 bps | +5,05 bps | -7,17 bps | +3,92 bps | -3,27 bps | 3/12 | 1/4 | No |
| 2023 | 365 | -2,45 bps | -2,67 bps | 47,95% | +2,43 bps | -4,89 bps | -5,29 bps | -4,94 bps | -0,44 bps | 4/12 | 2/4 | No |
| 2024 | 366 | -8,45 bps | -18,70 bps | 47,54% | -1,45 bps | -7,00 bps | -7,67 bps | -6,95 bps | -16,30 bps | 4/12 | 2/4 | No |
| 2025 | 364 | -37,72 bps | -33,25 bps | 45,88% | -32,89 bps | -4,83 bps | -11,09 bps | -7,40 bps | -9,31 bps | 2/12 | 0/4 | No |

2022 muestra un pequeño exceso medio relativo (+5,05 bps/día), pero el basket seleccionado todavía pierde cerca de 50 bps/día netos y las medianas de exceso y spread son negativas. En 2023–2025 fallan simultáneamente rentabilidad absoluta, alpha frente al mercado y coherencia cross-sectional.

## Conclusión

v17 falsifica **perpetual basis diario, top-5, long Spot t+1** bajo la construcción predeclarada. No se invierte retrospectivamente la dirección ni se ajustan top-k, hurdle o thresholds para rescatarla.

El resultado no falsifica el current-quarter basis académico, cuya cobertura histórica no alcanza para un análisis cross-sectional comparable en nuestro universo de 20 activos.

La siguiente familia debe aportar información diferente. Funding rate es una candidata natural porque mide transferencia de carry/posicionamiento del perpetuo y su histórico público de Binance es accesible desde 2022.

## Seguridad

- PAPER únicamente.
- 2026 cerrado.
- LIVE cerrado.
- Render sin cambios.
- `main` sin cambios.
