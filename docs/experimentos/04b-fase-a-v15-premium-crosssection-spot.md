# BOT 2.0-04B-v15 — Premium Index cross-sectional -> Spot

## Hipótesis predeclarada

v14 demostró que `premiumIndex` USD-M diario era históricamente reproducible. v15 probó una sola interpretación económica antes de mirar retornos:

- señal(t): `premiumIndex.close` diario;
- dirección: premium más bajo/negativo = mayor proxy de `Spot - Futures` = candidato long;
- selección: bottom-5 cross-sectional;
- entrada: Spot open de t+1;
- salida: Spot close de t+1;
- hurdle: 25 bps round-trip por día seleccionado;
- high-5 se usa solo como diagnóstico de spread, no como estrategia alternativa;
- promoción: al menos 3/4 años aptos.

Cada año debía mostrar simultáneamente retorno neto medio y mediano positivos, estabilidad mensual/trimestral, exceso medio y mediano positivos frente al equal-weight contemporáneo, y spread low-5 menos high-5 medio y mediano positivos con estabilidad.

## Validación técnica

GitHub Actions run `32410455282` sobre HEAD `b8d675a398074e2e83eeb472c499658abeffa86b`:

- `1034 passed`;
- `compileall` OK;
- frontend build OK (`841 modules transformed`);
- locks v15 OK: 2026 cerrado;
- premium: 960/960 meses válidos;
- Spot: 20/20 símbolos válidos, 40 requests públicas;
- 29.168 observaciones alineadas;
- sin GPT, LIVE ni Render.

## Resultado

`PREMIUM_SIN_SENAL_V15` — **0/4 años aptos**.

| Año | Días | Low-5 neto medio | Low-5 neto mediano | Hit-rate | Exceso medio vs mercado | Exceso mediano | Spread low-high medio | Spread mediano | Meses portfolio + | Folds portfolio + | Apto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2022 | 364 | -54,26 bps | -44,94 bps | 45,05% | -1,96 bps | -12,29 bps | +2,35 bps | -5,92 bps | 3/12 | 1/4 | No |
| 2023 | 364 | +2,49 bps | -0,08 bps | 49,73% | +0,67 bps | +3,69 bps | +9,97 bps | +13,90 bps | 6/12 | 2/4 | No |
| 2024 | 366 | -14,50 bps | -6,61 bps | 48,91% | -13,05 bps | -18,13 bps | -11,26 bps | -5,41 bps | 4/12 | 2/4 | No |
| 2025 | 364 | -36,02 bps | -32,29 bps | 45,88% | -3,13 bps | -7,20 bps | -11,71 bps | -3,01 bps | 2/12 | 1/4 | No |

2023 fue el único año con media neta y exceso medio levemente positivos, pero la mediana neta fue negativa, solo 6/12 meses y 2/4 folds del portfolio fueron positivos, y la estabilidad del exceso/spread tampoco cumplió los thresholds predeclarados.

En 2024 y 2025 el spread low-premium menos high-premium cambió además de signo, por lo que la dirección no es temporalmente coherente.

## Conclusión

v15 queda falsada. No se invierte la señal retrospectivamente ni se prueban top-3/top-10 dentro de la misma versión.

Este resultado **no falsifica el factor basis en general**. `premiumIndex` de Binance es una medida basada en precios de impacto del perpetuo frente al índice y solo se usó como proxy. La evidencia académica que motivó esta familia define basis con Spot y futures de current-quarter; por tanto la siguiente prueba, si existe cobertura suficiente, debe acercarse más a precios Spot/Futures reales.

## Seguridad

- PAPER únicamente.
- 2026 cerrado.
- LIVE cerrado.
- Render sin cambios.
- `main` sin cambios.
