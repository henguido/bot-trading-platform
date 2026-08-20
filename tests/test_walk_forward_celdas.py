"""Pruebas walk-forward del estimador escalable por celdas."""
from decimal import Decimal

import pytest

from backend.economia.edge_historico import EstadoHistorico, EtiquetaHorizonte, ObservacionEdge
from backend.economia.validacion_edge import HORA_MS
from backend.economia.walk_forward_celdas import evaluar_walk_forward_celdas
from backend.economia.walk_forward_edge import FoldTemporal


def obs(symbol: str, hora: int, h: int = 4) -> ObservacionEdge:
    # Features periodicas: validacion permanece dentro del soporte de train.
    ciclo = hora % 20
    retorno = Decimal(str((ciclo - 10) / 1000))
    return ObservacionEdge(
        estado=EstadoHistorico(
            symbol=symbol,
            timestamp_ms=hora * HORA_MS - 1,
            close=Decimal("100"),
            quote_volume_24h=Decimal(1000 + ciclo * 50),
            trades_24h=100 + ciclo * 5,
            rango_24h=Decimal(str(.02 + (ciclo % 5) * .005)),
            momentum_cierre_24h_pct=Decimal(str(-2 + (ciclo % 9) * .5)),
        ),
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=h,
            retorno_cierre=retorno,
            mfe=max(Decimal("0"), retorno),
            mae=min(Decimal("0"), retorno),
        ),),
    )


def dataset():
    return [
        obs(symbol, hora)
        for hora in range(1, 221)
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    ]


def folds():
    return (
        FoldTemporal(100 * HORA_MS - 1, 140 * HORA_MS - 1),
        FoldTemporal(160 * HORA_MS - 1, 200 * HORA_MS - 1),
    )


def ejecutar(datos=None, fs=None):
    return evaluar_walk_forward_celdas(
        dataset() if datos is None else datos,
        horizonte_horas=4,
        n_bins=3,
        min_muestras=6,
        min_symbols=3,
        min_timestamps=2,
        max_radio=3,
        folds=folds() if fs is None else fs,
    )


def test_walk_forward_usa_train_expansivo_embargo_y_rejilla_no_solapada():
    r = ejecutar()
    assert len(r.folds) == 2
    assert all(f.n_train_no_solapado < f.n_train_crudo for f in r.folds)
    assert all(f.n_descartadas_embargo > 0 for f in r.folds)
    # Cada ventana tiene 40 horas; en rejilla h=4 son 10 timestamps x 3 símbolos.
    assert all(f.n_validacion_no_solapada == 30 for f in r.folds)
    assert r.n_objetivo == 60
    assert r.n_estimadas > 0
    assert r.cobertura > 0


def test_reporta_baseline_objetivo_y_sesgo_de_cobertura():
    r = ejecutar()
    assert r.retorno_real_objetivo_medio is not None
    assert r.retorno_real_estimadas_medio is not None
    assert r.sesgo_seleccion_cobertura is not None
    assert r.mae_prediccion is not None
    assert r.exactitud_direccional is not None
    assert r.uplift_top25_vs_estimadas is not None
    assert r.uplift_top25_vs_objetivo is not None


def test_orden_de_entrada_no_cambia_resultado():
    a = ejecutar(dataset())
    b = ejecutar(reversed(dataset()))
    assert a == b


def test_folds_solapados_fallan():
    fs = (
        FoldTemporal(100 * HORA_MS - 1, 150 * HORA_MS - 1),
        FoldTemporal(140 * HORA_MS - 1, 180 * HORA_MS - 1),
    )
    with pytest.raises(ValueError, match="solaparse"):
        ejecutar(fs=fs)


def test_embargo_menor_al_horizonte_falla():
    with pytest.raises(ValueError, match="embargo_horas"):
        evaluar_walk_forward_celdas(
            dataset(), horizonte_horas=4, n_bins=3,
            min_muestras=6, min_symbols=3, min_timestamps=2, max_radio=3,
            folds=folds(), embargo_horas=3)
