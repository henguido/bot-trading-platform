"""La optimizacion por cache no puede cambiar la semantica del holdout."""
from decimal import Decimal

import backend.economia.evaluacion_celdas as ev
from backend.economia.edge_celdas import ajustar_modelo_celdas
from backend.economia.edge_historico import EstadoHistorico, EtiquetaHorizonte, ObservacionEdge


def obs(symbol, ts, qv, retorno):
    r = Decimal(str(retorno))
    return ObservacionEdge(
        estado=EstadoHistorico(
            symbol=symbol, timestamp_ms=ts, close=Decimal("100"),
            quote_volume_24h=Decimal(str(qv)), trades_24h=100,
            rango_24h=Decimal("0.03"), momentum_cierre_24h_pct=Decimal("1")),
        etiquetas=(EtiquetaHorizonte(
            horizonte_horas=4, retorno_cierre=r,
            mfe=max(Decimal("0"), r), mae=min(Decimal("0"), r)),),)


def test_dos_observaciones_misma_celda_calculan_edge_una_sola_vez(monkeypatch):
    train = [
        obs(f"T{i % 4}", i, 1000 + i * 10, (-2 + i % 5) / 100)
        for i in range(1, 31)
    ]
    modelo = ajustar_modelo_celdas(
        train, horizonte_horas=4, n_bins=2, min_muestras=3,
        min_symbols=2, min_timestamps=3, max_radio=2)

    original = ev.estimar_edge_celdas
    llamadas = []

    def contado(modelo_, estado_):
        llamadas.append(estado_.symbol)
        return original(modelo_, estado_)

    monkeypatch.setattr(ev, "estimar_edge_celdas", contado)

    # Misma combinación de bins: solo cambia symbol/timestamp/retorno real.
    valid = [
        obs("V1", 100, 1100, .01),
        obs("V2", 101, 1100, -.01),
    ]
    r = ev.evaluar_holdout_celdas(modelo, valid)
    assert r.n_objetivo == 2
    assert len(llamadas) == 1
    if r.n_estimadas == 2:
        assert r.predicciones[0].predicho == r.predicciones[1].predicho
