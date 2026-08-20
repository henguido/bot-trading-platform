"""Candados contra data snooping del protocolo 04B."""
from decimal import Decimal

from backend.economia.protocolo_experimento_edge import (
    COBERTURA_MINIMA_VALIDACION,
    CORTE_TEST_MS,
    CORTE_VALIDACION_MS,
    DATASET_DESDE_MS,
    DATASET_HASTA_MS,
    FOLDS_MINIMOS_CON_UPLIFT_POSITIVO,
    FOLDS_VALIDACION_2025,
    FRACCION_TIMESTAMPS_UPLIFT_POSITIVO_MINIMA,
    HORIZONTES_HORAS,
    INTERVALO_HORAS,
    INTERVALO_KLINE,
    MESES_CROSS_SECTION_MINIMOS,
    MESES_CROSS_SECTION_UPLIFT_POSITIVO_MINIMOS,
    SURVIVORSHIP_PENDIENTE,
    UNIVERSO_FALSACION,
    UPLIFT_CROSS_SECTION_MINIMO,
    VENTANA_ESTADO_HORAS,
    configuraciones_predeclaradas,
)


def test_universo_falsacion_tiene_20_simbolos_unicos_usdt():
    assert len(UNIVERSO_FALSACION) == 20
    assert len(set(UNIVERSO_FALSACION)) == 20
    assert all(s.endswith("USDT") for s in UNIVERSO_FALSACION)


def test_resolucion_4h_cubre_exactamente_horizontes_y_ventana():
    assert INTERVALO_KLINE == "4h"
    assert INTERVALO_HORAS == 4
    assert VENTANA_ESTADO_HORAS == 24
    assert all(h % INTERVALO_HORAS == 0 for h in HORIZONTES_HORAS)
    assert VENTANA_ESTADO_HORAS % INTERVALO_HORAS == 0


def test_particion_global_es_2022_train_2025_valid_2026_test():
    assert DATASET_DESDE_MS < CORTE_VALIDACION_MS < CORTE_TEST_MS < DATASET_HASTA_MS


def test_validacion_2025_tiene_cuatro_folds_no_solapados_y_test_no_entra():
    assert len(FOLDS_VALIDACION_2025) == 4
    assert FOLDS_VALIDACION_2025[0].valid_desde_ms == CORTE_VALIDACION_MS
    assert FOLDS_VALIDACION_2025[-1].valid_hasta_ms == CORTE_TEST_MS
    for a, b in zip(FOLDS_VALIDACION_2025, FOLDS_VALIDACION_2025[1:]):
        assert a.valid_hasta_ms == b.valid_desde_ms
    assert all(f.valid_hasta_ms <= CORTE_TEST_MS for f in FOLDS_VALIDACION_2025)


def test_grilla_predeclarada_tiene_72_configuraciones_unicas():
    configs = configuraciones_predeclaradas()
    assert len(configs) == 72
    assert len(set(configs)) == 72
    assert {c.horizonte_horas for c in configs} == set(HORIZONTES_HORAS)


def test_criterios_minimos_quedan_fijos_antes_de_resultados():
    assert COBERTURA_MINIMA_VALIDACION == Decimal("0.50")
    assert FOLDS_MINIMOS_CON_UPLIFT_POSITIVO == 3
    assert UPLIFT_CROSS_SECTION_MINIMO == Decimal("0")
    assert FRACCION_TIMESTAMPS_UPLIFT_POSITIVO_MINIMA == Decimal("0.50")
    assert MESES_CROSS_SECTION_MINIMOS == 12
    assert MESES_CROSS_SECTION_UPLIFT_POSITIVO_MINIMOS == 8
    assert SURVIVORSHIP_PENDIENTE is True
