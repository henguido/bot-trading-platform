"""BOT 2.0-04D-1: protocolo read-only de factibilidad operativa para 04C-2.

No cambia la economía de 04C-2 y no autoriza órdenes.
"""
from decimal import Decimal

SIMBOLOS_04D1 = ("BTCUSDT", "ETHUSDT")
NOTIONALES_USD_04D1 = (
    Decimal("500"),
    Decimal("5000"),
    Decimal("25000"),
    Decimal("100000"),
)

# El drag de 60 bps fue congelado en 04C-2. 04D-1 solo mide cuánto consume
# el libro; no cambia ni recalibra este presupuesto con el resultado.
DRAG_ALL_IN_BPS_HEREDADO_04C2 = Decimal("60")
MAX_FRICCION_LIBRO_ROUNDTRIP_BPS_04D1 = Decimal("10")

# Screening de arquitectura de margen. 1x significa USDT de margen igual al
# notional short; el test es deliberadamente más favorable que la realidad
# porque ignora maintenance margin, fees y mark/index basis.
MARGEN_FUTURES_ESTATICO_MULTIPLO_04D1 = Decimal("1")
CAPITAL_SPOT_MULTIPLO_04D1 = Decimal("1")
CAPITAL_TOTAL_REFERENCIA_04C2 = Decimal("2")

SPOT_DEPTH_URL_04D1 = "https://api.binance.com/api/v3/depth"
FUTURES_DEPTH_URL_04D1 = "https://fapi.binance.com/fapi/v1/depth"
DEPTH_LIMIT_04D1 = 1000
TIMEOUT_04D1_SEGUNDOS = 20
REINTENTOS_04D1 = 2

# Seguridad / metodología.
ORDENES_PERMITIDAS_04D1 = False
CREDENCIALES_REQUERIDAS_04D1 = False
RECALIBRAR_GATE_04C2_PERMITIDO_04D1 = False
DESARROLLO_2026_RETORNOS_ABIERTO_04D1 = False
