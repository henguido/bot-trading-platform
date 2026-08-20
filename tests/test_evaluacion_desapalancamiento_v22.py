from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.economia.edge_historico import Vela
from backend.economia.evaluacion_desapalancamiento_v22 import (
    RetornoSpotV22,
    evaluar_desapalancamiento_v22,
    retornos_spot_previos_y_futuros_v22,
)
from backend.economia.posicionamiento_v21 import FeaturePosicionamientoV21

SYMS = tuple(f"S{i:02d}" for i in range(15))


def _ts(year, month, day=5, hour=8):
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp() * 1000)


def _features(ts):
    out = []
    for i, s in enumerate(SYMS):
        # Solo S00/S01 confirman desapalancamiento.
        oi = Decimal("-0.02") if i < 2 else Decimal("0.01")
        taker = Decimal("0.8") if i < 2 else Decimal("1.2")
        out.append(FeaturePosicionamientoV21(s, ts, taker, oi, 96, 96))
    return out


def _retornos_timestamp(ts, *, signal_future=Decimal("0.01"), bottom_other_future=Decimal("0")):
    out = {}
    for i, s in enumerate(SYMS):
        # S00..S03 forman bottom quartile por retorno previo.
        previo = Decimal("-0.08") + Decimal(i) / Decimal("100")
        if i < 2:
            futuro = signal_future
        elif i < 4:
            futuro = bottom_other_future
        else:
            futuro = Decimal("0")
        out[(s, ts)] = RetornoSpotV22(previo=previo, futuro=futuro)
    return out


def _dataset_estable(*, bottom_other_future=Decimal("0")):
    features = []
    retornos = {}
    for year in (2022, 2023, 2024, 2025):
        for month in range(1, 13):
            for day in (3, 8, 13, 18, 23):
                ts = _ts(year, month, day)
                features.extend(_features(ts))
                retornos.update(_retornos_timestamp(ts, bottom_other_future=bottom_other_future))
    return features, retornos


def test_bottom_quartile_filtra_por_oi_y_taker_sin_reemplazo():
    ts = _ts(2025, 1)
    r = evaluar_desapalancamiento_v22(_features(ts), _retornos_timestamp(ts))
    assert len(r.timestamps) == 1
    t = r.timestamps[0]
    assert t.n_elegibles == 15
    assert t.n_bottom_precio == 4
    assert t.n_senales == 2
    assert t.symbols == ("S00", "S01")
    assert "S04" not in t.symbols


def test_dataset_estable_pasa_si_derivados_mejoran_precio_only_y_universo():
    features, retornos = _dataset_estable(bottom_other_future=Decimal("0"))
    r = evaluar_desapalancamiento_v22(features, retornos)
    assert r.apta is True
    assert r.motivos_rechazo == ()
    assert r.n_timestamps_con_senal == 240
    assert r.n_meses_con_senal == 48
    assert r.n_anios_con_senal == 4
    assert r.media_neta_bps == Decimal("75")
    assert r.media_uplift_universo_bps > 0
    assert r.media_uplift_precio_only_bps > 0
    assert r.n_anios_uplift_precio_only_positivo == 4


def test_rebote_rentable_no_pasa_si_derivados_no_agregan_sobre_precio_only():
    features, retornos = _dataset_estable(bottom_other_future=Decimal("0.01"))
    r = evaluar_desapalancamiento_v22(features, retornos)
    assert r.media_neta_bps == Decimal("75")
    assert r.media_uplift_precio_only_bps == 0
    assert r.apta is False
    assert "UPLIFT_VS_PRECIO_ONLY_NO_POSITIVO" in r.motivos_rechazo


def test_rebote_bruto_menor_al_hurdle_falla_aunque_haya_uplift():
    features, retornos = _dataset_estable(bottom_other_future=Decimal("0"))
    retornos = {
        k: RetornoSpotV22(v.previo, Decimal("0.001") if k[0] in ("S00", "S01") else Decimal("0"))
        for k, v in retornos.items()
    }
    r = evaluar_desapalancamiento_v22(features, retornos)
    assert r.media_bruta_bps == Decimal("10")
    assert r.media_neta_bps == Decimal("-15")
    assert r.media_uplift_precio_only_bps > 0
    assert r.apta is False
    assert "MEDIA_NETA_NO_POSITIVA" in r.motivos_rechazo


def _vela(ts, open_):
    p = Decimal(str(open_))
    return Vela(ts, p, p, p, p, Decimal("1"), ts + 1, Decimal("1"), 1)


def test_retorno_previo_y_futuro_separan_informacion_en_t():
    t = _ts(2025, 2, hour=8)
    h4 = 4 * 60 * 60 * 1000
    velas = {
        "BTCUSDT": (
            _vela(t - 2 * h4, "120"),
            _vela(t - h4, "110"),
            _vela(t, "100"),
            _vela(t + h4, "105"),
            _vela(t + 2 * h4, "110"),
        )
    }
    r = retornos_spot_previos_y_futuros_v22(velas)[("BTCUSDT", t)]
    assert r.previo == Decimal("100") / Decimal("120") - 1
    assert r.futuro == Decimal("0.10")
