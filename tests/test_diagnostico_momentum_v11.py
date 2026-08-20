"""Tests del diagnóstico semanal BOT 2.0-04B-v11."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.economia.diagnostico_momentum_v11 import diagnosticar_momentum_v11
from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.momentum_semanal_v11 import EstadoMomentumV11, ObservacionMomentumV11
from backend.economia.protocolo_edge_v11 import (
    CLASE_PROMETEDORA,
    CLASE_SIN_SENAL,
    DESARROLLO_2026_ABIERTO_V11,
    FACTORES_V11,
    HORIZONTE_HORAS_V11,
    TEST_MAY_JUL_ABIERTO_V11,
)


def _ts_cierre_domingo(lunes: datetime) -> int:
    return int(lunes.timestamp() * 1000) - 1


def _obs(ts: int, asset_idx: int, retorno_bps: int, *, senal: Decimal) -> ObservacionMomentumV11:
    estado = EstadoMomentumV11(
        symbol=f"A{asset_idx:02d}USDT",
        timestamp_ms=ts,
        close=Decimal("100"),
        mom1=senal,
        mom2=Decimal("0"),
        mom3=Decimal("0"),
        rmom1=Decimal("0"),
        rmom2=Decimal("0"),
        rmom3=Decimal("0"),
    )
    etiqueta = EtiquetaHorizonte(
        horizonte_horas=HORIZONTE_HORAS_V11,
        retorno_cierre=Decimal(retorno_bps) / Decimal("10000"),
        mfe=max(Decimal("0"), Decimal(retorno_bps) / Decimal("10000")),
        mae=min(Decimal("0"), Decimal(retorno_bps) / Decimal("10000")),
    )
    return ObservacionMomentumV11(estado=estado, etiquetas=(etiqueta,))


def dataset(n_semanas=50):
    inicio = datetime(2025, 1, 6, tzinfo=timezone.utc)  # lunes 00 UTC
    salida = []
    for semana in range(n_semanas):
        ts = _ts_cierre_domingo(inicio + timedelta(days=7 * semana))
        for i in range(20):
            retorno_bps = -50 + i * 15
            salida.append(_obs(ts, i, retorno_bps, senal=Decimal(i)))
    return tuple(salida)


def test_locks_2026_permanecen_cerrados():
    assert DESARROLLO_2026_ABIERTO_V11 is False
    assert TEST_MAY_JUL_ABIERTO_V11 is False


def test_solo_factor_con_senal_real_pasa():
    d = diagnosticar_momentum_v11(dataset())
    assert d.n_timestamps == 50
    assert d.factores_prometedores == ("mom1",)
    por_factor = {r.factor: r for r in d.resultados}
    assert por_factor["mom1"].apto is True
    assert por_factor["mom1"].spread_alto_menos_bajo_medio_bps > 25
    assert por_factor["mom1"].retorno_top1_neto_medio_bps > 0
    assert por_factor["mom1"].fraccion_top1_neto_positivo == Decimal("1")
    for factor in FACTORES_V11[1:]:
        assert por_factor[factor].apto is False


def test_factor_plano_no_inventa_ic_ni_spread():
    d = diagnosticar_momentum_v11(dataset())
    r = next(x for x in d.resultados if x.factor == "mom2")
    assert r.ic_spearman_medio is None
    assert r.spread_alto_menos_bajo_medio_bps is None
    assert "SPREAD_MEDIO_INSUFICIENTE" in r.motivos_rechazo


def test_menos_de_45_semanas_no_promueve_aunque_retorno_sea_bueno():
    d = diagnosticar_momentum_v11(dataset(44))
    r = next(x for x in d.resultados if x.factor == "mom1")
    assert r.apto is False
    assert "TOP1_SENALES_INSUFICIENTES" in r.motivos_rechazo


def test_ignora_observaciones_2026():
    base = list(dataset())
    ts_2026 = _ts_cierre_domingo(datetime(2026, 1, 5, tzinfo=timezone.utc))
    for i in range(20):
        base.append(_obs(ts_2026, i, 5000, senal=Decimal(i)))
    d = diagnosticar_momentum_v11(tuple(base))
    assert d.n_timestamps == 50


def test_clasificaciones_son_explicitas():
    d = diagnosticar_momentum_v11(dataset())
    clases = {c.factor: c.clase for c in d.clasificaciones}
    assert clases["mom1"] == CLASE_PROMETEDORA
    assert all(clases[f] == CLASE_SIN_SENAL for f in FACTORES_V11[1:])
