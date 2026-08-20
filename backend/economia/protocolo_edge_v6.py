"""Protocolo PREDECLARADO para BOT 2.0-04B-v6.

v5 demostro que la familia relativa v2-v4 no produce edge long spot neto al
cierre de 8h: las predicciones >=25 bps aparecen solo en regimenes negativos y,
aun sin filtro de regimen, el retorno neto medio sigue siendo negativo.

v6 NO cambia el modelo ni baja el hurdle. Prueba una hipotesis distinta y
acotada en desarrollo 2025: esas senales defensivas podrian contener rebotes
intrahorizonte aprovechables si la salida se hace con un bracket explicito y
conservador, en lugar de esperar siempre al cierre de 8h.

Solo desarrollo 2025. Enero-abril 2026 no se usa. Mayo-julio 2026 permanece
cerrado como unico holdout final aun no abierto.
"""
from __future__ import annotations

from decimal import Decimal

HORIZONTE_HORAS_V6 = 8

# Mismo presupuesto economico de v3-v5 para no rescatar la familia bajando
# costes. 20 bps round-trip + 5 bps de margen de seguridad.
COSTE_TOTAL_BPS_V6 = Decimal("20")
MARGEN_SEGURIDAD_BPS_V6 = Decimal("5")
HURDLE_ECONOMICO_BPS_V6 = COSTE_TOTAL_BPS_V6 + MARGEN_SEGURIDAD_BPS_V6

# Bracket derivado para una relacion neta aproximada 2:1 despues del hurdle:
# stop bruto -50 -> -75 bps despues de coste+margen;
# target bruto +175 -> +150 bps despues de coste+margen.
STOP_BRUTO_BPS_V6 = Decimal("50")
TARGET_BRUTO_BPS_V6 = Decimal("175")
STOP_NETO_DESPUES_HURDLE_BPS_V6 = -STOP_BRUTO_BPS_V6 - HURDLE_ECONOMICO_BPS_V6
TARGET_NETO_DESPUES_HURDLE_BPS_V6 = TARGET_BRUTO_BPS_V6 - HURDLE_ECONOMICO_BPS_V6

# Ambiguedad intrabar: con velas 4h no se conoce el orden exacto si stop y
# target aparecen dentro de la misma ventana. La evidencia v6 usa peor caso:
# cualquier toque de stop gana sobre target.
POLITICA_AMBIGUEDAD_V6 = "STOP_PRIORITARIO_PEOR_CASO"

# Senales: exactamente las cost-aware de v5 antes del filtro de regimen.
# No se cambia el modelo, no se optimiza threshold y se conserva una senal
# maxima por timestamp como en v3-v5.
HURDLE_PREDICHO_BPS_V6 = HURDLE_ECONOMICO_BPS_V6
MAX_SENALES_POR_TIMESTAMP_V6 = 1

# Criterios de diagnostico en 2025. Sirven solo para decidir si merece la pena
# formalizar una familia de salida para el holdout; no autorizan trading.
MIN_SENALES_V6 = 100
FRACCION_RESULTADOS_POSITIVOS_MIN_V6 = Decimal("0.50")
MESES_CON_SENAL_MIN_V6 = 12
MESES_NETOS_POSITIVOS_MIN_V6 = 8
FOLDS_CON_SENAL_MIN_V6 = 4
FOLDS_NETOS_POSITIVOS_MIN_V6 = 3

# La familia heredada contiene 4 configuraciones. Exigimos que al menos 3
# sobrevivan para no basar la decision en una variante aislada.
CONFIGS_DIAGNOSTICO_V6 = 4
CONFIGS_MINIMAS_APTAS_V6 = 3

VALIDACION_2026_ABIERTA_V6 = False
TEST_MAY_JUL_ABIERTO_V6 = False
