from __future__ import annotations

from decimal import Decimal

from backend.economia.funding_spot_v19 import (
    agregar_funding_diario_v19,
    construir_observaciones_funding_v19,
)
from backend.economia.historico_funding_v18 import EventoFundingV18
from backend.economia.historico_spot_diario_v15 import DIA_MS, SpotDiarioV15

BASE = 1640995200000  # 2022-01-01 UTC


def _f(symbol, horas, rate, intervalo=8):
    return EventoFundingV18(symbol, BASE + horas * 3_600_000, intervalo, Decimal(rate))


def test_suma_todos_los_settlements_del_dia_sin_promediar():
    diarios = agregar_funding_diario_v19({
        "BTCUSDT": (
            _f("BTCUSDT", 0, "-0.0001"),
            _f("BTCUSDT", 8, "-0.0002"),
            _f("BTCUSDT", 16, "0.00005"),
        )
    })
    assert len(diarios) == 1
    assert diarios[0].funding_suma == Decimal("-0.00025")
    assert diarios[0].n_settlements == 3


def test_cambio_de_intervalo_no_inventa_settlements():
    diarios = agregar_funding_diario_v19({
        "BTCUSDT": (
            _f("BTCUSDT", 0, "-0.0001", 8),
            _f("BTCUSDT", 4, "-0.0001", 4),
            _f("BTCUSDT", 8, "-0.0001", 4),
            _f("BTCUSDT", 12, "-0.0001", 4),
            _f("BTCUSDT", 16, "-0.0001", 4),
            _f("BTCUSDT", 20, "-0.0001", 4),
        )
    })
    assert diarios[0].n_settlements == 6
    assert diarios[0].funding_suma == Decimal("-0.0006")


def test_funding_t_usa_spot_open_close_t_mas_1():
    eventos = {"BTCUSDT": (_f("BTCUSDT", 0, "-0.0003"), _f("BTCUSDT", 8, "-0.0002"))}
    spot = {
        "BTCUSDT": (
            SpotDiarioV15(BASE + DIA_MS, Decimal("100"), Decimal("110")),
            SpotDiarioV15(BASE + 2 * DIA_MS, Decimal("200"), Decimal("50")),
        )
    }
    obs = construir_observaciones_funding_v19(eventos, spot)
    assert len(obs) == 1
    assert obs[0].timestamp_signal_ms == BASE
    assert obs[0].timestamp_entrada_ms == BASE + DIA_MS
    assert obs[0].retorno_spot_siguiente == Decimal("0.1")


def test_modificar_t_mas_2_no_cambia_etiqueta_t():
    eventos = {"BTCUSDT": (_f("BTCUSDT", 8, "-0.0003"),)}
    a = {"BTCUSDT": (
        SpotDiarioV15(BASE + DIA_MS, Decimal("100"), Decimal("101")),
        SpotDiarioV15(BASE + 2 * DIA_MS, Decimal("100"), Decimal("100")),
    )}
    b = {"BTCUSDT": (
        SpotDiarioV15(BASE + DIA_MS, Decimal("100"), Decimal("101")),
        SpotDiarioV15(BASE + 2 * DIA_MS, Decimal("1"), Decimal("1000")),
    )}
    assert construir_observaciones_funding_v19(eventos, a)[0].retorno_spot_siguiente == construir_observaciones_funding_v19(eventos, b)[0].retorno_spot_siguiente


def test_spot_t_mas_1_faltante_no_se_rellena():
    eventos = {"BTCUSDT": (_f("BTCUSDT", 8, "-0.0003"),)}
    spot = {"BTCUSDT": (SpotDiarioV15(BASE + 2 * DIA_MS, Decimal("100"), Decimal("101")),)}
    assert construir_observaciones_funding_v19(eventos, spot) == ()


def test_rechaza_funding_duplicado():
    e = _f("BTCUSDT", 8, "-0.0003")
    try:
        agregar_funding_diario_v19({"BTCUSDT": (e, e)})
    except ValueError as exc:
        assert "duplicado" in str(exc)
    else:
        raise AssertionError("debio rechazar duplicado")
