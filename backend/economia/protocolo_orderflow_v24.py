"""Protocolo PREDECLARADO BOT 2.0-04B-v24: order flow Spot residual -> 7d.

v23/v23a/v23b demostraron cobertura, semántica y coste de adquisición del
histórico Spot aggTrades sin observar el resultado económico de este diseño.
v24 formula UNA sola hipótesis antes de descargar el calendario de 7.617537 GiB:

    presión compradora agresiva Spot que sea alta incluso después de controlar
    cross-sectionalmente por el retorno del mismo lunes -> retorno Spot relativo
    positivo durante los siete días posteriores.

La residualización intenta separar información de order flow de la relación
mecánica entre compras agresivas y el movimiento de precio ya ocurrido. La
entrada siempre es posterior al cierre de la ventana de feature. Si falla, no
se invierte el signo ni se cambian fechas, horizonte, percentil o hurdle.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Tuple

from backend.economia.protocolo_orderflow_v23b import FECHAS_OBJETIVO_V23B, UNIVERSO_V23B

UNIVERSO_V24: Tuple[str, ...] = UNIVERSO_V23B
FECHAS_FEATURE_V24 = FECHAS_OBJETIVO_V23B
N_FECHAS_FEATURE_V24 = 96

# Feature: lunes UTC completo. isBuyerMaker=False => taker buy; True => taker sell.
DEFINICION_OFI_V24 = "(taker_buy_quote-taker_sell_quote)/(taker_buy_quote+taker_sell_quote)"
RETORNO_CONTEMPORANEO_V24 = "open(T+1d)/open(T)-1"
RESIDUALIZACION_V24 = "OLS_cross_section_OFI_sobre_retorno_contemporaneo_con_intercepto"
PERMITE_WINSORIZACION_V24 = False
PERMITE_CLIPPING_V24 = False

# La señal se decide cuando el lunes ya terminó: entrada martes 00:00 UTC,
# salida el martes siguiente 00:00 UTC. No hay solapamiento entre observaciones.
ENTRADA_DIAS_DESDE_T_V24 = 1
SALIDA_DIAS_DESDE_T_V24 = 8
HORIZONTE_RETORNO_DIAS_V24 = 7
INTERVALO_SPOT_V24 = "4h"

# Elegibilidad/selección cross-sectional.
MIN_SIMBOLOS_POR_TIMESTAMP_V24 = 15
FRACCION_TOP_RESIDUAL_V24 = Decimal("0.25")
SELECCION_V24 = "top_25pct_residual_OFI"
DESEMPATE_V24 = "residual_desc_symbol_asc"

# Controles predeclarados: universo contemporáneo, momentum de precio del lunes
# y OFI crudo. El OFI crudo se reporta como diagnóstico; para aprobar v24, el
# residual debe agregar valor frente al universo y frente al precio-only.
BASELINE_UNIVERSO_V24 = "equal_weight_todos_elegibles"
BASELINE_PRECIO_V24 = "top_25pct_retorno_contemporaneo"
BASELINE_OFI_CRUDO_V24 = "top_25pct_OFI_crudo"

# Coste conservador heredado de 04A/04B.
COSTE_ROUND_TRIP_BPS_V24 = Decimal("20")
MARGEN_SEGURIDAD_BPS_V24 = Decimal("5")
HURDLE_TOTAL_BPS_V24 = COSTE_ROUND_TRIP_BPS_V24 + MARGEN_SEGURIDAD_BPS_V24

# Gate de transporte/datos. Fallarlo produce DATOS_INSUFICIENTES, no falsación.
FRACCION_ARCHIVOS_AGGTRADES_COMPLETOS_MIN_V24 = Decimal("0.95")
MIN_SIMBOLOS_SPOT_COMPLETOS_V24 = 15
FRACCION_FECHAS_CON_MIN_SIMBOLOS_V24 = Decimal("1.00")
REINTENTOS_TRANSPORTE_AGGTRADES_V24 = 1

# Gate económico/temporal. Existe una única configuración.
MIN_TIMESTAMPS_CON_SENAL_V24 = 80
MIN_MESES_CON_SENAL_V24 = 42
MIN_ANIOS_CON_SENAL_V24 = 4
FRACCION_TIMESTAMPS_NETO_POSITIVO_MIN_V24 = Decimal("0.50")
MIN_MESES_NETO_POSITIVO_V24 = 28
MIN_ANIOS_NETO_POSITIVO_V24 = 3
MEDIA_NETA_BPS_MIN_EXCLUSIVA_V24 = Decimal("0")
MEDIA_UPLIFT_VS_UNIVERSO_MIN_EXCLUSIVA_V24 = Decimal("0")
MEDIA_UPLIFT_VS_PRECIO_ONLY_MIN_EXCLUSIVA_V24 = Decimal("0")
MIN_ANIOS_UPLIFT_VS_UNIVERSO_POSITIVO_V24 = 3
MIN_ANIOS_UPLIFT_VS_PRECIO_ONLY_POSITIVO_V24 = 3

# Candados metodológicos.
PERMITE_INVERTIR_SIGNO_V24 = False
PERMITE_AJUSTAR_UMBRALES_POST_RESULTADO_V24 = False
PERMITE_CAMBIAR_FECHAS_POST_RESULTADO_V24 = False
PERMITE_CAMBIAR_HORIZONTE_POST_RESULTADO_V24 = False
IMPUTACION_PERMITIDA_V24 = False
USA_FUTURES_V24 = False
USA_OI_V24 = False
USA_FUNDING_V24 = False
USA_GPT_V24 = False

DESARROLLO_2026_ABIERTO_V24 = False
TEST_MAY_JUL_ABIERTO_V24 = False
SURVIVORSHIP_PENDIENTE_V24 = True
