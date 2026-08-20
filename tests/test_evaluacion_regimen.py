"""Pruebas del filtro de regimen absoluto offline."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.economia.evaluacion_celdas import PrediccionCeldas
from backend.economia.evaluacion_cost_aware import DISPONIBLE, NO_DISPONIBLE
from backend.economia.evaluacion_regimen import evaluar_senales_regimen_cost_aware
from backend.economia.protocolo_edge_v3 import FOLDS_VALIDACION_ENE_ABR_2026

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "evaluacion_regimen.py"


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


def mapa_regimen(predicciones, regimen_por_ts):
    return {
        (p.timestamp_ms, p.symbol): Decimal(str(regimen_por_ts[p.timestamp_ms]))
        for p in predicciones
    }


def test_filtra_timestamps_bajistas_antes_de_evaluar_costes():
    ts_bajista = FOLDS_VALIDACION_ENE_ABR_2026[0].valid_desde_ms + 1
    ts_alcista = FOLDS_VALIDACION_ENE_ABR_2026[0].valid_desde_ms + 2
    datos = grupo(ts_bajista, top_predicho=30, top_real=-100)
    datos += grupo(ts_alcista, top_predicho=30, top_real=40)
    regimen = mapa_regimen(datos, {
        ts_bajista: Decimal("-1"),
        ts_alcista: Decimal("1"),
    })

    r = evaluar_senales_regimen_cost_aware(
        datos,
        regimen,
        regimen_minimo_bps=0,
        coste_total_bps=20,
        margen_seguridad_bps=5,
        min_activos_cross_section=15,
    )

    assert r.estado == DISPONIBLE
    assert r.n_timestamps_entrada == 2
    assert r.n_timestamps_regimen_aprobado == 1
    assert r.cobertura_regimen_timestamps == Decimal("0.5")
    assert r.cobertura_total_timestamps_senal == Decimal("0.5")
    assert r.resultado_cost_aware.n_timestamps_evaluables == 1
    assert {s.timestamp_ms for s in r.resultado_cost_aware.senales} == {ts_alcista}


def test_si_falta_regimen_no_rellena_con_cero():
    ts = FOLDS_VALIDACION_ENE_ABR_2026[0].valid_desde_ms + 1
    datos = grupo(ts, top_predicho=30, top_real=40)

    r = evaluar_senales_regimen_cost_aware(
        datos,
        {},
        regimen_minimo_bps=0,
        coste_total_bps=20,
        margen_seguridad_bps=5,
        min_activos_cross_section=15,
    )

    assert r.estado == NO_DISPONIBLE
    assert r.motivo == "sin_predicciones_regimen_aprobado"
    assert r.n_predicciones_sin_regimen == 15
    assert r.n_timestamps_sin_regimen == 1
    assert r.resultado_cost_aware.estado == NO_DISPONIBLE
    assert r.resultado_cost_aware.motivo == "sin_timestamps_evaluables"


def test_regimen_parcial_no_rompe_minimo_cross_section():
    ts = FOLDS_VALIDACION_ENE_ABR_2026[0].valid_desde_ms + 1
    datos = grupo(ts, top_predicho=30, top_real=40)
    regimen = {
        (p.timestamp_ms, p.symbol): Decimal("1")
        for p in datos[:14]
    }

    r = evaluar_senales_regimen_cost_aware(
        datos,
        regimen,
        regimen_minimo_bps=0,
        coste_total_bps=20,
        margen_seguridad_bps=5,
        min_activos_cross_section=15,
    )

    assert r.estado == DISPONIBLE
    assert r.n_predicciones_regimen_aprobado == 14
    assert r.resultado_cost_aware.estado == NO_DISPONIBLE
    assert r.resultado_cost_aware.motivo == "sin_timestamps_evaluables"


def test_parametros_invalidos_fallan_cerrado():
    with pytest.raises(ValueError):
        evaluar_senales_regimen_cost_aware(
            [],
            {},
            regimen_minimo_bps="NaN",
            coste_total_bps=20,
            margen_seguridad_bps=5,
        )


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
