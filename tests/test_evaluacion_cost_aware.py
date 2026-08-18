"""Pruebas del evaluador cost-aware offline."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.economia.evaluacion_celdas import PrediccionCeldas
from backend.economia.evaluacion_cost_aware import (
    DISPONIBLE,
    NO_DISPONIBLE,
    evaluar_senales_cost_aware,
)
from backend.economia.protocolo_edge_v3 import FOLDS_VALIDACION_ENE_ABR_2026

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "evaluacion_cost_aware.py"


def pred(symbol: str, ts: int, *, predicho_bps, real_bps) -> PrediccionCeldas:
    return PrediccionCeldas(
        symbol=symbol,
        timestamp_ms=ts,
        predicho=Decimal(str(predicho_bps)) / Decimal("10000"),
        real=Decimal(str(real_bps)) / Decimal("10000"),
        radio_usado=0,
        n_muestras_soporte=30,
        n_symbols_soporte=3,
        n_timestamps_soporte=20,
        max_symbol_share=Decimal("0.34"),
        max_timestamp_share=Decimal("0.05"),
    )


def grupo(ts: int, *, top_predicho=30, top_real=40, resto_real=0, n=15):
    salida = [pred("S00", ts, predicho_bps=top_predicho, real_bps=top_real)]
    for i in range(1, n):
        salida.append(pred(
            f"S{i:02d}",
            ts,
            predicho_bps=10 - i / 100,
            real_bps=resto_real,
        ))
    return salida


def test_solo_selecciona_top_si_supera_hurdle_coste_mas_margen():
    ts1 = FOLDS_VALIDACION_ENE_ABR_2026[0].valid_desde_ms + 1
    ts2 = FOLDS_VALIDACION_ENE_ABR_2026[0].valid_desde_ms + 2
    datos = grupo(ts1, top_predicho=30, top_real=40) + grupo(
        ts2, top_predicho=24, top_real=100)

    r = evaluar_senales_cost_aware(
        datos,
        coste_total_bps=20,
        margen_seguridad_bps=5,
        min_activos_cross_section=15,
    )

    assert r.estado == DISPONIBLE
    assert r.hurdle_predicho_bps == Decimal("25")
    assert r.n_timestamps_evaluables == 2
    assert r.n_timestamps_senal == 1
    assert r.n_senales == 1
    assert r.cobertura_timestamps_senal == Decimal("0.5")
    assert r.senales[0].symbol == "S00"
    assert r.senales[0].real_neto_despues_margen_bps == Decimal("15")
    assert r.retorno_neto_despues_margen_medio_bps == Decimal("15")
    assert r.uplift_bruto_medio_bps > 0


def test_timestamps_con_poca_seccion_transversal_no_entran_como_senal():
    ts_pobre = FOLDS_VALIDACION_ENE_ABR_2026[0].valid_desde_ms + 1
    ts_valido = FOLDS_VALIDACION_ENE_ABR_2026[0].valid_desde_ms + 2
    datos = grupo(ts_pobre, top_predicho=100, top_real=100, n=14)
    datos += grupo(ts_valido, top_predicho=30, top_real=40, n=15)

    r = evaluar_senales_cost_aware(
        datos,
        coste_total_bps=20,
        margen_seguridad_bps=5,
        min_activos_cross_section=15,
    )

    assert r.n_timestamps_evaluables == 1
    assert r.n_timestamps_senal == 1
    assert {s.timestamp_ms for s in r.senales} == {ts_valido}


def test_reporta_estabilidad_mensual_y_por_fold():
    datos = []
    for i, fold in enumerate(FOLDS_VALIDACION_ENE_ABR_2026):
        real_top = 40 if i < 3 else -10
        datos.extend(grupo(
            fold.valid_desde_ms + 1,
            top_predicho=30,
            top_real=real_top,
            resto_real=0,
        ))

    r = evaluar_senales_cost_aware(
        datos,
        coste_total_bps=20,
        margen_seguridad_bps=5,
        min_activos_cross_section=15,
        folds=FOLDS_VALIDACION_ENE_ABR_2026,
    )

    assert r.n_meses_con_senal == 4
    assert r.meses_neto_despues_margen_positivo == 3
    assert r.n_folds_con_senal == 4
    assert r.folds_neto_despues_margen_positivo == 3
    assert r.fraccion_timestamps_neto_despues_margen_positivo == Decimal("0.75")


def test_sin_timestamps_evaluables_falla_cerrado():
    r = evaluar_senales_cost_aware(
        [],
        coste_total_bps=20,
        margen_seguridad_bps=5,
        min_activos_cross_section=15,
    )
    assert r.estado == NO_DISPONIBLE
    assert r.motivo == "sin_timestamps_evaluables"
    assert r.retorno_neto_despues_margen_medio_bps is None


def test_sin_senales_sobre_hurdle_no_inventa_retorno_cero():
    ts = FOLDS_VALIDACION_ENE_ABR_2026[0].valid_desde_ms + 1
    r = evaluar_senales_cost_aware(
        grupo(ts, top_predicho=24, top_real=100),
        coste_total_bps=20,
        margen_seguridad_bps=5,
        min_activos_cross_section=15,
    )
    assert r.estado == NO_DISPONIBLE
    assert r.motivo == "sin_senales_sobre_hurdle"
    assert r.retorno_neto_despues_margen_medio_bps is None


@pytest.mark.parametrize("kwargs", [
    {"coste_total_bps": -1, "margen_seguridad_bps": 5},
    {"coste_total_bps": 20, "margen_seguridad_bps": -1},
    {"coste_total_bps": 20, "margen_seguridad_bps": 5, "hurdle_predicho_bps": -1},
    {"coste_total_bps": 20, "margen_seguridad_bps": 5, "max_senales_por_timestamp": 0},
    {"coste_total_bps": 20, "margen_seguridad_bps": 5, "min_activos_cross_section": 0},
])
def test_parametros_invalidos_fallan_cerrado(kwargs):
    with pytest.raises(ValueError):
        evaluar_senales_cost_aware([], **kwargs)


def test_modulo_no_importa_red_bd_scanner_risk_llm_ni_trading():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    prohibidos = (
        "requests", "sqlalchemy", "openai", "binance", "scanner",
        "MotorRiesgo", "SessionLocal", "real_trading",
    )
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            texto = ast.dump(nodo)
            for p in prohibidos:
                assert p not in texto
