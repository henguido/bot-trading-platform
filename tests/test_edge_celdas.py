"""Pruebas del estimador escalable por celdas cuantiles."""
from decimal import Decimal

import pytest

from backend.economia.edge_celdas import (
    DISPONIBLE,
    NO_DISPONIBLE,
    ajustar_modelo_celdas,
    estimar_edge_celdas,
)
from backend.economia.edge_historico import (
    EstadoHistorico, EtiquetaHorizonte, ObservacionEdge,
)


def obs(symbol, ts, *, qv, trades, rango, momentum, retorno, h=4):
    estado = EstadoHistorico(
        symbol=symbol, timestamp_ms=ts, close=Decimal("100"),
        quote_volume_24h=Decimal(str(qv)), trades_24h=int(trades),
        rango_24h=Decimal(str(rango)),
        momentum_cierre_24h_pct=Decimal(str(momentum)),
    )
    r = Decimal(str(retorno))
    return ObservacionEdge(
        estado=estado,
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=h,
            retorno_cierre=r,
            mfe=max(Decimal("0"), r),
            mae=min(Decimal("0"), r),
        ),),
    )


def estado(ts=10_000, *, qv=1000, trades=100, rango=.03, momentum=1):
    return EstadoHistorico(
        symbol="LIVEUSDT", timestamp_ms=ts, close=Decimal("100"),
        quote_volume_24h=Decimal(str(qv)), trades_24h=int(trades),
        rango_24h=Decimal(str(rango)),
        momentum_cierre_24h_pct=Decimal(str(momentum)),
    )


def train_base():
    salida = []
    for i in range(1, 41):
        salida.append(obs(
            f"S{i % 8}", i,
            qv=500 + i * 25,
            trades=50 + i * 3,
            rango=.01 + (i % 10) * .005,
            momentum=-4 + (i % 9),
            retorno=(-.02 + (i % 7) * .01),
        ))
    return salida


def modelo(**cambios):
    p = dict(
        horizonte_horas=4,
        n_bins=4,
        min_muestras=3,
        min_symbols=2,
        min_timestamps=3,
        max_radio=2,
    )
    p.update(cambios)
    return ajustar_modelo_celdas(train_base(), **p)


def test_modelo_agrupa_train_sin_perder_muestras():
    m = modelo()
    assert m.n_muestras_train == 40
    assert sum(len(v) for v in m.celdas.values()) == 40
    assert m.max_timestamp_train == 40


def test_consulta_fuera_de_rango_train_falla_cerrado():
    m = modelo()
    e = estimar_edge_celdas(m, estado(qv=10_000_000))
    assert e.estado == NO_DISPONIBLE
    assert e.motivo == "fuera_rango_train:log_quote_volume_24h"
    assert e.retorno_esperado is None


def test_consulta_no_posterior_a_train_no_se_evalua():
    m = modelo()
    e = estimar_edge_celdas(m, estado(ts=40))
    assert e.estado == NO_DISPONIBLE
    assert e.motivo == "consulta_no_posterior_a_train"


def test_celda_exacta_se_prefiere_si_tiene_soporte():
    datos = [
        obs("A", 1, qv=100, trades=10, rango=.01, momentum=-2, retorno=.01),
        obs("B", 2, qv=110, trades=11, rango=.011, momentum=-1.8, retorno=.02),
        obs("C", 3, qv=120, trades=12, rango=.012, momentum=-1.6, retorno=.03),
        obs("D", 4, qv=10_000, trades=1000, rango=.10, momentum=8, retorno=-.5),
    ]
    m = ajustar_modelo_celdas(
        datos, horizonte_horas=4, n_bins=2, min_muestras=2,
        min_symbols=2, min_timestamps=2, max_radio=1)
    # Esta consulta cae deliberadamente en la misma celda cuantílica de A/B.
    q = estado(qv=105, trades=10, rango=.0105, momentum=-1.9)
    e = estimar_edge_celdas(m, q)
    assert e.estado == DISPONIBLE
    assert e.radio_usado == 0
    assert e.retorno_esperado > 0


def test_expande_radio_solo_hasta_conseguir_soporte():
    m = modelo(min_muestras=8, min_symbols=3, min_timestamps=8, max_radio=4)
    e = estimar_edge_celdas(m, estado(qv=1000, trades=100, rango=.03, momentum=1))
    assert e.estado == DISPONIBLE
    assert e.radio_usado is not None
    assert e.radio_usado > 0
    assert e.n_muestras >= 8
    assert e.n_symbols_unicos >= 3
    assert e.n_timestamps_unicos >= 8


def test_sin_soporte_no_fabrica_edge():
    m = modelo(min_muestras=39, min_symbols=8, min_timestamps=39, max_radio=0)
    e = estimar_edge_celdas(m, estado(qv=1000, trades=100, rango=.03, momentum=1))
    assert e.estado == NO_DISPONIBLE
    assert e.motivo == "soporte_insuficiente"
    assert e.retorno_esperado is None


def test_soporte_exige_diversidad_no_solo_muchas_filas():
    datos = [
        obs("SOLO", i, qv=1000 + i, trades=100 + i,
            rango=.03, momentum=1, retorno=.01) for i in range(1, 31)
    ]
    m = ajustar_modelo_celdas(
        datos, horizonte_horas=4, n_bins=3, min_muestras=5,
        min_symbols=2, min_timestamps=5, max_radio=3)
    e = estimar_edge_celdas(m, estado(qv=1015, trades=115, rango=.03, momentum=1))
    assert e.estado == NO_DISPONIBLE
    assert e.n_symbols_unicos == 1


def test_orden_train_no_cambia_celdas_ni_estimacion():
    datos = train_base()
    kwargs = dict(
        horizonte_horas=4, n_bins=4, min_muestras=3,
        min_symbols=2, min_timestamps=3, max_radio=2)
    a = ajustar_modelo_celdas(datos, **kwargs)
    b = ajustar_modelo_celdas(reversed(datos), **kwargs)
    assert a.discretizaciones == b.discretizaciones
    assert tuple(a.celdas) == tuple(b.celdas)
    q = estado(qv=1000, trades=100, rango=.03, momentum=1)
    assert estimar_edge_celdas(a, q) == estimar_edge_celdas(b, q)


@pytest.mark.parametrize("campo,valor", [
    ("horizonte_horas", 0), ("horizonte_horas", 4.5),
    ("n_bins", 1), ("n_bins", True),
    ("min_muestras", 0), ("min_symbols", 0),
    ("min_timestamps", 0), ("max_radio", -1),
])
def test_hiperparametros_invalidos_fallan_cerrado(campo, valor):
    kwargs = dict(
        horizonte_horas=4, n_bins=4, min_muestras=3,
        min_symbols=2, min_timestamps=3, max_radio=2)
    kwargs[campo] = valor
    with pytest.raises(ValueError):
        ajustar_modelo_celdas(train_base(), **kwargs)


def test_feature_invalida_no_se_convierte_en_cero():
    m = modelo()
    e = estimar_edge_celdas(m, estado(qv=-1))
    assert e.estado == NO_DISPONIBLE
    assert "negativas" in e.motivo


def test_modelo_no_importa_trading_llm_red_ni_bd():
    import ast
    from pathlib import Path
    modulo = Path(__file__).resolve().parents[1] / "backend" / "economia" / "edge_celdas.py"
    arbol = ast.parse(modulo.read_text(encoding="utf-8"))
    importados = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            importados.append(nodo.module or "")
            importados.extend(alias.name for alias in nodo.names)
    texto = " ".join(importados).lower()
    for prohibido in ("openai", "motorriesgo", "scanner", "requests", "sqlalchemy"):
        assert prohibido not in texto
