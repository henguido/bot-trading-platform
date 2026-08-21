from __future__ import annotations

from decimal import Decimal

from backend.economia.auditoria_produccion_04d1 import (
    _fill_base,
    _fill_spot_buy_quote,
    auditar_stress_margen_04d1,
)
from backend.economia.protocolo_produccion_04d1 import (
    CAPITAL_TOTAL_REFERENCIA_04C2,
    CREDENCIALES_REQUERIDAS_04D1,
    DESARROLLO_2026_RETORNOS_ABIERTO_04D1,
    DRAG_ALL_IN_BPS_HEREDADO_04C2,
    MARGEN_FUTURES_ESTATICO_MULTIPLO_04D1,
    MAX_FRICCION_LIBRO_ROUNDTRIP_BPS_04D1,
    NOTIONALES_USD_04D1,
    ORDENES_PERMITIDAS_04D1,
    RECALIBRAR_GATE_04C2_PERMITIDO_04D1,
    SIMBOLOS_04D1,
)


def test_protocol_locks_prohibit_orders_credentials_and_gate_rewrite():
    assert SIMBOLOS_04D1 == ("BTCUSDT", "ETHUSDT")
    assert NOTIONALES_USD_04D1 == (
        Decimal("500"), Decimal("5000"), Decimal("25000"), Decimal("100000")
    )
    assert DRAG_ALL_IN_BPS_HEREDADO_04C2 == Decimal("60")
    assert MAX_FRICCION_LIBRO_ROUNDTRIP_BPS_04D1 == Decimal("10")
    assert MARGEN_FUTURES_ESTATICO_MULTIPLO_04D1 == Decimal("1")
    assert CAPITAL_TOTAL_REFERENCIA_04C2 == Decimal("2")
    assert ORDENES_PERMITIDAS_04D1 is False
    assert CREDENCIALES_REQUERIDAS_04D1 is False
    assert RECALIBRAR_GATE_04C2_PERMITIDO_04D1 is False
    assert DESARROLLO_2026_RETORNOS_ABIERTO_04D1 is False


def test_market_fill_uses_multiple_levels_and_reports_depth_impact():
    asks = ((Decimal("100"), Decimal("1")), (Decimal("101"), Decimal("2")))
    buy = _fill_spot_buy_quote(asks, Decimal("200"))
    assert buy.base_qty > Decimal("1.98")
    assert buy.vwap > Decimal("100")
    assert buy.impact_bps > 0
    assert buy.levels == 2

    bids = ((Decimal("100"), Decimal("1")), (Decimal("99"), Decimal("2")))
    sell = _fill_base(bids, Decimal("2"), side="sell")
    assert sell.vwap == Decimal("99.5")
    assert sell.impact_bps == Decimal("50.00")
    assert sell.levels == 2


def test_04c2_fixture_proves_static_2x_architecture_failed_historical_lower_bound():
    rows = auditar_stress_margen_04d1()
    assert len(rows) == 8
    by_key = {(r.symbol, r.year): r for r in rows}

    btc_2023 = by_key[("BTCUSDT", 2023)]
    assert btc_2023.mark_excursion == Decimal("1.6796")
    assert btc_2023.minimum_total_capital_multiple_no_maintenance == Decimal("2.6796")
    assert btc_2023.lower_bound_topup_from_1x == Decimal("0.6796")
    assert btc_2023.static_2x_not_disproven is False

    btc_2024 = by_key[("BTCUSDT", 2024)]
    assert btc_2024.static_2x_not_disproven is False
    assert btc_2024.lower_bound_topup_from_1x == Decimal("0.5415")

    eth_2023 = by_key[("ETHUSDT", 2023)]
    assert eth_2023.minimum_total_capital_multiple_no_maintenance == Decimal("2.0422")
    assert eth_2023.static_2x_not_disproven is False

    # El test es un lower bound favorable: no incorpora maintenance margin.
    assert max(r.minimum_total_capital_multiple_no_maintenance for r in rows) == Decimal("2.6796")
