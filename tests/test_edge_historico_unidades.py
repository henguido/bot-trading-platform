"""Compatibilidad temporal REST(ms) / Binance Vision(us)."""
from backend.economia.edge_historico import vela_desde_kline


def fila(t0, t1):
    return [t0, "100", "110", "90", "105", "10", t1, "1000", 50]


def test_kline_milisegundos_se_conserva():
    v = vela_desde_kline(fila(1735689600000, 1735703999999))
    assert v.open_time_ms == 1735689600000
    assert v.close_time_ms == 1735703999999


def test_kline_microsegundos_vision_se_normaliza_a_ms():
    v = vela_desde_kline(fila(1735689600000000, 1735703999999999))
    assert v.open_time_ms == 1735689600000
    assert v.close_time_ms == 1735703999999


def test_ms_y_us_producen_misma_vela_temporal():
    ms = vela_desde_kline(fila(1735689600000, 1735703999999))
    us = vela_desde_kline(fila(1735689600000000, 1735703999999999))
    assert (ms.open_time_ms, ms.close_time_ms) == (us.open_time_ms, us.close_time_ms)


def test_unidad_mayor_no_declarada_falla_cerrado():
    import pytest
    with pytest.raises(ValueError, match="unidad no soportada"):
        vela_desde_kline(fila(1735689600000000000, 1735703999999999999))
