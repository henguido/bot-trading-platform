from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.simulation.simulator import Simulator
from backend.telemetria_http import MEDIDOR_NULO, anotar_elementos

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
        anotar_elementos(op_info, len(symbols_info))
        # get_account_balance, en cambio, captura la excepcion y devuelve [].
        # Una lista vacia es ambigua (cuenta sin saldo o peticion muerta), asi
        # que sin evidencia positiva no se cuenta como exito.
        with op_saldos.peticion(observador=observador,
                                exige_evidencia=True) as p:
            balances = binance.get_account_balance()
            if balances:
                p.marcar_ok()
        anotar_elementos(op_saldos, len(balances))
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

def get_market_pairs(symbols_info=None, snapshot=None, medidor=None):
    """
    Devuelve todos los pares activos disponibles con sus precios actuales.
    Estructura: [{"pair": "BTCETH", "price": 13.45}, ...]

    Fase BOT 2.0-02B: se construye ENTERAMENTE EN MEMORIA. 02A midio aqui 1.361
    peticiones -una por par- y 342.594 ms de reloj para que el prompt acabara
    recibiendo 0 pares. Ahora esta funcion no hace ninguna peticion propia:
    combina `symbols_info` con el snapshot de precios del ciclo.

    El criterio de que par se considera operable NO cambia: sigue siendo
    status == TRADING y isSpotTradingAllowed. Lo unico que se anade es que su
    precio tiene que existir en el snapshot; un par sin precio conocido se
    omite en lugar de publicarse con un 0.0 inventado.

    `symbols_info` y `snapshot` se piden solo si nadie los aporta, y en ese
    caso cuesta UNA peticion cada uno, nunca una por par.
    """
    m = medidor if medidor is not None else MEDIDOR_NULO
    op = m.operacion("binance", "get_market_pairs")
    try:
        binance.init_client()
        if symbols_info is None:
            op_info = m.operacion("binance", "exchange_info")
            with op_info.peticion(observador=binance.observador_http()):
                exchange_info = binance.client.get_exchange_info()
            symbols_info = exchange_info.get("symbols", [])
            anotar_elementos(op_info, len(symbols_info))
        if snapshot is None:
            snapshot = binance.get_price_snapshot(
                medicion=m.operacion("binance", "market_price_snapshot"))
    except Exception as e:
        print(f"❌ Error al obtener exchange info de Binance: {e}")
        return []

    pairs = []
    for s in symbols_info:
        if s.get("status") == "TRADING" and s.get("isSpotTradingAllowed"):
            pair_symbol = s["symbol"]
            precio = snapshot.get(pair_symbol)
            if precio is None:
                continue          # sin precio conocido no se publica el par
            pairs.append({"pair": pair_symbol, "price": float(precio)})

    anotar_elementos(op, len(pairs))
    return pairs
