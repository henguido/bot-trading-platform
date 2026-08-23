from __future__ import annotations

from decimal import Decimal

# BOT 2.0 — 04H-1
# Protocolo económico congelado ANTES de observar PnL cross-venue.

ACTIVOS_04H1 = ("BTC", "ETH", "SOL")
ANIOS_04H1 = (2024, 2025)

VENUE_LONG_04H1 = "BINANCE_USDM_PERPETUAL"
VENUE_SHORT_04H1 = "HYPERLIQUID_PERPETUAL"
DIRECCION_04H1 = "LONG_BINANCE_SHORT_HYPERLIQUID"

PESO_POR_ACTIVO_04H1 = Decimal("0.3333333333333333333333333333")
LEVERAGE_POR_PATA_04H1 = Decimal("2")

# Drag all-in anual predeclarado sobre notional de referencia.
# Caso primario y stress. No se usarán VIP, BNB discount ni maker fills
# retrospectivos para reducir estos supuestos después de ver resultados.
COSTE_PRIMARIO_BPS_ANUAL_04H1 = Decimal("60")
COSTE_STRESS_BPS_ANUAL_04H1 = Decimal("120")

# Gates económicos mínimos.
SHARPE_ECONOMICO_MIN_04H1 = Decimal("1.0")
MAX_DRAWDOWN_ECONOMICO_04H1 = Decimal("0.10")
TSTAT_HAC_ABS_MIN_04H1 = Decimal("1.96")

# Gates para considerar la estrategia candidata a ingeniería productiva.
RETORNO_MEDIO_ANUAL_CAPITAL_MIN_04H1 = Decimal("0.05")
PEOR_ANIO_CAPITAL_MIN_04H1 = Decimal("0.02")
SHARPE_PRODUCCION_MIN_04H1 = Decimal("2.0")
MAX_DRAWDOWN_PRODUCCION_04H1 = Decimal("0.075")

# Candados metodológicos.
SELECCION_POST_RESULTADO_PERMITIDA_04H1 = False
INVERTIR_DIRECCION_POST_RESULTADO_PERMITIDO_04H1 = False
CAMBIAR_COSTES_POST_RESULTADO_PERMITIDO_04H1 = False
OPTIMIZAR_LEVERAGE_POST_RESULTADO_PERMITIDO_04H1 = False
GPT_PERMITIDO_04H1 = False
CREDENCIALES_PERMITIDAS_04H1 = False
PAPER_OPERATIVO_PERMITIDO_04H1 = False
LIVE_PERMITIDO_04H1 = False
RENDER_PERMITIDO_04H1 = False
DESARROLLO_2026_ABIERTO_04H1 = False

# 04H-1 sí autoriza cálculo histórico económico 2024-2025 una vez que el
# protocolo y sus pruebas estén versionados. 2026 sigue físicamente excluido.
CALCULAR_PNL_2024_2025_PERMITIDO_04H1 = True
