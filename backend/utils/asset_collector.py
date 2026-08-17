from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.simulation.simulator import Simulator
from backend.telemetria_http import MEDIDOR_NULO

# Instancias compartidas
binance = BinanceConnector()
simulator = Simulator()

def get_available_assets(medidor=None):
    """
    Devuelve una lista de activos (cripto) operables contra USDT que estén activos y permitidos en spot.
    También retorna los balances y symbols_info para evitar consultas duplicadas.

    `medidor` es telemetria opcional (fase 02A). Cuando no se pasa se usa un
    medidor nulo: no cambia ninguna rama de ejecucion.
    """
    m = medidor if medidor is not None else MEDIDOR_NULO
    op_info = m.operacion("binance", "exchange_info")
    op_saldos = m.operacion("binance", "account_balance")
    try:
        binance.init_client()
        observador = binance.observador_http()
        # get_exchange_info SI propaga sus fallos: no hace falta evidencia.
        with op_info.peticion(observador=observador):
            exchange_info = binance.client.get_exchange_info()
        symbols_info = exchange_info.get("symbols", [])
        op_info.elementos(len(symbols_info))
        # get_account_balance, en cambio, captura la excepcion y devuelve [].
        # Una lista vacia es ambigua (cuenta sin saldo o peticion muerta), asi
        # que sin evidencia positiva no se cuenta como exito.
        with op_saldos.peticion(observador=observador,
                                exige_evidencia=True) as p:
            balances = binance.get_account_balance()
            if balances:
                p.marcar_ok()
        op_saldos.elementos(len(balances))
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

def get_market_pairs(symbols_info=None, medidor=None):
    """
    Devuelve todos los pares activos disponibles con sus precios actuales.
    Estructura: [{"pair": "BTCETH", "price": 13.45}, ...]

    Pide un ticker INDIVIDUAL por par: es el mayor consumidor de peticiones del
    ciclo. 02A lo cuantifica; 02B lo corrige.
    """
    m = medidor if medidor is not None else MEDIDOR_NULO
    op = m.operacion("binance", "get_market_pairs")
    observador = None
    try:
        binance.init_client()
        observador = binance.observador_http()
        if symbols_info is None:
            op_info = m.operacion("binance", "exchange_info")
            with op_info.peticion(observador=observador):
                exchange_info = binance.client.get_exchange_info()
            symbols_info = exchange_info.get("symbols", [])
            op_info.elementos(len(symbols_info))
    except Exception as e:
        print(f"❌ Error al obtener exchange info de Binance: {e}")
        return []

    pairs = []
    for s in symbols_info:
        if s.get("status") == "TRADING" and s.get("isSpotTradingAllowed"):
            pair_symbol = s["symbol"]
            try:
                # exige_evidencia: get_current_price captura sus excepciones y
                # devuelve 0.0, asi que la ausencia de excepcion no prueba nada.
                with op.peticion(observador=observador,
                                 exige_evidencia=True) as p:
                    price = float(binance.get_current_price(pair_symbol))
                    if price:
                        p.marcar_ok()      # evidencia positiva: llego un precio
                    else:
                        p.marcar_error()   # la excepcion se trago dentro
                pairs.append({"pair": pair_symbol, "price": price})
            except Exception:
                continue

    op.elementos(len(pairs))
    return pairs
