from decimal import Decimal

from backend.economia.edge_historico import EtiquetaHorizonte
from backend.economia.edge_selector_v8 import EstadoSelectorV8, ObservacionSelectorV8
from backend.economia.selector_probabilistico_v8 import ajustar_selector_v8, estimar_selector_v8


def _estado(symbol: str, ts: int, *, rank=Decimal("0.5")):
    return EstadoSelectorV8(
        symbol=symbol,
        timestamp_ms=ts,
        close=Decimal("100"),
        rank_retorno_4h=rank,
        rank_retorno_24h=rank,
        rank_sorpresa_volumen_4h=rank,
        mediana_retorno_24h_mercado=Decimal("0.001"),
        dispersion_iqr_retorno_24h_mercado=Decimal("0.02"),
    )


def _train(retornos_bps):
    salida = []
    for i, bps in enumerate(retornos_bps):
        symbol = f"S{i % 3}USDT"
        ts = 1_000_000 + (i // 3) * 86_400_000
        salida.append(ObservacionSelectorV8(
            estado=_estado(symbol, ts),
            etiquetas=(EtiquetaHorizonte(
                horizonte_horas=24,
                retorno_cierre=Decimal(str(bps)) / Decimal("10000"),
                mfe=Decimal("0.01"),
                mae=Decimal("-0.01"),
            ),),
        ))
    return tuple(salida)


def _modelo(retornos_bps):
    return ajustar_selector_v8(
        _train(retornos_bps),
        rank_bins=3,
        regimen_bins=3,
        dispersion_bins=3,
        min_muestras=60,
        max_radio=0,
    )


def test_celda_con_60pct_y_media_40bps_es_candidata():
    # 36x +100 y 24x -50 => media +40 bps, P(>25)=0.60.
    modelo = _modelo([100] * 36 + [-50] * 24)
    consulta = _estado("BTCUSDT", modelo.max_timestamp_train + 86_400_000)
    r = estimar_selector_v8(modelo, consulta)
    assert r.disponible
    assert r.n_muestras == 60
    assert r.retorno_bruto_esperado_bps == Decimal("40")
    assert r.prob_superar_hurdle == Decimal("0.6")
    assert r.candidata


def test_break_even_exacto_y_probabilidad_50pct_no_es_candidato():
    # 30x +100 y 30x -50 => media +25 bps, P(>25)=0.50.
    modelo = _modelo([100] * 30 + [-50] * 30)
    consulta = _estado("BTCUSDT", modelo.max_timestamp_train + 86_400_000)
    r = estimar_selector_v8(modelo, consulta)
    assert r.disponible
    assert r.retorno_bruto_esperado_bps == Decimal("25")
    assert r.prob_superar_hurdle == Decimal("0.5")
    assert not r.candidata


def test_consulta_no_posterior_al_train_falla_cerrado():
    modelo = _modelo([100] * 36 + [-50] * 24)
    consulta = _estado("BTCUSDT", modelo.max_timestamp_train)
    r = estimar_selector_v8(modelo, consulta)
    assert not r.disponible
    assert not r.candidata
    assert r.motivo == "consulta_no_posterior_a_train"


def test_probabilidad_usa_estrictamente_retorno_mayor_que_hurdle():
    # 33 retornos exactamente 25 no cuentan como superar hurdle.
    modelo = _modelo([25] * 33 + [100] * 27)
    consulta = _estado("BTCUSDT", modelo.max_timestamp_train + 86_400_000)
    r = estimar_selector_v8(modelo, consulta)
    assert r.prob_superar_hurdle == Decimal("0.45")
    assert not r.candidata
