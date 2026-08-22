from datetime import date

from backend.economia.auditoria_world_orderflow_04g0 import (
    PairInventory04G0,
    evaluar_inventario_04g0,
)
from backend.economia.protocolo_world_orderflow_04g0 import (
    BASES_04G0,
    CALCULAR_ORDER_FLOW_PERMITIDO_04G0,
    DESARROLLO_2026_ABIERTO_04G0,
    MESES_OBJETIVO_04G0,
    MIN_BASES_MULTIQUOTE_POR_MES_04G0,
    MIN_QUOTES_POR_BASE_MES_04G0,
    ML_PERMITIDO_04G0,
    PNL_PERMITIDO_04G0,
    QUOTES_04G0,
    STATUS_APTO_04G0,
    STATUS_NO_APTO_04G0,
)


def _inventory(active_quotes_by_base):
    out = []
    months = tuple(MESES_OBJETIVO_04G0)
    for base in BASES_04G0:
        active = set(active_quotes_by_base.get(base, ()))
        for quote in QUOTES_04G0:
            out.append(PairInventory04G0(
                base=base,
                quote=quote,
                symbol=f"{base}{quote}",
                listing_complete=True,
                months=months if quote in active else (),
                compressed_bytes=100 if quote in active else 0,
            ))
    return tuple(out)


def test_protocol_locks():
    assert len(BASES_04G0) == 20
    assert MIN_QUOTES_POR_BASE_MES_04G0 == 2
    assert MIN_BASES_MULTIQUOTE_POR_MES_04G0 == 15
    assert len(MESES_OBJETIVO_04G0) == 48
    assert CALCULAR_ORDER_FLOW_PERMITIDO_04G0 is False
    assert ML_PERMITIDO_04G0 is False
    assert PNL_PERMITIDO_04G0 is False
    assert DESARROLLO_2026_ABIERTO_04G0 is False


def test_synthetic_multiquote_passes():
    active = {base: ("USDT", "BUSD") for base in BASES_04G0}
    result = evaluar_inventario_04g0(_inventory(active))
    assert result["status"] == STATUS_APTO_04G0
    assert result["months_passing_multiquote_gate"] == 48
    assert result["multi_quote_bases_min"] == 20
    assert result["pnl_calculated"] is False


def test_fails_closed_if_only_fourteen_bases_have_two_quotes():
    active = {}
    for i, base in enumerate(BASES_04G0):
        active[base] = ("USDT", "BUSD") if i < 14 else ("USDT",)
    result = evaluar_inventario_04g0(_inventory(active))
    assert result["status"] == STATUS_NO_APTO_04G0
    assert result["multi_quote_bases_min"] == 14
    assert any(r.startswith("BASES_MULTIQUOTE_") for r in result["reasons"])


def test_incomplete_listing_fails_closed():
    inventories = list(_inventory({base: ("USDT", "BUSD") for base in BASES_04G0}))
    first = inventories[0]
    inventories[0] = PairInventory04G0(
        base=first.base,
        quote=first.quote,
        symbol=first.symbol,
        listing_complete=False,
        months=(),
        compressed_bytes=0,
        error="synthetic",
    )
    result = evaluar_inventario_04g0(tuple(inventories))
    assert result["status"] == STATUS_NO_APTO_04G0
    assert "PAIR_LISTING_INCOMPLETE" in result["reasons"]
