# BOT 2.0-04B-v10 — factores nuevos 24h en régimen no negativo

## Alcance

Diagnóstico sin entrenamiento sobre desarrollo 2022-2025, evaluado en 2025 sobre días con mediana cross-sectional del retorno conocido 24h >= 0. Horizonte futuro 24h y hurdle económico 25 bps.

Factores nuevos:
- momentum 24h ajustado por volatilidad realizada;
- máximo retorno de barra 4h en las últimas 24h;
- posición del cierre en el rango high-low de 24h;
- taker-buy quote-volume share de 24h.

Cada factor se probó en orientación ALTA y BAJA. 2026 permaneció cerrado.

## Validación técnica

- 988 tests passed;
- compileall backend OK;
- frontend build OK (841 módulos);
- candados 2026 OK;
- 20/20 símbolos útiles;
- 175.080 observaciones;
- 180 timestamps 2025 en régimen no negativo.

## Resultado

Status: `SIN_FACTORES_PROMETEDORES_V10`.

### Momentum ajustado por riesgo 24h

ALTA fue la variante más cercana de v10, pero siguió fallando:
- IC Spearman medio: -0,02286;
- spread orientado medio: +6,10 bps;
- 51,67% de timestamps con spread correcto;
- 7 meses y 3/4 folds con spread positivo;
- 180 señales top-1;
- retorno top-1 neto medio: -2,12 bps;
- hit-rate neto: 45,56%;
- 6 meses y 2/4 folds top-1 positivos.

BAJA: -16,03 bps netos medios.

### Máximo retorno 4h dentro de 24h

- ALTA: -21,28 bps top-1 netos;
- BAJA: -41,34 bps top-1 netos;
- spread orientado máximo entre ambas direcciones: ~5,77 bps.

### Posición del cierre dentro del rango 24h

- ALTA: -60,69 bps top-1 netos;
- BAJA: -44,00 bps top-1 netos;
- BAJA logró 8 meses de spread positivo, pero solo 2/4 folds y 49,44% de timestamps con signo correcto.

### Taker-buy share 24h

- ALTA: -34,15 bps top-1 netos;
- BAJA: -52,06 bps top-1 netos;
- spread orientado BAJA: +7,85 bps, insuficiente frente al hurdle de 25 bps.

## Conclusión

Ningún factor pasa simultáneamente magnitud económica, hit-rate y estabilidad temporal. No se modifican thresholds después del resultado.

El resultado no invalida momentum a otras escalas temporales. La literatura que motivó la familia usa formación semanal/multisemanal y rebalanceo semanal, por lo que el siguiente experimento deberá cambiar de horizonte y lookback en vez de continuar ajustando 24h.

2026 continúa cerrado.