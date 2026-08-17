"""BOT 2.0-04B-1 · estimador empirico deterministico de edge bruto."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.economia.edge_empirico import (
    DISPONIBLE,
    NO_DISPONIBLE,
    ajustar_modelo,
    estimar_edge,
    seleccionar_vecinos,
)
from backend.economia.edge_historico import (
    EstadoHistorico, EtiquetaHorizonte, ObservacionEdge,
)

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "edge_empirico.py"


def obs(symbol, ts, *, qv, trades, rango, momentum, retorno, h=4,
        mfe=None, mae=None):
    estado = EstadoHistorico(
        symbol=symbol,
        timestamp_ms=ts,
        close=Decimal("100"),
        quote_volume_24h=Decimal(str(qv)),
        trades_24h=int(trades),
        rango_24h=Decimal(str(rango)),
        momentum_cierre_24h_pct=Decimal(str(momentum)),
    )
    r = Decimal(str(retorno))
    etiqueta = EtiquetaHorizonte(
        horizonte_horas=h,
        retorno_cierre=r,
        mfe=Decimal(str(mfe if mfe is not None else max(0, float(r)))),
        mae=Decimal(str(mae if mae is not None else min(0, float(r)))),
    )
    return ObservacionEdge(estado=estado, etiquetas=(etiqueta,))


def estado(symbol="LIVEUSDT", ts=1000, *, qv=1_000_000, trades=10_000,
           rango="0.05", momentum="5"):
    return EstadoHistorico(
        symbol=symbol, timestamp_ms=ts, close=Decimal("100"),
        quote_volume_24h=Decimal(str(qv)), trades_24h=int(trades),
        rango_24h=Decimal(str(rango)),
        momentum_cierre_24h_pct=Decimal(str(momentum)))


def train_dos_clusters():
    return [
        obs("P1", 10, qv=1_000_000, trades=10_000, rango=.05, momentum=5.0, retorno=.01),
        obs("P2", 20, qv=1_100_000, trades=11_000, rango=.055, momentum=5.5, retorno=.02),
        obs("P3", 30, qv=900_000, trades=9_000, rango=.045, momentum=4.5, retorno=.03),
        obs("N1", 40, qv=10_000, trades=100, rango=.01, momentum=-5.0, retorno=-.01),
        obs("N2", 50, qv=11_000, trades=110, rango=.012, momentum=-5.5, retorno=-.02),
        obs("N3", 60, qv=9_000, trades=90, rango=.008, momentum=-4.5, retorno=-.03),
    ]


def test_vecinos_cercanos_recuperan_cluster_positivo():
    modelo = ajustar_modelo(train_dos_clusters(), horizonte_horas=4, k=3)
    vecinos = seleccionar_vecinos(modelo, estado(ts=1000))
    assert {v.symbol for v in vecinos} == {"P1", "P2", "P3"}

    e = estimar_edge(modelo, estado(ts=1000))
    assert e.estado == DISPONIBLE
    assert e.n_vecinos == 3
    assert e.retorno_esperado == Decimal("0.02")
    assert e.retorno_p50 == Decimal("0.02")
    assert e.prob_retorno_positivo == Decimal("1")


def test_cluster_negativo_produce_edge_bruto_negativo():
    modelo = ajustar_modelo(train_dos_clusters(), horizonte_horas=4, k=3)
    q = estado(ts=1000, qv=10_000, trades=100, rango="0.01", momentum="-5")
    e = estimar_edge(modelo, q)
    assert e.disponible
    assert e.retorno_esperado == Decimal("-0.02")
    assert e.prob_retorno_positivo == Decimal("0")


def test_no_importa_scanner_ni_lee_atributo_score():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom):
            assert nodo.module != "backend.scanner"
        if isinstance(nodo, ast.Import):
            assert all(alias.name != "backend.scanner" for alias in nodo.names)
        if isinstance(nodo, ast.Attribute):
            assert nodo.attr != "score"


def test_modelo_rechaza_consulta_no_posterior_a_todo_train():
    modelo = ajustar_modelo(train_dos_clusters(), horizonte_horas=4, k=3)
    e = estimar_edge(modelo, estado(ts=60))
    assert e.estado == NO_DISPONIBLE
    assert e.motivo == "consulta_no_posterior_a_train"
    assert e.retorno_esperado is None
    assert seleccionar_vecinos(modelo, estado(ts=59)) == ()


def test_orden_de_train_no_cambia_modelo_ni_resultado():
    datos = train_dos_clusters()
    a = ajustar_modelo(datos, horizonte_horas=4, k=3)
    b = ajustar_modelo(reversed(datos), horizonte_horas=4, k=3)
    qa = estimar_edge(a, estado(ts=1000))
    qb = estimar_edge(b, estado(ts=1000))
    assert a.escalas == b.escalas
    assert qa == qb


def test_soporte_reporta_diversidad_de_symbol_y_timestamp():
    modelo = ajustar_modelo(train_dos_clusters(), horizonte_horas=4, k=3)
    e = estimar_edge(modelo, estado(ts=1000))
    assert e.n_symbols_unicos == 3
    assert e.n_timestamps_unicos == 3
    assert e.distancia_media is not None
    assert e.distancia_max is not None
    assert e.distancia_max >= e.distancia_media >= 0


def test_k_es_explicito_y_train_debe_tener_soporte_suficiente():
    with pytest.raises(ValueError, match="train insuficiente"):
        ajustar_modelo(train_dos_clusters()[:2], horizonte_horas=4, k=3)
    with pytest.raises(ValueError):
        ajustar_modelo(train_dos_clusters(), horizonte_horas=4, k=0)


def test_observaciones_sin_horizonte_solicitado_no_entran_al_train():
    datos = train_dos_clusters()
    datos.append(obs("OTRO", 70, qv=1e6, trades=10000, rango=.05,
                     momentum=5, retorno=.99, h=8))
    modelo = ajustar_modelo(datos, horizonte_horas=4, k=3)
    assert len(modelo.muestras) == 6
    assert modelo.max_timestamp_train == 60


def test_todas_features_constantes_no_fabrican_distancia():
    datos = [
        obs(f"X{i}", i, qv=1000, trades=100, rango=.02, momentum=1,
            retorno=.01) for i in range(1, 6)
    ]
    with pytest.raises(ValueError, match="constantes"):
        ajustar_modelo(datos, horizonte_horas=4, k=3)


def test_feature_actual_invalida_da_no_disponible_no_cero():
    modelo = ajustar_modelo(train_dos_clusters(), horizonte_horas=4, k=3)
    q = estado(ts=1000, qv=-1)
    e = estimar_edge(modelo, q)
    assert e.estado == NO_DISPONIBLE
    assert e.retorno_esperado is None
    assert "negativas" in e.motivo


def test_desempate_de_distancia_es_estable_por_timestamp_y_symbol():
    # Activa escalas con extremos; A/B quedan simetricos alrededor de la consulta.
    datos = [
        obs("A", 10, qv=100, trades=100, rango=.02, momentum=-1, retorno=.01),
        obs("B", 10, qv=100, trades=100, rango=.02, momentum=1, retorno=.02),
        obs("C", 20, qv=10, trades=10, rango=.01, momentum=-10, retorno=-.1),
        obs("D", 30, qv=1000, trades=1000, rango=.10, momentum=10, retorno=.1),
    ]
    modelo = ajustar_modelo(datos, horizonte_horas=4, k=2)
    q = estado(ts=1000, qv=100, trades=100, rango=.02, momentum=0)
    vecinos = seleccionar_vecinos(modelo, q)
    assert [v.symbol for v in vecinos] == ["A", "B"]


@pytest.mark.parametrize("h,k", [(0, 3), (4.5, 3), (4, 0), (4, True)])
def test_hiperparametros_invalidos_fallan_cerrado(h, k):
    with pytest.raises(ValueError):
        ajustar_modelo(train_dos_clusters(), horizonte_horas=h, k=k)


def test_modulo_no_importa_cost_model_scanner_llm_ml_red_ni_bd():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    texto = ast.dump(arbol)
    for prohibido in (
        "costes", "openai", "sklearn", "numpy", "pandas",
        "requests", "sqlalchemy", "binance", "MotorRiesgo", "SessionLocal",
    ):
        assert prohibido not in texto
