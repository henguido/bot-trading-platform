# BOT 2.0 — 04F-0 Auditoría de datos low-volatility

## Objetivo

Determinar si Binance Vision permite reconstruir, sin survivorship bias y sin credenciales, un universo histórico suficientemente amplio para una réplica **long-only Spot** de la anomalía low-volatility.

**04F-0 NO ES BACKTEST Y NO OBSERVA PnL.** No descarga contenido ZIP ni calcula volatilidad, retornos, rankings o costos.

## Por qué esta línea es nueva

Los experimentos 04B-v9/v10 no probaron una cartera low-volatility:

- v9: retorno 4h, retorno 24h y sorpresa de volumen;
- v10: momentum 24h ajustado por volatilidad, máximo retorno 4h, posición del cierre en rango y taker-buy share.

En v10 la volatilidad fue un denominador del momentum ajustado por riesgo; nunca se usó la volatilidad realizada por sí sola para comprar el cuartil/quintil de menor riesgo.

## Evidencia externa previa al experimento

Pyo y Jang, *Revisiting the low-volatility anomaly in cryptocurrency markets*, Finance Research Letters (2026), DOI `10.1016/j.frl.2026.109851`, estudian 432 criptomonedas Spot de Binance entre enero de 2018 y noviembre de 2025. Reportan una prima low-volatility cross-sectional y señalan que el spread es más fuerte con ventanas de formación de 2–3 meses y holding de 1 mes.

04F adopta **una sola** especificación antes de cualquier PnL interno: **3 meses de formación + 1 mes de holding**. No se ejecutará después un grid 1/2/3 meses para escoger retrospectivamente el mejor.

La literatura de restricciones económicas en cripto advierte además que muchas anomalías dependen de activos difíciles de negociar, trading costs o regímenes alcistas. Por eso una eventual 04F-1 deberá predeclarar liquidez, costos, long-only y estabilidad reciente antes de observar PnL.

## Periodo

- holdings objetivo: enero 2022 a diciembre 2025;
- 48 meses;
- para el primer holding se requieren octubre, noviembre y diciembre de 2021 como formación;
- archivo auditado: octubre 2021 a diciembre 2025;
- 2026 permanece cerrado.

## Fuente y reconstrucción del universo

Fuente única: Binance Vision, Spot monthly klines `1d`.

El universo **no** se obtiene desde `exchangeInfo` actual. Se listan los prefixes históricos en:

`data/spot/monthly/klines/`

y después los objetos:

`data/spot/monthly/klines/{SYMBOL}/1d/{SYMBOL}-1d-YYYY-MM.zip`

Solo en esta auditoría de disponibilidad se consideran prefixes cuyo símbolo termina en `USDT`.

Esto evita descartar automáticamente activos que existieron en 2022–2024 pero fueron delistados después. Todavía no define la elegibilidad económica final: stablecoins, leveraged tokens, liquidez y cobertura diaria se resolverán antes de PnL en una etapa posterior si 04F-0 pasa.

## Gate PREDECLARADO antes del inventario real

04F-0 será apto solo si:

1. el listado raíz termina completamente;
2. todos los prefixes Spot-USDT descubiertos terminan su listado `1d`;
3. no hay pares `(symbol, month)` duplicados;
4. no hay ZIPs objetivo de tamaño cero;
5. para **cada uno de los 48 meses** de holding existen al menos **100 símbolos** con los tres meses de formación y el mes de holding presentes.

Estado de aprobación:

`ARCHIVO_LOW_VOL_INVENTARIO_APTO_04F0`

Cualquier incumplimiento:

`ARCHIVO_LOW_VOL_INVENTARIO_NO_APTO_04F0`

El mínimo de 100 símbolos no se reducirá después de observar el archivo.

## Lo que 04F-0 no puede concluir

Incluso si pasa, no demuestra:

- que cada ZIP contenga todos los días esperados;
- que los símbolos sean económicamente negociables;
- que exista liquidez suficiente;
- que la anomalía se reproduzca;
- que sobreviva fees/slippage;
- que sea apta para PAPER o LIVE.

Una 04F-1 posterior tendría que auditar contenido y reglas de elegibilidad **antes** de cualquier retorno de cartera.

## Candados

- PnL: prohibido;
- contenido de ZIP: prohibido;
- `exchangeInfo` actual como universo: prohibido;
- imputación: prohibida;
- credenciales: prohibidas;
- PAPER operativo: prohibido;
- LIVE: prohibido;
- Render: sin cambios;
- 2026: cerrado.
