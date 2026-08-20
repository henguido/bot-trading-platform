from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.economia.edge_historico import Vela
from backend.economia.evaluacion_posicionamiento_v21 import (
    evaluar_posicionamiento_v21,
    retornos_spot_open_a_open_v21,
)
from backend.economia.posicionamiento_v21 import FeaturePosicionamientoV21


SYMS = tuple(f"S{i:02d}" for i in range(15))


def _ts(year, month, day=5, hour=8):
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp() * 1000)


def _features_timestamp(ts, *, oi_top_negativo=False):
    out = []
    for i, s in enumerate(SYMS):
        # S00..S03 son el top-25% por presión taker.
        presion = Decimal("2") - Decimal(i) / Decimal("100")
        cambio = Decimal("0.01")
        if oi_top_negativo and i == 0:
            cambio = Decimal("-0.01")
        out.append(FeaturePosicionamientoV21(s, ts, presion, cambio, 96, 96))
    return out


def _dataset_estable(retorno_signal=Decimal("0.01")):
    features = []
    retornos = {}
    for year in (2022, 2023, 2024, 2025):
        for month in range(1, 13):
            for day in (3, 8, 13, 18, 23):
                ts = _ts(year, month, day)
                features.extend(_features_timestamp(ts))
                for i, s in enumerate(SYMS):
                    retornos[(s, ts)] = retorno_signal if i < 4 else Decimal("0")
    return features, retornos


def test_regla_toma_top_quartile_y_no_reemplaza_oi_negativo_con_quinto():
    ts = _ts(2025, 1)
    fs = _features_timestamp(ts, oi_top_negativo=True)
    retornos = {(s, ts): Decimal("0.01") for s in SYMS}
    r = evaluar_posicionamiento_v21(fs, retornos)
    assert len(r.timestamps) == 1
    t = r.timestamps[0]
    assert t.n_elegibles == 15
    assert t.n_top_taker == 4
    assert t.n_senales == 3
    assert "S00" not in t.symbols
    assert "S04" not in t.symbols


def test_dataset_estable_y_neto_superior_a_hurdle_pasa_gate():
    features, retornos = _dataset_estable(Decimal("0.01"))
    r = evaluar_posicionamiento_v21(features, retornos)
    assert r.apta is True
    assert r.motivos_rechazo == ()
    assert r.n_timestamps_con_senal == 240
    assert r.n_meses_con_senal == 48
    assert r.n_anios_con_senal == 4
    assert r.n_meses_neto_positivo == 48
    assert r.n_anios_neto_positivo == 4
    assert r.media_neta_bps == Decimal("75")
    assert r.media_uplift_bps > 0


def test_edge_bruto_positivo_pero_menor_a_25bps_falla_economicamente():
    features, retornos = _dataset_estable(Decimal("0.001"))
    r = evaluar_posicionamiento_v21(features, retornos)
    assert r.apta is False
    assert r.media_bruta_bps == Decimal("10")
    assert r.media_neta_bps == Decimal("-15")
    assert "MEDIA_NETA_NO_POSITIVA" in r.motivos_rechazo


def _vela(ts, open_):
    p = Decimal(str(open_))
    return Vela(ts, p, p, p, p, Decimal("1"), ts + 1, Decimal("1"), 1)


def test_retorno_spot_usa_open_t_a_open_t_mas_8h():
    t0 = _ts(2025, 2, hour=8)
    h4 = 4 * 60 * 60 * 1000
    velas = {
        "BTCUSDT": (
            _vela(t0, "100"),
            _vela(t0 + h4, "150"),
            _vela(t0 + 2 * h4, "110"),
        )
    }
    r = retornos_spot_open_a_open_v21(velas)
    assert r[("BTCUSDT", t0)] == Decimal("0.10")
