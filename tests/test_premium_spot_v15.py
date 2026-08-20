from decimal import Decimal

from backend.economia.historico_derivados_v14 import PremiumDiarioV14
from backend.economia.historico_spot_diario_v15 import DIA_MS, SpotDiarioV15
from backend.economia.premium_spot_v15 import construir_observaciones_premium_v15

T0 = 1640995200000


def _premium(ts, close="-0.001"):
    c = Decimal(close)
    return PremiumDiarioV14(ts, c, c, c, c)


def _spot(ts, open_="100", close="105"):
    return SpotDiarioV15(ts, Decimal(open_), Decimal(close))


def test_signal_t_entra_open_t1_y_sale_close_t1_sin_lookahead():
    premium = {"BTCUSDT": (_premium(T0),)}
    spot = {"BTCUSDT": (
        _spot(T0, "1", "999"),
        _spot(T0 + DIA_MS, "100", "105"),
        _spot(T0 + 2 * DIA_MS, "100", "1"),
    )}
    out = construir_observaciones_premium_v15(premium, spot)
    assert len(out) == 1
    o = out[0]
    assert o.timestamp_signal_ms == T0
    assert o.timestamp_entrada_ms == T0 + DIA_MS
    assert o.retorno_spot_siguiente == Decimal("0.05")


def test_cambiar_t2_no_cambia_label_de_t():
    premium = {"BTCUSDT": (_premium(T0),)}
    a = {"BTCUSDT": (_spot(T0 + DIA_MS, "100", "105"), _spot(T0 + 2 * DIA_MS, "1", "1000"))}
    b = {"BTCUSDT": (_spot(T0 + DIA_MS, "100", "105"), _spot(T0 + 2 * DIA_MS, "1000", "1"))}
    assert construir_observaciones_premium_v15(premium, a) == construir_observaciones_premium_v15(premium, b)


def test_falta_spot_t1_no_se_rellena():
    premium = {"BTCUSDT": (_premium(T0),)}
    spot = {"BTCUSDT": (_spot(T0 + 2 * DIA_MS),)}
    assert construir_observaciones_premium_v15(premium, spot) == ()


def test_signal_ultimo_dia_2025_no_consume_2026():
    dec31_2025 = 1767139200000
    premium = {"BTCUSDT": (_premium(dec31_2025),)}
    spot = {"BTCUSDT": (_spot(dec31_2025 + DIA_MS),)}
    assert construir_observaciones_premium_v15(premium, spot) == ()


def test_orden_de_entrada_no_afecta_salida():
    premium = {
        "ETHUSDT": (_premium(T0, "0.002"),),
        "BTCUSDT": (_premium(T0, "-0.001"),),
    }
    spot = {
        "ETHUSDT": (_spot(T0 + DIA_MS, "100", "101"),),
        "BTCUSDT": (_spot(T0 + DIA_MS, "100", "102"),),
    }
    out = construir_observaciones_premium_v15(premium, spot)
    assert tuple(o.symbol for o in out) == ("BTCUSDT", "ETHUSDT")
