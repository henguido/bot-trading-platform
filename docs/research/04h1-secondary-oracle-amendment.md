# 04H-1 — Enmienda pre-PnL para rescate secundario de oracle

Estado: **PRE-PNL**. Esta enmienda se congela antes de observar cualquier resultado económico de 04H-1.

## Hechos empíricos que motivan la enmienda

- El archivo oficial `hyperliquid-archive/asset_ctxs` fue descargado completo para 2024-01-01..2025-12-31: 731/731 días, sin archivos faltantes ni errores de descarga.
- BTC, ETH y SOL presentan 17,237 snapshots exactamente horarios sobre 17,544 esperados: 98.2501%.
- Existen 17,543 settlements de `fundingHistory` por activo y 306 de esos settlements no-cero carecen de `oracle_px` exactamente horario en `asset_ctxs`.
- Los 306 gaps son comunes a BTC, ETH y SOL.
- El gate de precios/basis a 8h sí alcanza 2,192/2,193 = 99.9544% por activo.
- No se ha calculado PnL de 04H-1.

## Regla primaria

`asset_ctxs` oficial de Hyperliquid sigue siendo la fuente primaria y autoritativa para `mark_px` y `oracle_px`.

No se relaja el gate de 99%, no se permite imputación y no se elimina ningún settlement real de funding para mejorar resultados.

## Rescate secundario permitido

Una fuente secundaria podrá aportar `oracle_px` **únicamente** para settlements de funding que cumplan simultáneamente:

1. el settlement existe en `fundingHistory` oficial de Hyperliquid;
2. el funding es distinto de cero;
3. `asset_ctxs` no contiene un `oracle_px` exacto para ese settlement hour;
4. la fuente secundaria identifica explícitamente BTC, ETH o SOL;
5. conserva un timestamp de exchange (`time_exchange` o equivalente), no solamente tiempo de recepción del proveedor;
6. reporta `oracle_px` de Hyperliquid como campo independiente, no un índice reconstruido ni candle proxy;
7. el evento de precio está temporalmente asociado al settlement con una diferencia máxima absoluta de 1 segundo respecto al timestamp publicado por `fundingHistory`;
8. no se usa nearest-neighbor fuera de esa ventana, interpolación, forward-fill, back-fill ni OHLCV.

La fuente secundaria nunca podrá reemplazar un `oracle_px` oficial ya existente en `asset_ctxs`.

## Validación de equivalencia obligatoria antes de usar gaps

Antes de aceptar un solo valor secundario para PnL, la misma fuente debe demostrar equivalencia contra `asset_ctxs` en horas donde ambas fuentes tienen datos:

- mínimo 1,000 observaciones de solapamiento por activo distribuidas entre 2024 y 2025;
- mediana del error relativo absoluto <= 1 bp;
- percentil 99 del error relativo absoluto <= 5 bps;
- máximo error relativo absoluto <= 20 bps;
- 0 valores no positivos o no finitos;
- 0 cambios de símbolo/activo;
- timestamp de exchange requerido; tiempo del proveedor no sustituye al tiempo de exchange.

Estas tolerancias se congelan antes de observar datos de la fuente secundaria.

## Gate secundario

Tras pasar equivalencia:

- cobertura de `oracle_px` sobre settlements no-cero reales >= 99%;
- cobertura se calcula por activo;
- cualquier gap restante se conserva como gap y bloquea PnL si deja la cobertura bajo 99%;
- provenance de cada valor debe quedar explícito: `HYPERLIQUID_ASSET_CTXS` o `SECONDARY_VALIDATED`.

## Fuentes evaluadas al congelar esta enmienda

- 0xArchive: descartada; cobertura medida insuficiente para el gate oficial.
- Bitquery Hyperliquid: documentación comercial actual indica backfill histórico aún no disponible.
- Polaris: no hay documentación pública suficiente que demuestre una serie histórica `oracle_px` equivalente para estos gaps.
- CoinAPI Hyperliquid Oracle Prices: candidato técnicamente compatible porque expone `time_exchange`, `coin_id`, `oracle_px` y `mark_px`; su uso es comercial/pagado y requiere autorización separada antes de cualquier gasto.

## Prohibiciones que siguen vigentes

- 2026 permanece cerrado.
- No LIVE.
- No PAPER operativo todavía.
- No cambiar dirección, activos, leverage, costes o gates económicos después de observar PnL.
- No selección post-resultado de una fuente secundaria según conveniencia económica.
