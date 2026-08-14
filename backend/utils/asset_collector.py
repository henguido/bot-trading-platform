from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.simulation.simulator import Simulator

# Instancias compartidas
binance = BinanceConnector()
simulator = Simulator()

def get_available_assets():
    """
    Devuelve una lista de activos (cripto) operables contra USDT que estén activos y permitidos en spot.
    También retorna los balances y symbols_info para evitar consultas duplicadas.
    """
    try:
        binance.init_client()
        exchange_info = binance.client.get_exchange_info()
        symbols_info = exchange_info.get("symbols", [])
        balances = binance.get_account_balance()
    except Exception as e:
        print(f"❌ Error al inicializar Binance o traer datos: {e}")
        import traceback
        traceback.print_exc()
        return [], [], []

    activos = []
    saldos = {b["asset"]: float(b["free"]) + float(b["locked"]) for b in balances}

    for s in symbols_info:
        symbol = s.get("symbol")
        base_asset = s.get("baseAsset")
        quote_asset = s.get("quoteAsset")

        if (
            quote_asset == "USDT"
            and s.get("status") == "TRADING"
            and s.get("isSpotTradingAllowed")
        ):
            activos.append({
                "symbol": symbol,
                "type": "crypto",
                "has_balance": saldos.get(base_asset, 0.0) > 0,
                "has_position": symbol in simulator.positions and simulator.positions[symbol].quantity > 0
            })

    return activos, balances, symbols_info

def get_market_pairs(symbols_info=None):
    """
    Devuelve todos los pares activos disponibles con sus precios actuales.
    Estructura: [{"pair": "BTCETH", "price": 13.45}, ...]
    """
    try:
        binance.init_client()
        if symbols_info is None:
            exchange_info = binance.client.get_exchange_info()
            symbols_info = exchange_info.get("symbols", [])
    except Exception as e:
        print(f"❌ Error al obtener exchange info de Binance: {e}")
        return []

    pairs = []
    for s in symbols_info:
        if s.get("status") == "TRADING" and s.get("isSpotTradingAllowed"):
            pair_symbol = s["symbol"]
            try:
                price = float(binance.get_current_price(pair_symbol))
                pairs.append({"pair": pair_symbol, "price": price})
            except Exception:
                continue

    return pairs
