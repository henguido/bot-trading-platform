"""BOT 2.0-04B-0 · estadisticas descriptivas de retornos futuros."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.economia.edge_historico import (
    EstadoHistorico, EtiquetaHorizonte, ObservacionEdge,
)
from backend.economia.estadisticas_edge import resumir_horizonte, resumir_horizontes

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "estadisticas_edge.py"


def obs(retorno, *, mfe="0.02", mae="-0.01", h=4, ts=0):
    estado = EstadoHistorico(
        symbol="BTCUSDT", timestamp_ms=ts, close=Decimal("100"),
        quote_volume_24h=Decimal("1000000"), trades_24h=10000,
        rango_24h=Decimal("0.05"), momentum_cierre_24h_pct=Decimal("2"))
    etiqueta = EtiquetaHorizonte(
        horizonte_horas=h,
        retorno_cierre=Decimal(str(retorno)),
        mfe=Decimal(str(mfe)), mae=Decimal(str(mae)))
    return ObservacionEdge(estado=estado, etiquetas=(etiqueta,))


def test_resume_media_percentiles_y_probabilidad_positiva():
    datos = [obs("-0.02"), obs("-0.01"), obs("0.01"), obs("0.04")]
    r = resumir_horizonte(datos, 4)
    assert r.n == 4
    assert r.retorno_medio == Decimal("0.005")
    # Interpolacion lineal sobre [-.02,-.01,.01,.04]
    assert r.retorno_p25 == Decimal("-0.0125")
    assert r.retorno_p50 == Decimal("0.000")
    assert r.retorno_p75 == Decimal("0.0175")
    assert r.prob_retorno_positivo == Decimal("0.5")


def test_mfe_y_mae_se_resumen_por_separado():
    datos = [
        obs("0", mfe="0.01", mae="-0.04"),
        obs("0", mfe="0.02", mae="-0.03"),
        obs("0", mfe="0.03", mae="-0.02"),
        obs("0", mfe="0.04", mae="-0.01"),
    ]
    r = resumir_horizonte(datos, 4)
    assert r.mfe_p50 == Decimal("0.025")
    assert r.mfe_p75 == Decimal("0.0325")
    assert r.mae_p25 == Decimal("-0.0325")
    assert r.mae_p50 == Decimal("-0.025")


def test_cero_no_cuenta_como_retorno_positivo():
    r = resumir_horizonte([obs("0"), obs("0.01"), obs("-0.01")], 4)
    assert r.prob_retorno_positivo == Decimal(1) / Decimal(3)


def test_ignora_observacion_que_no_tiene_el_horizonte_solicitado():
    r = resumir_horizonte([obs("0.01", h=4), obs("0.50", h=8)], 4)
    assert r.n == 1
    assert r.retorno_medio == Decimal("0.01")


def test_sin_etiquetas_del_horizonte_falla_explicito():
    with pytest.raises(ValueError, match="sin etiquetas"):
        resumir_horizonte([obs("0.01", h=8)], 4)


def test_resumir_varios_horizontes_conserva_orden_solicitado():
    estado = obs("0.01").estado
    o = ObservacionEdge(estado=estado, etiquetas=(
        EtiquetaHorizonte(4, Decimal("0.01"), Decimal("0.02"), Decimal("-0.01")),
        EtiquetaHorizonte(8, Decimal("0.02"), Decimal("0.03"), Decimal("-0.02")),
    ))
    rs = resumir_horizontes([o], horizontes_horas=(8, 4))
    assert [r.horizonte_horas for r in rs] == [8, 4]


@pytest.mark.parametrize("h", [0, -1, True, 4.5])
def test_horizonte_invalido_falla_cerrado(h):
    with pytest.raises(ValueError):
        resumir_horizonte([obs("0.01")], h)


def test_estadisticas_no_importan_cost_model_ni_ml():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    texto = ast.dump(arbol)
    for prohibido in ("costes", "estimacion", "sklearn", "numpy", "pandas",
                       "openai", "binance", "requests", "sqlalchemy"):
        assert prohibido not in texto
