"""Candados del protocolo 04B-v3."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

from backend.economia.protocolo_edge_v3 import (
    COSTE_TOTAL_MINIMO_OPERABLE_BPS,
    FOLDS_VALIDACION_ENE_ABR_2026,
    HORIZONTE_V3_HORAS,
    HURDLE_EDGE_PREDICHO_BPS,
    MARGEN_SEGURIDAD_OPERABLE_BPS,
    MIN_CONFIGS_COST_AWARE_APTAS_V3,
    TEST_DESDE_MS,
    TEST_HASTA_MS,
    VALIDACION_DESDE_MS,
    VALIDACION_HASTA_MS,
    configuraciones_v3_predeclaradas,
)

RAIZ = Path(__file__).resolve().parents[1]
RUNNER = RAIZ / "scripts" / "run_edge_validacion_v3.py"


def test_split_temporal_v3_mantiene_mayo_julio_como_holdout_cerrado():
    assert VALIDACION_DESDE_MS < VALIDACION_HASTA_MS
    assert VALIDACION_HASTA_MS < TEST_DESDE_MS
    assert TEST_DESDE_MS < TEST_HASTA_MS
    assert all(f.valid_hasta_ms <= TEST_DESDE_MS for f in FOLDS_VALIDACION_ENE_ABR_2026)
    assert len(FOLDS_VALIDACION_ENE_ABR_2026) == 4


def test_hurdle_v3_es_coste_mas_margen_predeclarado():
    assert COSTE_TOTAL_MINIMO_OPERABLE_BPS == Decimal("20")
    assert MARGEN_SEGURIDAD_OPERABLE_BPS == Decimal("5")
    assert HURDLE_EDGE_PREDICHO_BPS == Decimal("25")
    assert HURDLE_EDGE_PREDICHO_BPS == (
        COSTE_TOTAL_MINIMO_OPERABLE_BPS + MARGEN_SEGURIDAD_OPERABLE_BPS
    )


def test_grilla_v3_usa_solo_cluster_robusto_v2_y_no_expande_busqueda():
    configs = configuraciones_v3_predeclaradas()
    assert len(configs) == 4
    assert len(set(configs)) == 4
    assert {c.horizonte_horas for c in configs} == {HORIZONTE_V3_HORAS}
    assert {c.rank_bins for c in configs} == {3}
    assert {c.regimen_bins for c in configs} == {3}
    assert {c.min_muestras for c in configs} == {30, 60}
    assert {c.max_radio for c in configs} == {0, 1}
    assert {c.hurdle_predicho_bps for c in configs} == {Decimal("25")}
    assert MIN_CONFIGS_COST_AWARE_APTAS_V3 == 2


def test_runner_v3_no_usa_holdout_final():
    fuente = RUNNER.read_text(encoding="utf-8")
    assert "end_ms = VALIDACION_HASTA_MS" in fuente
    assert "TEST_HASTA_MS" not in fuente
    assert "test_may_jul_open" in fuente
    arbol = ast.parse(fuente)
    assert "VALIDACION_HASTA_MS" in ast.dump(arbol)
    assert "TEST_DESDE_MS" in ast.dump(arbol)
