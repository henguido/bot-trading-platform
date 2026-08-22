# BOT 2.0 — 04H-0 Auditoría Funding Cross-Venue Binance / Hyperliquid

## Estado

**PRE-PNL / PRE-SPREAD.** Esta fase no calcula la diferencia de funding, retornos, Sharpe ni selecciona activos por resultado.

## Por qué esta familia es nueva

04C-2 ya demostró que Spot + short Binance perpetual puede tener carry económico, pero falló los gates productivos por eficiencia de capital y peor año. 04D-3 demostró que, sin leverage/borrowing ni una fuente adicional de yield, compartir collateral no podía rescatar matemáticamente 2022. 04C-3 también falsó el calendar spread perpetual-vs-quarterly.

04H no repite esas estructuras. La hipótesis potencial es **perpetual-vs-perpetual entre dos venues sobre el mismo activo**, de forma que no exista una pata Spot cash 1x obligatoria.

## Evidencia externa que justifica auditarla

Tony Lau (2026), *The Funding Carry and a Cross-Venue Spread on Perpetual Futures: A Significance-Tested Study of Hyperliquid and Centralized Venues* (SSRN 6993978), reporta que el funding de Hyperliquid excedió estructuralmente al de Binance/Bybit en activos coincidentes y que una posición long CEX perp / short Hyperliquid perp mantuvo un spread significativo después de basis, costos y capital, con validación walk-forward. El estudio también reporta que refinamientos más complejos no mejoraron la baseline simple.

Werapun et al. (2026), *Exploring risk and return profiles of funding rate arbitrage on CEX and DEX*, Blockchain: Research and Applications 7(4), 100354, documenta diferencias relevantes de funding entre CEX/DEX y muestra que leverage puede aumentar retorno, pero también reducirlo o provocar pérdidas/liquidaciones si es excesivo.

Estas referencias motivan el audit; sus retornos **no** se importan como expectativa para nuestro BOT.

## Universo auditado

Candidatos definidos antes de datos: BTC, ETH, SOL, XRP, BNB.

Obligatorios para habilitar una futura 04H-1: BTC, ETH y SOL.

Periodo de infraestructura: 2024-01-01 a 2025-12-31. 2026 permanece cerrado.

## Fuentes públicas

### Hyperliquid

API pública `/info`:

- `metaAndAssetCtxs` para universo actual;
- `fundingHistory` para funding histórico horario;
- `candleSnapshot` 8h para precio de perpetual.

El API documenta paginación y un máximo de 500 elementos para respuestas temporales; el auditor pagina sin imputar huecos.

### Binance

Binance Vision:

- `data/futures/um/monthly/fundingRate/{SYMBOL}/...`;
- `data/futures/um/monthly/klines/{SYMBOL}/8h/...`.

Se conservan timestamps reales de funding; 04H-0 no presupone ni normaliza automáticamente la cadencia Binance a 8h.

## Gates de datos

Para BTC/ETH/SOL:

- el activo debe existir en el universo Hyperliquid;
- funding Hyperliquid: >=95% de slots horarios 2024-2025, timestamps sin duplicados y tasas finitas;
- candles Hyperliquid 8h: >=95% de slots, sin duplicados y OHLCV válido;
- Binance funding: >=95% de 24 meses con archivo válido;
- Binance klines 8h: >=95% de 24 meses con archivo válido;
- sin duplicados ni valores inválidos en los archivos Binance aceptados.

Además deben existir al menos 3 activos comunes entre los cinco candidatos.

## Costos y riesgo: qué se puede y qué no se puede reconstruir aquí

- Hyperliquid publica su fee schedule actual, pero el fee efectivo depende de volumen/staking/referral; no se reconstruye un fee tier histórico de usuario sin wallet.
- Binance expone la comisión efectiva de usuario mediante endpoint USER_DATA firmado; no se reconstruye un VIP histórico sin credenciales.
- 04H-1, si se habilita, deberá usar supuestos conservadores fijados antes de PnL y no una comisión retrospectiva favorable.
- Los candles 8h permiten estudiar basis cross-venue y un stress de precio, pero no equivalen al histórico completo de mark price usado por motores de liquidación.
- La suficiencia de datos para funding/basis **no autoriza producción**. Liquidation buffer, margin mode, slippage y ejecución simultánea requerirán gates separados.

## Candados

04H-0 prohíbe:

- calcular spread de funding;
- normalizarlo a una métrica económica común;
- calcular retorno/PnL/Sharpe;
- seleccionar activos por performance;
- imputar huecos;
- usar credenciales;
- PAPER operativo;
- LIVE;
- Render;
- abrir 2026.

El único resultado permitido es `DATASET_CROSSVENUE_FUNDING_APTO_04H0` o `DATASET_CROSSVENUE_FUNDING_NO_APTO_04H0` según disponibilidad/integridad.
