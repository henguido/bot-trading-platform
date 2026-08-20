"""Protocolo PREDECLARADO para BOT 2.0-04B-v11.

v10 falsó cuatro factores de horizonte 24h. v11 cambia el horizonte, no los
thresholds después de ver resultados: evalúa momentum cross-sectional de 1, 2
y 3 semanas y su versión ajustada por riesgo basada en un Sharpe-style de
retornos diarios, con rebalanceo semanal.

La hipótesis es direccional: mayor momentum/RMOM debería preceder mayor retorno
la semana siguiente. No se prueba la orientación contraria para evitar duplicar
grados de libertad. Solo desarrollo 2022-2025; 2026 permanece cerrado.
"""
from __future__ import annotations

from decimal import Decimal

HORIZONTE_HORAS_V11 = 24 * 7
INTERVALO_HORAS_V11 = 4
BARRAS_POR_DIA_V11 = 24 // INTERVALO_HORAS_V11
DIAS_POR_SEMANA_V11 = 7
MAX_SEMANAS_FORMACION_V11 = 3

# La barra que cierra el domingo 23:59:59.999 tiene límite lunes 00:00 UTC.
DIA_REBALANCEO_UTC_V11 = 0  # datetime.weekday(): lunes
HORA_REBALANCEO_UTC_V11 = 0

HURDLE_ECONOMICO_BPS_V11 = Decimal("25")
MIN_ACTIVOS_TIMESTAMP_V11 = 15

MOM1 = "mom1"
MOM2 = "mom2"
MOM3 = "mom3"
RMOM1 = "rmom1"
RMOM2 = "rmom2"
RMOM3 = "rmom3"
FACTORES_V11 = (MOM1, MOM2, MOM3, RMOM1, RMOM2, RMOM3)

# Criterios de promoción fijados antes del diagnóstico real de 2025.
SPREAD_MEDIO_MIN_BPS_V11 = Decimal("25")
FRACCION_SPREAD_POSITIVO_MIN_V11 = Decimal("0.55")
MESES_SPREAD_POSITIVOS_MIN_V11 = 8
FOLDS_SPREAD_POSITIVOS_MIN_V11 = 3

MIN_SENALES_TOP1_V11 = 45
FRACCION_TOP1_NETO_POSITIVO_MIN_V11 = Decimal("0.55")
MESES_CON_SENAL_TOP1_MIN_V11 = 11
MESES_TOP1_NETOS_POSITIVOS_MIN_V11 = 8
FOLDS_CON_SENAL_TOP1_MIN_V11 = 4
FOLDS_TOP1_NETOS_POSITIVOS_MIN_V11 = 3

CLASE_PROMETEDORA = "MOMENTUM_PROMETEDOR_V11"
CLASE_SIN_SENAL = "SIN_SENAL_V11"

DESARROLLO_2026_ABIERTO_V11 = False
TEST_MAY_JUL_ABIERTO_V11 = False
