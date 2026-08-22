# BOT 2.0 — 04G-2 Consensus Order Flow + SGB

## Estado

**PREDECLARADO / SIN RESULTADO ECONÓMICO AL VERSIONAR ESTE DOCUMENTO.**

04G-2 es el primer test económico OOS de la línea 04G. No modifica Scanner, RiskEngine, PAPER, LIVE, Render ni credenciales. 2026 permanece cerrado.

## Motivación externa

Anastasopoulos, Gradojevic, Liu, Maynard y Tsiakas (2026), *Order flow and cryptocurrency returns*, Journal of Financial Markets 79, 101047, DOI 10.1016/j.finmar.2026.101047, documentan que modelos no lineales que condicionan en order flow internacional producen capacidad predictiva OOS y alto valor económico. El mejor modelo individual reportado es stochastic gradient boosted regression trees (SGB); los modelos salvo RF usan objetivo Huber y todos incluyen retorno rezagado.

El paper usa un panel internacional fijo que Binance Vision público no replica exactamente. Por eso 04G-2 **no se presenta como réplica exacta**.

## Evidencia interna previa

- 04G-0: disponibilidad multi-quote apta en 48/48 meses, con 19–20 bases multi-quote por mes.
- 04G-1: contenido/semántica OF desagregado apto; 6.192 archivos, 186.515 barras, 0 errores, 19–20 bases válidas por mes.
- 04G-1a: matriz fija USDT/EUR/BRL/TRY/UAH no apta; solo 1–4 activos complete-case por día y 0/1.461 días con >=10 activos. No hubo ML/PnL.

## Hipótesis única

Para cada activo/día, el promedio equiponderado de todos los order flows estandarizados disponibles (`consensus_of`), junto con el OF USDT y el retorno rezagado, contiene información no lineal suficiente para pronosticar el retorno Spot-USDT del día siguiente. Un SGB entrenado walk-forward debería generar una cartera long-only top-quintile con retorno neto positivo y valor incremental frente a equal-weight y frente al sort directo por consensus OF.

Si falla, no se invierte el signo, no se cambian features, grid, costos ni selección después de ver el resultado.

## Construcción causal

Para cada par Spot base/quote:

- `seller_quote = quote_volume - taker_buy_quote_volume`;
- `raw_of = ln(taker_buy_quote_volume) - ln(seller_quote)`;
- `std_of_t = raw_of_t / stdev(raw_of_{t-29..t})`;
- se requiere una ventana completa de 30 días y valores positivos;
- no epsilon, clipping ni imputación.

Para una base en día `t`:

- `consensus_of_t = mean(std_of_t de todos los quotes disponibles)`;
- se requieren al menos 2 quotes;
- `usdt_of_t` debe existir;
- `lag_return = open(t+1)/open(t)-1`;
- la señal queda disponible al abrir `t+1`;
- `target = open(t+2)/open(t+1)-1`.

## Universo y fechas

20 bases heredadas: BTC, ETH, BNB, XRP, ADA, DOGE, SOL, LTC, BCH, LINK, TRX, ETC, XLM, DOT, ATOM, AVAX, UNI, AAVE, FIL, NEAR.

Quotes auditados: USDT, BUSD, USDC, TUSD, FDUSD, EUR, GBP, AUD, BRL, TRY, RUB, UAH, BIDR, IDRT.

- archivos: nov-2021 a dic-2025, exclusivamente para warm-up y observaciones 2022–2025;
- training inicial: 2022;
- validation exclusiva para hiperparámetros: 2023;
- OOS económico: 2024–2025;
- 2026: cerrado.

## SGB predeclarado

`scikit-learn==1.9.0`, `GradientBoostingRegressor`:

- loss = Huber;
- subsample = 0.50;
- random_state = 42;
- min_samples_leaf = 20;
- grid fijo: n_estimators {100, 200} × learning_rate {0.03, 0.10} × max_depth {1, 2};
- métrica de selección: MSE sobre 2023;
- desempate determinista: menor n_estimators, learning_rate, max_depth;
- selección de hiperparámetros ocurre una sola vez y jamás usa 2024–2025;
- esos hiperparámetros quedan congelados;
- reestimación del modelo al inicio de cada mes OOS con ventana expansiva que termina el mes anterior;
- StandardScaler ajustado solo con filas pre-test.

## Portafolio

Cada día OOS con >=15 activos:

- ordenar por forecast SGB descendente;
- comprar top 20%;
- pesos iguales;
- horizonte 1 día;
- rebalance diario.

Turnover = `0.5 * sum(abs(w_t - w_{t-1}))`; primer día = 1.

Costos:

- caso primario: 25 bps × turnover;
- stress: 50 bps × turnover.

Baselines predeclarados:

1. equal-weight de todos los activos elegibles;
2. top 20% por consensus OF sin ML.

## Gates

Primero datos:

- >=95% de los días OOS deben tener >=15 activos elegibles;
- errores de contenido o duplicados cross-file invalidan el gate de datos.

Si datos pasan, la hipótesis aprueba solo si **todos** cumplen:

- R² OOS vs forecast cero > 0;
- media diaria neta a 25 bps > 0;
- Sharpe anualizado neto a 25 bps >= 1.00;
- >=14 meses netos positivos;
- 2/2 años netos positivos;
- uplift medio neto vs equal-weight > 0;
- uplift medio neto vs consensus sort > 0;
- media diaria neta a 50 bps > 0;
- Sharpe anualizado neto a 50 bps >= 0.50.

Workflow success no equivale a aprobación económica.

## Candados

- no signo invertido post resultado;
- no cambio de costos post resultado;
- no cambio de features post resultado;
- no cambio del grid post resultado;
- no selección de quotes por performance;
- no imputación;
- no conversión FX inventada;
- no GPT;
- no credenciales;
- no PAPER operativo;
- no LIVE;
- no Render;
- no 2026.
