"""BOT 2.0-04B-1 · evaluacion out-of-sample del edge empirico."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

from backend.economia.edge_empirico import ajustar_modelo
from backend.economia.edge_historico import (
    EstadoHistorico, EtiquetaHorizonte, ObservacionEdge,
)
from backend.economia.evaluacion_edge import DISPONIBLE, NO_DISPONIBLE, evaluar_holdout

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "evaluacion_edge.py"


def obs(symbol, ts, *, qv, trades, rango, momentum, retorno, h=4):
    return ObservacionEdge(
        estado=EstadoHistorico(
            symbol=symbol, timestamp_ms=ts, close=Decimal("100"),
            quote_volume_24h=Decimal(str(qv)), trades_24h=trades,
            rango_24h=Decimal(str(rango)),
            momentum_cierre_24h_pct=Decimal(str(momentum))),
        etiquetas=(EtiquetaHorizonte(
            h, Decimal(str(retorno)),
            max(Decimal("0"), Decimal(str(retorno))),
            min(Decimal("0"), Decimal(str(retorno)))),),
    )


def train():
    return [
        obs("P1", 10, qv=1e6, trades=10000, rango=.05, momentum=5, retorno=.01),
        obs("P2", 20, qv=1.1e6, trades=11000, rango=.055, momentum=5.5, retorno=.02),
        obs("P3", 30, qv=.9e6, trades=9000, rango=.045, momentum=4.5, retorno=.03),
        obs("N1", 40, qv=1e4, trades=100, rango=.01, momentum=-5, retorno=-.01),
        obs("N2", 50, qv=1.1e4, trades=110, rango=.012, momentum=-5.5, retorno=-.02),
        obs("N3", 60, qv=.9e4, trades=90, rango=.008, momentum=-4.5, retorno=-.03),
    ]


def validacion():
    return [
        obs("VP", 100, qv=1e6, trades=10000, rango=.05, momentum=5, retorno=.04),
        obs("VN", 110, qv=1e4, trades=100, rango=.01, momentum=-5, retorno=-.04),
    ]


def test_metricas_holdout_son_out_of_sample_y_deterministas():
    modelo = ajustar_modelo(train(), horizonte_horas=4, k=3)
    r = evaluar_holdout(modelo, validacion())
    assert r.estado == DISPONIBLE
    assert r.n_objetivo == 2 and r.n_estimadas == 2
    assert r.cobertura == Decimal("1")
    assert r.retorno_real_medio == Decimal("0.00")
    assert r.retorno_predicho_medio == Decimal("0.00")
    assert r.mae_prediccion == Decimal("0.02")
    assert r.sesgo_prediccion == Decimal("0.00")
    assert r.exactitud_direccional == Decimal("1")


def test_cuartil_superior_mide_uplift_sin_elegir_threshold():
    modelo = ajustar_modelo(train(), horizonte_horas=4, k=3)
    r = evaluar_holdout(modelo, validacion())
    assert r.n_top25 == 1
    assert r.retorno_real_top25_predicho == Decimal("0.04")
    assert r.uplift_top25_vs_baseline == Decimal("0.04")
    assert r.n_predicho_positivo == 1
    assert r.retorno_real_predicho_positivo == Decimal("0.04")


def test_validacion_antes_del_fin_de_train_no_se_evalua_como_si_fuera_oos():
    modelo = ajustar_modelo(train(), horizonte_horas=4, k=3)
    datos = [obs("TEMPRANO", 50, qv=1e6, trades=10000,
                 rango=.05, momentum=5, retorno=.99)]
    r = evaluar_holdout(modelo, datos)
    assert r.estado == NO_DISPONIBLE
    assert r.n_objetivo == 1 and r.n_estimadas == 0
    assert r.cobertura == Decimal("0")
    assert r.retorno_real_medio is None


def test_observacion_sin_label_del_horizonte_no_entra_denominador():
    modelo = ajustar_modelo(train(), horizonte_horas=4, k=3)
    otro_h = obs("H8", 120, qv=1e6, trades=10000,
                 rango=.05, momentum=5, retorno=.5, h=8)
    r = evaluar_holdout(modelo, validacion() + [otro_h])
    assert r.n_objetivo == 2
    assert r.n_estimadas == 2


def test_orden_de_validacion_no_cambia_resumen():
    modelo = ajustar_modelo(train(), horizonte_horas=4, k=3)
    a = evaluar_holdout(modelo, validacion())
    b = evaluar_holdout(modelo, reversed(validacion()))
    assert a == b


def test_distancias_quedan_observables_para_calibrar_ood_despues():
    modelo = ajustar_modelo(train(), horizonte_horas=4, k=3)
    r = evaluar_holdout(modelo, validacion())
    assert r.distancia_p50 is not None
    assert r.distancia_p95 is not None
    assert r.distancia_p50 >= 0 and r.distancia_p95 >= 0


def test_evaluacion_no_importa_costes_risk_scanner_llm_ml_ni_random():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    texto = ast.dump(arbol)
    for prohibido in (
        "costes", "MotorRiesgo", "scanner", "openai", "sklearn", "numpy",
        "pandas", "random", "requests", "sqlalchemy", "SessionLocal",
    ):
        assert prohibido not in texto
