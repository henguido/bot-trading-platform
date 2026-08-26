from types import SimpleNamespace

import pytest

from backend.simulation.paper_ledger import reconstruir_paper


def op(side, qty, quote_net, fee, symbol="BTCUSDT"):
    return SimpleNamespace(
        symbol=symbol,
        side=side,
        base_quantity=qty,
        quote_net=quote_net,
        fee_usd=fee,
    )


def test_reconstruccion_paper_incluye_fees_en_coste_y_pnl():
    estado = reconstruir_paper(500.0, [
        # Compra 0.1 BTC: notional 10 + fee .01 = coste efectivo 10.01.
        op("BUY", 0.1, 10.01, 0.01),
        # Venta parcial: recibe 6 bruto - .006 fee = 5.994 neto.
        op("SELL", 0.05, 5.994, 0.006),
    ])

    assert estado.capital_usd == pytest.approx(495.984)
    assert estado.fees_total_usd == pytest.approx(0.016)
    assert estado.operaciones == 2
    assert estado.posiciones["BTCUSDT"].cantidad == pytest.approx(0.05)
    assert estado.posiciones["BTCUSDT"].coste_medio_neto == pytest.approx(100.1)
    assert estado.realized_pnl_usd == pytest.approx(0.989)


def test_reconstruccion_es_determinista_tras_reinicio():
    operaciones = [
        op("BUY", 0.1, 10.01, 0.01),
        op("BUY", 0.1, 12.012, 0.012),
        op("SELL", 0.05, 6.4935, 0.0065),
    ]
    a = reconstruir_paper(500, operaciones)
    b = reconstruir_paper(500, list(operaciones))
    assert a == b


def test_compra_que_supera_capital_falla_cerrado():
    with pytest.raises(ValueError, match="mas capital"):
        reconstruir_paper(10, [op("BUY", 1, 10.01, 0.01)])


def test_venta_sin_posicion_falla_cerrado():
    with pytest.raises(ValueError, match="vende mas posicion"):
        reconstruir_paper(500, [op("SELL", 0.1, 10, 0.01)])


def test_cerrar_posicion_elimina_exposicion_y_conserva_pnl_neto():
    estado = reconstruir_paper(100, [
        op("BUY", 1, 10.01, 0.01, "ETHUSDT"),
        op("SELL", 1, 10.989, 0.011, "ETHUSDT"),
    ])
    assert "ETHUSDT" not in estado.posiciones
    assert estado.exposicion_coste_usd == 0
    assert estado.capital_usd == pytest.approx(100.979)
    assert estado.realized_pnl_usd == pytest.approx(0.979)
