# 04C-3 — Corrección de calendario pre-PnL

**Estado: corrección factual realizada antes de ejecutar el runner histórico 04C-3.**

El primer run de CI de 04C-3 se detuvo en unit tests; el paso `Run fixed calendar-spread replication` quedó `skipped`. Por tanto todavía no se había observado ningún PnL 04C-3.

El test del fixture de delivery detectó que el texto inicial de `04C-3-calendar-spread.md` describía por error el vencimiento como "tercer viernes". Los 32 delivery prices previamente capturados de Binance y los códigos de contrato históricos (`220325`, `220624`, `220930`, `221230`, etc.) muestran la convención correcta para esta muestra:

**último viernes de marzo, junio, septiembre y diciembre a las 08:00 UTC.**

Se corrigió `protocolo_calendar_04c3.py` para calcular el último viernes. Esta corrección modifica solamente las fechas contractuales para que coincidan con los contratos Binance reales; no cambia:

- BTC/ETH;
- holding 28 días;
- lookback funding 28 días;
- regla `predicted_net > 0`;
- coste 60 bps por trade;
- capital de referencia 1x;
- gates económicos o de producción;
- dirección long perpetual / short quarterly;
- 2026 cerrado.

Para 04C-3, cualquier mención a "tercer viernes" en el documento inicial queda **supersedida por esta corrección pre-PnL**. No se permite una nueva modificación de calendario después de observar PnL.
