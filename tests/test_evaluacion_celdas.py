"""Pruebas de evaluación fuera de muestra del modelo por celdas."""
from decimal import Decimal

from backend.economia.edge_celdas import ajustar_modelo_celdas
from backend.economia.edge_historico import EstadoHistorico, EtiquetaHorizonte, ObservacionEdge
from backend.economia.evaluacion_celdas import DISPONIBLE, NO_DISPONIBLE, evaluar_holdout_celdas


def obs(symbol, ts, qv, momentum, retorno):
    r = Decimal(str(retorno))
    return ObservacionEdge(
        estado=EstadoHistorico(
            symbol=symbol, timestamp_ms=ts, close=Decimal("100"),
            quote_volume_24h=Decimal(str(qv)), trades_24h=100 + int(qv) % 50,
            rango_24h=Decimal("0.03"), momentum_cierre_24h_pct=Decimal(str(momentum))),
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=4, retorno_cierre=r,
            mfe=max(Decimal("0"), r), mae=min(Decimal("0"), r)),),)


def train():
    return [
        obs(f"S{i % 6}", i, 1000 + i * 10, -2 + (i % 5),
            -.02 + (i % 5) * .01)
        for i in range(1, 41)
    ]


def modelo():
    return ajustar_modelo_celdas(
        train(), horizonte_horas=4, n_bins=3,
        min_muestras=3, min_symbols=2, min_timestamps=3, max_radio=3)


def test_holdout_reporta_cobertura_y_metricas_brutas():
    valid = [
        obs("V1", 100, 1100, -1, .03),
        obs("V2", 101, 1200, 0, -.01),
        obs("V3", 102, 1250, 1, .02),
        obs("V4", 103, 1300, 2, .01),
    ]
    r = evaluar_holdout_celdas(modelo(), valid)
    assert r.estado == DISPONIBLE
    assert r.n_objetivo == 4
    assert 0 < r.n_estimadas <= 4
    assert r.cobertura == Decimal(r.n_estimadas) / Decimal(4)
    assert r.mae_prediccion is not None
    assert r.exactitud_direccional is not None
    assert r.uplift_top25_vs_baseline is not None
    assert r.radio_p50 is not None
    assert r.soporte_muestras_p50 is not None


def test_ood_reduce_cobertura_no_fabrica_prediccion():
    valid = [obs("OOD", 100, 99_999_999, 0, .5)]
    r = evaluar_holdout_celdas(modelo(), valid)
    assert r.estado == NO_DISPONIBLE
    assert r.n_objetivo == 1
    assert r.n_estimadas == 0
    assert r.cobertura == Decimal("0")
    assert r.predicciones == ()


def test_orden_validacion_no_cambia_resultado():
    valid = [
        obs("V1", 100, 1100, -1, .03),
        obs("V2", 101, 1200, 0, -.01),
        obs("V3", 102, 1250, 1, .02),
    ]
    a = evaluar_holdout_celdas(modelo(), valid)
    b = evaluar_holdout_celdas(modelo(), reversed(valid))
    assert a == b
