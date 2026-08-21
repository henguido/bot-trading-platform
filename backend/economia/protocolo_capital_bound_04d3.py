"""BOT 2.0-04D-3: prueba de imposibilidad por cota mínima de capital.

No usa datos 2026, no reoptimiza 04C-2 y no autoriza leverage adicional.
"""
from decimal import Decimal

# Resultado neto notional del portafolio BTC+ETH 04C-2 para 2022.
RETORNO_NOTIONAL_2022_04C2 = Decimal("0.012413")

# Gate de producción heredado: peor año committed >= 2%.
PEOR_ANIO_PROD_MIN_04C2 = Decimal("0.02")

# Sin borrowing/leverage, comprar el Spot cash exige como mínimo 1x del notional.
CAPITAL_MINIMO_SPOT_MULTIPLO_04D3 = Decimal("1")

LEVERAGE_ADICIONAL_PERMITIDO_04D3 = False
EXCLUIR_2022_PERMITIDO_04D3 = False
CAMBIAR_GATE_PERMITIDO_04D3 = False
DESARROLLO_2026_ABIERTO_04D3 = False

VEREDICTO_04D3 = "CARRY_NO_RESCATABLE_SIN_LEVERAGE_04D3"
