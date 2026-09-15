import pytest

from backend.economia.estadisticas_paper import resumen_por_estrategia


def op(symbol, side, qty, quote_net, *, strategy=None, expected_net_bps=None):
    return {
        "symbol": symbol,
        "side": side,
        "base_quantity": qty,
        "quote_net": quote_net,
        "strategy": strategy,
        "expected_net_bps": expected_net_bps,
    }


def test_fifo_reparte_venta_entre_estrategias_de_entrada():
    operaciones = [
        # A compra 1 BTC a coste neto 100; B compra 1 BTC a coste neto 120.
        op("BTCUSDT", "BUY", 1.0, 100.0, strategy="A", expected_net_bps=100.0),
        op("BTCUSDT", "BUY", 1.0, 120.0, strategy="B", expected_net_bps=50.0),
        # Venta neta 1.5 BTC por 180 => 120 por BTC. FIFO consume A completo y B 0.5.
        op("BTCUSDT", "SELL", 1.5, 180.0),
    ]

    r = resumen_por_estrategia(operaciones)
    a = r["estrategias"]["A"]
    b = r["estrategias"]["B"]

    assert r["metodologia"] == "FIFO_POR_ESTRATEGIA_DE_ENTRADA"
    assert r["pnl_incluye_fees_ejecutadas"] is True

    assert a["coste_cerrado_usd"] == pytest.approx(100.0)
    assert a["pnl_realizado_neto_usd"] == pytest.approx(20.0)
    assert a["retorno_realizado_neto_bps"] == pytest.approx(2000.0)
    assert a["expected_net_bps_ponderado"] == pytest.approx(100.0)
    assert a["error_expected_vs_realizado_bps"] == pytest.approx(1900.0)
    assert a["cierres"] == 1
    assert a["positive_rate"] == pytest.approx(1.0)
    assert a["cantidad_abierta"] == pytest.approx(0.0)

    assert b["coste_cerrado_usd"] == pytest.approx(60.0)
    assert b["pnl_realizado_neto_usd"] == pytest.approx(0.0)
    assert b["retorno_realizado_neto_bps"] == pytest.approx(0.0)
    assert b["expected_net_bps_ponderado"] == pytest.approx(50.0)
    assert b["error_expected_vs_realizado_bps"] == pytest.approx(-50.0)
    assert b["cierres"] == 1
    assert b["positive_rate"] == pytest.approx(0.0)
    assert b["cantidad_abierta"] == pytest.approx(0.5)
    assert b["coste_abierto_usd"] == pytest.approx(60.0)


def test_estrategia_desconocida_no_se_inventa():
    r = resumen_por_estrategia([
        op("ETHUSDT", "BUY", 1.0, 100.0),
    ])

    fila = r["estrategias"]["SIN_ESTRATEGIA"]
    assert fila["expected_net_bps_ponderado"] is None
    assert fila["retorno_realizado_neto_bps"] is None
    assert fila["positive_rate"] is None
    assert fila["cantidad_abierta"] == pytest.approx(1.0)


def test_venta_mayor_que_lotes_falla_cerrado():
    with pytest.raises(ValueError, match="excede lotes"):
        resumen_por_estrategia([
            op("BTCUSDT", "BUY", 1.0, 100.0, strategy="A"),
            op("BTCUSDT", "SELL", 2.0, 220.0),
        ])
