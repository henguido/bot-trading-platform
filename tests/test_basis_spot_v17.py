from decimal import Decimal

from backend.economia.basis_spot_v17 import construir_observaciones_basis_v17
from backend.economia.edge_historico import Vela
from backend.economia.historico_spot_diario_v15 import DIA_MS, SpotDiarioV15

T0 = 1640995200000


def _fut(ts, close="90"):
    c = Decimal(close)
    return Vela(ts, c, c, c, c, Decimal("1"), ts + DIA_MS - 1, c, 1)


def _spot(ts, open_="100", close="100"):
    return SpotDiarioV15(ts, Decimal(open_), Decimal(close))


def test_basis_formula_y_label_t1_son_exactos():
    fut = {"BTCUSDT": (_fut(T0, "90"),)}
    spot = {"BTCUSDT": (_spot(T0, "99", "100"), _spot(T0 + DIA_MS, "100", "105"))}
    out = construir_observaciones_basis_v17(fut, spot)
    assert len(out) == 1
    o = out[0]
    assert o.basis_perp == Decimal("10") / Decimal("90")
    assert o.retorno_spot_siguiente == Decimal("0.05")
    assert o.timestamp_entrada_ms == T0 + DIA_MS


def test_cambiar_futuro_t1_no_cambia_basis_t():
    fut_a = {"BTCUSDT": (_fut(T0, "90"), _fut(T0 + DIA_MS, "1"))}
    fut_b = {"BTCUSDT": (_fut(T0, "90"), _fut(T0 + DIA_MS, "10000"))}
    spot = {"BTCUSDT": (_spot(T0, "99", "100"), _spot(T0 + DIA_MS, "100", "105"))}
    assert construir_observaciones_basis_v17(fut_a, spot)[0] == construir_observaciones_basis_v17(fut_b, spot)[0]


def test_si_falta_spot_o_futures_en_t_no_se_imputa():
    spot = {"BTCUSDT": (_spot(T0), _spot(T0 + DIA_MS),)}
    assert construir_observaciones_basis_v17({}, spot) == ()
    assert construir_observaciones_basis_v17({"BTCUSDT": ()}, spot) == ()


def test_31_dic_2025_no_consume_2026():
    dec31 = 1767139200000
    fut = {"BTCUSDT": (_fut(dec31),)}
    spot = {"BTCUSDT": (_spot(dec31), _spot(dec31 + DIA_MS))}
    assert construir_observaciones_basis_v17(fut, spot) == ()
