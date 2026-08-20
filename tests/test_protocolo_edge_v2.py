"""Candados del protocolo 04B-v2."""
from __future__ import annotations

import ast
from pathlib import Path

from backend.economia.protocolo_edge_v2 import (
    FOLDS_VALIDACION_ENE_ABR_2026,
    MESES_CROSS_SECTION_UPLIFT_POSITIVO_MINIMOS,
    TEST_DESDE_MS,
    TEST_HASTA_MS,
    VALIDACION_DESDE_MS,
    VALIDACION_HASTA_MS,
    configuraciones_v2_predeclaradas,
)

RAIZ = Path(__file__).resolve().parents[1]
RUNNER = RAIZ / "scripts" / "run_edge_validacion_v2.py"


def test_split_temporal_mantiene_mayo_julio_como_holdout_cerrado():
    assert VALIDACION_DESDE_MS < VALIDACION_HASTA_MS
    assert VALIDACION_HASTA_MS < TEST_DESDE_MS
    assert TEST_DESDE_MS < TEST_HASTA_MS
    assert all(f.valid_hasta_ms <= TEST_DESDE_MS for f in FOLDS_VALIDACION_ENE_ABR_2026)
    assert len(FOLDS_VALIDACION_ENE_ABR_2026) == 4
    assert MESES_CROSS_SECTION_UPLIFT_POSITIVO_MINIMOS == 3


def test_grilla_v2_tiene_64_configuraciones_predeclaradas():
    configs = configuraciones_v2_predeclaradas()
    assert len(configs) == 64
    assert len(set(configs)) == 64
    assert {c.horizonte_horas for c in configs} == {4, 8, 12, 24}
    assert {c.rank_bins for c in configs} == {3, 4}
    assert {c.regimen_bins for c in configs} == {3, 4}
    assert {c.min_muestras for c in configs} == {30, 60}
    assert {c.max_radio for c in configs} == {0, 1}


def test_runner_no_usa_holdout_final():
    fuente = RUNNER.read_text(encoding="utf-8")
    assert "end_ms = VALIDACION_HASTA_MS" in fuente
    assert "TEST_HASTA_MS" not in fuente
    assert "test_may_jul_open" in fuente
    arbol = ast.parse(fuente)
    assert "VALIDACION_HASTA_MS" in ast.dump(arbol)
