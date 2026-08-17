"""Guardas de seguridad para las fuentes de coste 04A-1."""
from types import SimpleNamespace


def test_error_de_cuenta_firmada_no_publica_signature(monkeypatch, capsys):
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
            raise RuntimeError(
                "GET https://api.binance.com/api/v3/account?timestamp=123&"
                "signature=SECRETO-NO-DEBE-SALIR")

    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    monkeypatch.setattr(ac.binance, "client", Cliente(), raising=False)
    monkeypatch.setattr(ac.simulator, "positions", {}, raising=False)

    activos, _, _, costes = ac.get_available_assets(incluir_costes_cuenta=True)
    salida = capsys.readouterr().out

    assert [a["symbol"] for a in activos] == ["BTCUSDT"]
    assert costes["fee_taker_bps_por_lado"] is None
    assert "SECRETO-NO-DEBE-SALIR" not in salida
    assert "signature=***REDACTADO***" in salida
