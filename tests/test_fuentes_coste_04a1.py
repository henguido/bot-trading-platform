"""BOT 2.0-04A-1 · fuentes reales/auditables del Cost Model."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.economia.fuentes import (
    DISPONIBLE,
    NO_DISPONIBLE,
    asignar_costo_ia,
    estimar_slippage_compra,
    estimar_slippage_roundtrip,
    estimar_slippage_venta,
    extraer_taker_bps,
)
from backend.economia.profundidad import obtener_order_book
from backend.telemetria_http import MedidorCicloHttp

RAIZ = Path(__file__).resolve().parents[1]
MAIN = RAIZ / "backend" / "main.py"


# ── Fee de cuenta ───────────────────────────────────────────────────────────
def test_fee_taker_sale_de_commission_rates_y_pasa_a_bps():
    info = {"commissionRates": {"maker": "0.0005", "taker": "0.001"}}
    assert extraer_taker_bps(info) == Decimal("10.000")


@pytest.mark.parametrize("info", [
    None, {}, {"commissionRates": None}, {"commissionRates": {}},
    {"commissionRates": {"taker": "?"}}, {"commissionRates": {"taker": "-0.1"}},
])
def test_fee_ausente_o_invalida_es_desconocida_no_cero(info):
    assert extraer_taker_bps(info) is None


def test_get_available_assets_reutiliza_misma_peticion_de_cuenta(monkeypatch):
    from backend.utils import asset_collector as ac

    symbols = [{
        "symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
        "status": "TRADING", "isSpotTradingAllowed": True, "filters": [],
    }]

    class Cliente:
        def __init__(self):
            self.account_calls = 0
            self.response = None

        def get_exchange_info(self):
            self.response = SimpleNamespace(status_code=200)
            return {"symbols": symbols}

        def get_account(self):
            self.account_calls += 1
            self.response = SimpleNamespace(status_code=200)
            return {
                "balances": [{"asset": "USDT", "free": "500", "locked": "0"}],
                "commissionRates": {"taker": "0.001"},
            }

    cliente = Cliente()
    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    monkeypatch.setattr(ac.binance, "client", cliente, raising=False)
    monkeypatch.setattr(ac.simulator, "positions", {}, raising=False)

    activos, balances, info, costes = ac.get_available_assets(incluir_costes_cuenta=True)

    assert cliente.account_calls == 1, "fees y balance deben salir del MISMO get_account"
    assert [a["symbol"] for a in activos] == ["BTCUSDT"]
    assert balances[0]["asset"] == "USDT"
    assert info == symbols
    assert costes == {
        "fee_taker_bps_por_lado": 10.0,
        "fuente_fee": "binance_account.commissionRates.taker",
        "fee_maker_bps_por_lado": None,
        "fuente_fee_maker": "NO_DISPONIBLE",
    }


def test_firma_historica_de_get_available_assets_sigue_en_tres_elementos(monkeypatch):
    from backend.utils import asset_collector as ac

    class Cliente:
        response = None
        def get_exchange_info(self):
            self.response = SimpleNamespace(status_code=200)
            return {"symbols": []}
        def get_account(self):
            self.response = SimpleNamespace(status_code=200)
            return {"balances": [], "commissionRates": {"taker": "0.001"}}

    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    monkeypatch.setattr(ac.binance, "client", Cliente(), raising=False)
    salida = ac.get_available_assets()
    assert isinstance(salida, tuple) and len(salida) == 3


def test_fallo_de_cuenta_no_borra_universo_publico(monkeypatch):
    from backend.utils import asset_collector as ac

    symbols = [{
        "symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
        "status": "TRADING", "isSpotTradingAllowed": True, "filters": [],
    }]

    class Cliente:
        response = None
        def get_exchange_info(self):
            self.response = SimpleNamespace(status_code=200)
            return {"symbols": symbols}
        def get_account(self):
            raise ConnectionError("cuenta privada no disponible")

    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    monkeypatch.setattr(ac.binance, "client", Cliente(), raising=False)
    monkeypatch.setattr(ac.simulator, "positions", {}, raising=False)

    activos, balances, _, costes = ac.get_available_assets(incluir_costes_cuenta=True)
    assert [a["symbol"] for a in activos] == ["BTCUSDT"]
    assert balances == []
    assert costes["fee_taker_bps_por_lado"] is None
    assert costes["fuente_fee"] == "NO_DISPONIBLE"
    assert costes["fee_maker_bps_por_lado"] is None
    assert costes["fuente_fee_maker"] == "NO_DISPONIBLE"


# ── Slippage por profundidad ────────────────────────────────────────────────
def test_compra_en_mejor_ask_sin_barrer_niveles_tiene_slippage_cero():
    e = estimar_slippage_compra([["100", "1"]], quote_amount="10")
    assert e.estado == DISPONIBLE
    assert e.vwap == Decimal("100")
    assert e.slippage_bps == Decimal("0")


def test_compra_que_barre_dos_asks_tiene_slippage_positivo():
    e = estimar_slippage_compra([["100", "0.05"], ["101", "0.10"]],
                                 quote_amount="10")
    assert e.estado == DISPONIBLE
    assert e.best_price == Decimal("100")
    assert e.vwap > e.best_price
    assert e.slippage_bps > 0


def test_venta_que_barre_dos_bids_tiene_slippage_positivo():
    e = estimar_slippage_venta([["100", "0.05"], ["99", "0.10"]],
                                base_quantity="0.10")
    assert e.estado == DISPONIBLE
    assert e.best_price == Decimal("100")
    assert e.vwap < e.best_price
    assert e.slippage_bps > 0


def test_profundidad_insuficiente_no_inventa_slippage():
    e = estimar_slippage_compra([["100", "0.01"]], quote_amount="10")
    assert e.estado == NO_DISPONIBLE
    assert e.slippage_bps is None
    assert e.faltante == "profundidad_insuficiente"


def test_roundtrip_reutiliza_base_comprada_para_estimar_salida():
    book = {
        "asks": [["100", "1"]],
        "bids": [["99.9", "1"]],
    }
    r = estimar_slippage_roundtrip(book, quote_amount="10")
    assert r.estado == DISPONIBLE
    assert r.entrada.base_ejecutada == Decimal("0.1")
    assert r.salida.base_ejecutada == Decimal("0.1")
    # Un único nivel por lado: spread existe, pero slippage adicional es cero.
    assert r.entrada.slippage_bps == Decimal("0")
    assert r.salida.slippage_bps == Decimal("0")
    assert r.slippage_bps_por_lado_promedio == Decimal("0")


def test_order_book_es_una_sola_peticion_on_demand():
    class Cliente:
        def __init__(self):
            self.calls = 0
            self.response = None
        def get_order_book(self, **kwargs):
            self.calls += 1
            self.response = SimpleNamespace(status_code=200)
            assert kwargs == {"symbol": "BTCUSDT", "limit": 20}
            return {"asks": [["100", "1"]], "bids": [["99", "1"]]}

    class Conector:
        def __init__(self):
            self.client = Cliente()
        def init_client(self):
            return None
        def observador_http(self):
            return None

    c = Conector()
    m = MedidorCicloHttp()
    op = m.operacion("binance", "order_book_coste")
    book = obtener_order_book(c, "BTCUSDT", limit=20, medicion=op)

    assert c.client.calls == 1
    assert book["asks"] and book["bids"]
    assert op.metricas.n_requests == 1
    assert op.metricas.n_elementos == 2


def test_profundidad_no_esta_conectada_al_loop_ni_al_scanner():
    main = MAIN.read_text(encoding="utf-8")
    scanner = (RAIZ / "backend" / "scanner.py").read_text(encoding="utf-8")
    assert "obtener_order_book" not in main
    assert "obtener_order_book" not in scanner


# ── Asignación del coste IA ─────────────────────────────────────────────────
def test_costo_ia_se_reparte_una_sola_vez_entre_decisiones_accionables():
    a = asignar_costo_ia("0.009", decisiones_accionables=3)
    assert a.estado == DISPONIBLE
    assert a.costo_por_operacion_usd == Decimal("0.003")
    assert a.costo_screening_sin_asignar_usd == Decimal("0")
    assert a.costo_por_operacion_usd * 3 == a.costo_llamada_usd


def test_llm_sin_operaciones_deja_todo_como_screening_del_ciclo():
    a = asignar_costo_ia("0.0084475", decisiones_accionables=0)
    assert a.estado == DISPONIBLE
    assert a.costo_por_operacion_usd is None
    assert a.costo_screening_sin_asignar_usd == Decimal("0.0084475")


def test_costo_llm_desconocido_no_se_convierte_en_cero():
    a = asignar_costo_ia(None, decisiones_accionables=1)
    assert a.estado == NO_DISPONIBLE
    assert a.costo_por_operacion_usd is None
    assert a.costo_screening_sin_asignar_usd is None


@pytest.mark.parametrize("n", [-1, 1.5, True])
def test_numero_de_decisiones_accionables_invalido_se_rechaza(n):
    with pytest.raises(ValueError):
        asignar_costo_ia("0.01", decisiones_accionables=n)
