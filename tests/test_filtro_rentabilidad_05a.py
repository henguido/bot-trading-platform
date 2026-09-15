from backend.economia.filtro_rentabilidad_05a import (
    ResumenFiltroRentabilidad,
    filtrar_compras_rentables,
)


class BinanceFake:
    def __init__(self, *, klines, book):
        self.klines = klines
        self.book = book
        self.klines_calls = []
        self.book_calls = []

    def get_recent_klines(self, symbol, *, interval, limit, medicion=None):
        self.klines_calls.append((symbol, interval, limit))
        return self.klines.get(symbol, [])

    def get_order_book(self, symbol, *, limit, medicion=None):
        self.book_calls.append((symbol, limit))
        return self.book.get(symbol, {})


def _klines_alcistas(n=1000, inicio=100.0, factor=1.002):
    filas = []
    hora = 3_600_000
    precio = inicio
    for i in range(n):
        precio *= factor
        filas.append([
            i * hora, str(precio), str(precio), str(precio), str(precio), "1",
            (i + 1) * hora - 1,
        ])
    return filas


def _metricas(bid="100", ask="100.02"):
    return {"bidPrice": bid, "askPrice": ask}


def _book():
    return {
        "asks": [["100.02", "1000"]],
        "bids": [["100.00", "1000"]],
    }


def test_fee_desconocida_bloquea_sin_hacer_red_profunda():
    fake = BinanceFake(klines={}, book={})
    activos = [{"symbol": "AAAUSDT", "_position_detected": False}]
    r = ResumenFiltroRentabilidad()
    salida, evs = filtrar_compras_rentables(
        activos, {"AAAUSDT": _metricas()}, fee_taker_bps_por_lado=None,
        notional_por_symbol={"AAAUSDT": 10}, binance=fake, resumen=r,
    )
    assert salida == []
    assert evs["AAAUSDT"]["motivo"] == "FEE_DESCONOCIDA"
    assert fake.klines_calls == []
    assert fake.book_calls == []


def test_posicion_abierta_se_preserva_sin_edge():
    fake = BinanceFake(klines={}, book={})
    pos = {"symbol": "BTCUSDT", "_position_detected": True, "position_quantity": 0.1}
    salida, _ = filtrar_compras_rentables(
        [pos], {}, fee_taker_bps_por_lado=10,
        notional_por_symbol={}, binance=fake,
    )
    assert salida == [pos]
    assert fake.klines_calls == []


def test_solo_profundiza_cinco_finalistas():
    syms = [f"A{i}USDT" for i in range(8)]
    klines = {s: _klines_alcistas() for s in syms}
    books = {s: _book() for s in syms}
    fake = BinanceFake(klines=klines, book=books)
    activos = [{"symbol": s, "_position_detected": False} for s in syms]
    metricas = {s: _metricas() for s in syms}
    notionals = {s: 10 for s in syms}

    salida, _ = filtrar_compras_rentables(
        activos, metricas, fee_taker_bps_por_lado=10,
        notional_por_symbol=notionals, binance=fake,
        ahora_ms=2_000 * 3_600_000,
    )
    assert len(fake.klines_calls) == 5
    assert len(salida) <= 5


def test_edge_fuerte_cubre_costes_y_pasa():
    sym = "AAAUSDT"
    fake = BinanceFake(klines={sym: _klines_alcistas(factor=1.003)}, book={sym: _book()})
    activo = {"symbol": sym, "_position_detected": False}
    salida, evs = filtrar_compras_rentables(
        [activo], {sym: _metricas()}, fee_taker_bps_por_lado=10,
        notional_por_symbol={sym: 10}, binance=fake,
        ahora_ms=2_000 * 3_600_000,
    )
    assert len(salida) == 1
    assert salida[0]["symbol"] == sym
    assert salida[0]["_edge_neto_bps"] > 5
    assert evs[sym]["rentabilidad"].apta is True
    assert len(fake.book_calls) == 1


def test_sin_edge_no_gasta_order_book():
    sym = "FLATUSDT"
    hora = 3_600_000
    filas = [
        [i * hora, "100", "100", "100", "100", "1", (i + 1) * hora - 1]
        for i in range(1000)
    ]
    fake = BinanceFake(klines={sym: filas}, book={sym: _book()})
    salida, evs = filtrar_compras_rentables(
        [{"symbol": sym, "_position_detected": False}],
        {sym: _metricas()}, fee_taker_bps_por_lado=10,
        notional_por_symbol={sym: 10}, binance=fake,
        ahora_ms=2_000 * hora,
    )
    assert salida == []
    assert evs[sym]["motivo"] == "SIN_SENAL"
    assert fake.book_calls == []
