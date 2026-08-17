"""BOT 2.0-04B-1 · validacion walk-forward cronologica."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from backend.economia.edge_historico import (
    EstadoHistorico, EtiquetaHorizonte, ObservacionEdge,
)
from backend.economia.validacion_edge import HORA_MS
from backend.economia.walk_forward_edge import (
    DISPONIBLE,
    FoldTemporal,
    comparar_configuraciones,
    evaluar_walk_forward,
)

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "walk_forward_edge.py"


def obs(symbol, hora, *, cluster="P", retorno=None, h=4):
    positivo = cluster == "P"
    qv = 1_000_000 if positivo else 10_000
    trades = 10_000 if positivo else 100
    rango = Decimal("0.05") if positivo else Decimal("0.01")
    momentum = Decimal("5") if positivo else Decimal("-5")
    r = Decimal(str(retorno if retorno is not None else (.02 if positivo else -.02)))
    return ObservacionEdge(
        estado=EstadoHistorico(
            symbol=symbol, timestamp_ms=hora * HORA_MS, close=Decimal("100"),
            quote_volume_24h=Decimal(qv), trades_24h=trades,
            rango_24h=rango, momentum_cierre_24h_pct=momentum),
        etiquetas=(EtiquetaHorizonte(
            h, r, max(Decimal("0"), r), min(Decimal("0"), r)),),
    )


def dataset():
    datos = []
    # Train inicial: suficientes ejemplos de ambos estados antes de 100h.
    for i, hora in enumerate((10, 20, 30, 40, 50, 60)):
        cluster = "P" if i < 3 else "N"
        datos.append(obs(f"T{i}", hora, cluster=cluster))
    # Fold 1 [100,140): realizaciones más fuertes con mismo patrón.
    datos += [obs("V1P", 110, cluster="P", retorno=.04),
              obs("V1N", 120, cluster="N", retorno=-.04)]
    # Entre folds: pasan a formar parte del train expansivo del fold 2.
    datos += [obs("M1P", 150, cluster="P", retorno=.03),
              obs("M1N", 160, cluster="N", retorno=-.03)]
    # Fold 2 [200,240).
    datos += [obs("V2P", 210, cluster="P", retorno=.05),
              obs("V2N", 220, cluster="N", retorno=-.05)]
    return datos


def folds():
    return (FoldTemporal(100 * HORA_MS, 140 * HORA_MS),
            FoldTemporal(200 * HORA_MS, 240 * HORA_MS))


def test_walk_forward_reajusta_train_en_cada_fold():
    r = evaluar_walk_forward(dataset(), horizonte_horas=4, k=3, folds=folds())
    assert r.n_folds_disponibles == 2
    assert [f.n_train for f in r.folds] == [6, 10]
    assert [f.n_validacion for f in r.folds] == [2, 2]
    assert r.n_estimadas == 4
    assert r.cobertura == Decimal("1")


def test_embargo_excluye_muestras_demasiado_cercanas_al_fold():
    datos = dataset() + [obs("BORDE", 98, cluster="P")]
    r = evaluar_walk_forward(datos, horizonte_horas=4, k=3, folds=folds())
    assert r.folds[0].n_descartadas_embargo >= 1
    assert all(p.symbol != "BORDE" for p in r.folds[0].predicciones)


def test_resultado_oos_recupera_relacion_sintetica():
    r = evaluar_walk_forward(dataset(), horizonte_horas=4, k=3, folds=folds())
    assert r.exactitud_direccional == Decimal("1")
    assert r.retorno_real_medio == Decimal("0.00")
    assert r.uplift_top25_vs_baseline > 0
    assert r.mae_prediccion is not None


def test_fold_sin_train_suficiente_queda_no_disponible_sin_fabricar_edge():
    r = evaluar_walk_forward(
        [obs("X", 10, cluster="P")], horizonte_horas=4, k=3,
        folds=(FoldTemporal(100 * HORA_MS, 140 * HORA_MS),))
    assert r.n_folds_disponibles == 0
    assert r.n_estimadas == 0
    assert r.cobertura == Decimal("0")
    assert r.mae_prediccion is None
    assert "train insuficiente" in r.folds[0].motivo


def test_folds_solapados_o_desordenados_se_rechazan():
    datos = dataset()
    with pytest.raises(ValueError, match="orden cronologico"):
        evaluar_walk_forward(
            datos, horizonte_horas=4, k=3,
            folds=(FoldTemporal(200 * HORA_MS, 240 * HORA_MS),
                   FoldTemporal(100 * HORA_MS, 140 * HORA_MS)))
    with pytest.raises(ValueError, match="solaparse"):
        evaluar_walk_forward(
            datos, horizonte_horas=4, k=3,
            folds=(FoldTemporal(100 * HORA_MS, 150 * HORA_MS),
                   FoldTemporal(140 * HORA_MS, 180 * HORA_MS)))


def test_embargo_nunca_puede_ser_menor_que_horizonte():
    with pytest.raises(ValueError):
        evaluar_walk_forward(dataset(), horizonte_horas=8, k=3,
                             folds=folds(), embargo_horas=4)


def test_comparar_configuraciones_no_escoge_ganador():
    resultados = comparar_configuraciones(
        dataset(), horizontes_horas=(4,), valores_k=(2, 3), folds=folds())
    assert [(r.horizonte_horas, r.k) for r in resultados] == [(4, 2), (4, 3)]
    assert not hasattr(resultados, "ganador")
    fuente = MODULO.read_text(encoding="utf-8").lower()
    assert "best_model" not in fuente
    assert "ganador =" not in fuente


def test_orden_de_dataset_no_cambia_resultado():
    a = evaluar_walk_forward(dataset(), horizonte_horas=4, k=3, folds=folds())
    b = evaluar_walk_forward(reversed(dataset()), horizonte_horas=4, k=3, folds=folds())
    assert a == b


def test_modulo_no_importa_ml_llm_trading_red_ni_bd():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    importados = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            importados.append(nodo.module or "")
            importados.extend(alias.name for alias in nodo.names)
    texto = " ".join(importados).lower()
    for prohibido in (
        "random", "sklearn", "numpy", "pandas", "openai", "costes",
        "motorriesgo", "scanner", "backend.main", "sessionlocal", "requests",
    ):
        assert prohibido not in texto
