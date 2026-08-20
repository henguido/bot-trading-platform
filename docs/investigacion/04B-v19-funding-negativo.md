# BOT 2.0 — 04B-v19: funding negativo -> Spot long

## Estado

**FALSIFICADA / NO PROMOCIONAR**.

v19 evaluó una única hipótesis predeclarada, sin invertir el signo después de observar retornos:

- señal(t): suma de todos los settlements reales de funding USD-M del día UTC t;
- ranking: funding diario más negativo primero;
- selección: bottom-5 cross-sectional;
- ejecución histórica: Spot open(t+1) -> close(t+1);
- hurdle económico: 25 bps round-trip por día seleccionado;
- benchmark: equal-weight contemporáneo con el mismo hurdle;
- control direccional: spread bottom-5 funding vs top-5 funding;
- desarrollo: 2022-01-01 .. 2025-12-31;
- 2026 y test mayo-julio permanecieron cerrados.

La agregación por suma diaria no presupone una cadencia fija de funding: consume únicamente los settlements realmente publicados dentro del día UTC.

## Infraestructura y datos

Ejecución CI #74 del PR temporal #19:

- 1082 tests passed;
- `compileall` backend: OK;
- frontend: 841 módulos transformados;
- funding Binance Vision: 960/960 archivos mensuales válidos;
- Spot: 20/20 símbolos válidos;
- observaciones alineadas sin lookahead: 29,200;
- 2026_OPEN=False.

## Resultado por año

| Año | Días | Neto medio bottom-5 (bps) | Mediana neta (bps) | Exceso vs equal-weight (bps) | Spread bottom-5 vs top-5 (bps) | Apto |
|---|---:|---:|---:|---:|---:|---|
| 2022 | 365 | -60.1705 | -36.9297 | -8.7052 | -4.6172 | No |
| 2023 | 365 | +2.4683 | -10.9520 | +0.0363 | -1.9374 | No |
| 2024 | 366 | -5.9202 | -3.6279 | -4.4736 | -11.5152 | No |
| 2025 | 364 | -19.8732 | -26.1102 | +13.0156 | +26.4509 | No |

**Años aptos: 0/4.**

Clasificación final del runner: `FUNDING_SIN_SENAL_V19`.

## Interpretación

2025 muestra separación cross-sectional favorable: bottom funding superó a equal-weight y al top funding. Sin embargo, el basket long siguió siendo negativo después del hurdle y la señal no fue estable a través de años. Ese hallazgo no autoriza modificar retrospectivamente el signo, el top-k, el horizonte ni el hurdle.

Por tanto:

1. funding negativo aislado no se promociona como Expected Edge;
2. no se prueba inmediatamente funding positivo como reversión post-hoc de v19;
3. funding puede conservarse como variable contextual futura, pero no como autoridad de BUY;
4. la siguiente investigación debe aportar información independiente —open interest/posicionamiento— y comenzar por una auditoría de datos antes de observar retornos.

## Seguridad

v19 fue exclusivamente investigación offline. No modificó scanner productivo, RiskEngine, tamaño de órdenes, ejecución PAPER/LIVE, Render ni autoridad de trading.
