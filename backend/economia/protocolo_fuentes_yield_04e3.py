"""BOT 2.0-04E-3: auditoría comparativa de fuentes de yield públicas.

No calcula PnL, no observa retornos, no usa credenciales y no abre 2026.
"""
from __future__ import annotations

from datetime import date

ANIOS_04E3 = (2022, 2023, 2024, 2025)
DESDE_04E3 = date(2022, 1, 1)
HASTA_EXCLUSIVO_04E3 = date(2026, 1, 1)

CANDIDATOS_04E3 = ("BINANCE_OPTIONS", "LIDO_STETH", "AAVE_LENDING")

# Binance Vision: inventario directo, sin descargar contenido económico todavía.
BINANCE_S3_04E3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
OPTIONS_EOH_PREFIX_04E3 = "data/option/daily/EOHSummary/"
MIN_DIAS_OPTIONS_POR_ANIO_04E3 = 350
MAX_PAGINAS_S3_04E3 = 20
TIMEOUT_04E3_SEGUNDOS = 30
REINTENTOS_04E3 = 2

# Gate común para que una fuente pueda pasar a auditoría de contenido/económica.
REQUIERE_COBERTURA_2022_2025_04E3 = True
REQUIERE_SIN_API_KEY_04E3 = True
REQUIERE_MECANICA_EXACTA_04E3 = True
REQUIERE_TIMESTAMPS_AUDITABLES_04E3 = True
REQUIERE_TRANSFERENCIA_ACOTABLE_04E3 = True

# Evaluación de acceso derivada de documentación oficial, no de performance.
# Lido: fórmula/reward semantics públicas, pero el subgraph oficial usa [api-key];
# las APIs read-only documentadas exponen APR actual/SMA, no la serie global 2022-2025.
LIDO_SEMANTICA_EXACTA_04E3 = True
LIDO_HISTORICO_OFICIAL_SIN_KEY_VERIFICADO_04E3 = False
LIDO_STATUS_04E3 = "LIDO_SEMANTICA_APTA_TRANSPORTE_HISTORICO_SIN_KEY_NO_VERIFICADO_04E3"

# Aave: ReserveDataUpdated/liquidityIndex definen exactamente el yield on-chain,
# pero no se predeclara un archivo HTTP oficial/no-key 2022-2025 en esta etapa.
AAVE_SEMANTICA_EXACTA_04E3 = True
AAVE_HISTORICO_OFICIAL_SIN_KEY_VERIFICADO_04E3 = False
AAVE_STATUS_04E3 = "AAVE_SEMANTICA_APTA_TRANSPORTE_HISTORICO_SIN_KEY_NO_VERIFICADO_04E3"

OPTIONS_STATUS_APTO_04E3 = "OPTIONS_ARCHIVO_PUBLICO_APTO_04E3"
OPTIONS_STATUS_INCOMPLETO_04E3 = "OPTIONS_ARCHIVO_PUBLICO_INCOMPLETO_04E3"

PNL_PERMITIDO_04E3 = False
DESCARGAR_CONTENIDO_OPTIONS_PERMITIDO_04E3 = False
CREDENCIALES_PERMITIDAS_04E3 = False
PAPER_OPERATIVO_PERMITIDO_04E3 = False
LIVE_PERMITIDO_04E3 = False
RENDER_PERMITIDO_04E3 = False
DESARROLLO_2026_ABIERTO_04E3 = False
IMPUTACION_YIELD_PERMITIDA_04E3 = False
USAR_PRECIO_SECUNDARIO_COMO_YIELD_PERMITIDO_04E3 = False
