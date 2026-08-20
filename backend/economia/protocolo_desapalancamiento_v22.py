"""Protocolo PREDECLARADO BOT 2.0-04B-v22: desapalancamiento -> rebote Spot 8h.

v21 falsó la continuación simple basada en presión taker compradora + OI
creciente: mostró uplift relativo pequeño pero no edge absoluto suficiente.
v22 NO invierte esa señal. Formula una mecánica distinta, motivada por cascadas
de liquidación/desapalancamiento:

    caída Spot relativa fuerte durante [T-8h,T)
    + contracción de open interest
    + predominio de venta taker
    -> posible rebote Spot durante [T,T+8h].

La caída de precio es indispensable: OI descendente y taker vendedor por sí
solos no constituyen v22. La contribución de derivados se compara contra un
benchmark de simple reversión bottom-quartile de precio.

2026 permanece cerrado. No se ajustan umbrales ni se invierte la hipótesis
tras observar resultados.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Tuple

from backend.economia.protocolo_edge_v2 import UNIVERSO_VALIDACION_V2

UNIVERSO_V22: Tuple[str, ...] = UNIVERSO_VALIDACION_V2
DESDE_V22 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_V22 = datetime(2026, 1, 1, tzinfo=timezone.utc)

VENTANA_FEATURE_HORAS_V22 = 8
HORIZONTE_RETORNO_HORAS_V22 = 8
INTERVALO_SPOT_V22 = "4h"
MIN_SIMBOLOS_POR_TIMESTAMP_V22 = 15

# Shock de precio: bottom quartile cross-sectional del retorno Spot previo 8h.
FRACCION_BOTTOM_PRECIO_V22 = Decimal("0.25")

# Confirmación de desapalancamiento con umbrales de signo económicamente
# naturales, no calibrados por rentabilidad:
# - OI cae durante las 8h previas;
# - taker buy/sell < 1 => volumen taker vendedor domina al comprador.
OI_CAMBIO_MAX_EXCLUSIVO_V22 = Decimal("0")
TAKER_RATIO_MAX_EXCLUSIVO_V22 = Decimal("1")

# Un candidato bottom-quartile que no confirma desapalancamiento se elimina;
# NO se reemplaza por el activo siguiente del ranking.
REEMPLAZO_CANDIDATOS_PERMITIDO_V22 = False

# Mismo modelo conservador de coste de 04B.
COSTE_ROUND_TRIP_BPS_V22 = Decimal("20")
MARGEN_SEGURIDAD_BPS_V22 = Decimal("5")
HURDLE_TOTAL_BPS_V22 = COSTE_ROUND_TRIP_BPS_V22 + MARGEN_SEGURIDAD_BPS_V22

# Gate de transporte; si falla, no se emite veredicto económico.
FRACCION_ARCHIVOS_METRICAS_COMPLETOS_MIN_V22 = Decimal("0.95")
MIN_SIMBOLOS_SPOT_COMPLETOS_V22 = 15

# Gate económico/temporal predeclarado.
MIN_TIMESTAMPS_CON_SENAL_V22 = 200
MIN_MESES_CON_SENAL_V22 = 36
MIN_ANIOS_CON_SENAL_V22 = 4
FRACCION_TIMESTAMPS_NETO_POSITIVO_MIN_V22 = Decimal("0.50")
MIN_MESES_NETO_POSITIVO_V22 = 26
MIN_ANIOS_NETO_POSITIVO_V22 = 3
MEDIA_NETA_BPS_MIN_EXCLUSIVA_V22 = Decimal("0")

# Debe agregar valor sobre ambos controles:
# 1) equal-weight de todo el cross-section;
# 2) simple bottom-quartile de retorno previo, sin OI/taker.
MEDIA_UPLIFT_VS_UNIVERSO_MIN_EXCLUSIVA_V22 = Decimal("0")
MEDIA_UPLIFT_VS_PRECIO_ONLY_MIN_EXCLUSIVA_V22 = Decimal("0")
MIN_ANIOS_UPLIFT_VS_UNIVERSO_POSITIVO_V22 = 3
MIN_ANIOS_UPLIFT_VS_PRECIO_ONLY_POSITIVO_V22 = 3

# Reglas metodológicas.
PERMITE_INVERTIR_SIGNO_V22 = False
PERMITE_AJUSTAR_UMBRALES_POST_RESULTADO_V22 = False
IMPUTACION_PERMITIDA_V22 = False
USA_FUNDING_V22 = False
USA_BASIS_V22 = False
USA_TOPTRADER_RATIO_V22 = False

DESARROLLO_2026_ABIERTO_V22 = False
TEST_MAY_JUL_ABIERTO_V22 = False
SURVIVORSHIP_PENDIENTE_V22 = True
