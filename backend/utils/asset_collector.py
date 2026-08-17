from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.economia.fuentes import extraer_taker_bps
from backend.simulation.simulator import Simulator
from backend.telemetria_http import (MEDIDOR_NULO, anotar_elementos,
                                     describir_error)

# Instancias compartidas
binance = BinanceConnector()
simulator = Simulator()


def get_available_assets(medidor=None, *, incluir_costes_cuenta=False):
    """
    Devuelve activos crypto/USDT operables, balances y symbols_info.

    04A-1: si `incluir_costes_cuenta=True`, devuelve además un cuarto elemento
    con la fee taker observada en EL MISMO GET /api/v3/account que ya se hacía
    para balances. No añade ninguna petición.

    El modo por defecto conserva exactamente la firma histórica de 3 elementos,
    para no romper consumidores ajenos a 04A.

    `medidor` es telemetria opcional. Cuando no se pasa se usa un medidor nulo.
    """
    m = medidor if medidor is not None else MEDIDOR_NULO
    op_info = m.operacion("binance", "exchange_info")
    op_saldos = m.operacion("binance", "account_balance")

    try:
        binance.init_client()
        observador = binance.observador_http()
        with op_info.peticion(observador=observador):
            exchange_info = binance.client.get_exchange_info()
        symbols_info = exchange_info.get("symbols", [])
        anotar_elementos(op_info, len(symbols_info))
    except Exception as e:
        print(f"❌ Error al inicializar Binance o traer exchange info: {describir_error(e)}")
        if incluir_costes_cuenta:
            return [], [], [], {"fee_taker_bps_por_lado": None,
                                "fuente_fee": "NO_DISPONIBLE"}
        return [], [], []

    account_info = None
    balances = []
    try:
        # Una sola llamada privada. Antes se delegaba a get_account_balance(),
        # que internamente hacía get_account() y descartaba commissionRates.
        # Ahora conservamos el mismo tráfico y aprovechamos ese payload para
        # extraer la fee taker. Fallo/ausencia => fee desconocida, nunca cero.
        with op_saldos.peticion(observador=observador,
                                exige_evidencia=True) as p:
            account_info = binance.client.get_account()
            balances_crudos = account_info.get("balances", []) if isinstance(account_info, dict) else []
            balances = [
                b for b in balances_crudos
                if float(b.get("free", 0) or 0) > 0 or float(b.get("locked", 0) or 0) > 0
            ]
            # La respuesta de cuenta es evidencia positiva aunque todos los
            # balances estén en cero. No confundimos "cuenta vacía" con fallo.
            if isinstance(account_info, dict):
                p.marcar_ok()
    except Exception as e:
        # Compatibilidad con el comportamiento anterior de get_account_balance:
        # un fallo privado NO borra el universo público. Sólo deja balances y
        # fee como desconocidos. En PAPER esto permite seguir analizando sin
        # depender de que el endpoint de cuenta esté disponible.
        # Se sanea porque una excepción de endpoint firmado puede incluir URL,
        # timestamp o signature en su representación.
        print(f"❌ Error obteniendo el balance: {describir_error(e)}")
        account_info = None
        balances = []
    anotar_elementos(op_saldos, len(balances))

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

    if incluir_costes_cuenta:
        fee = extraer_taker_bps(account_info)
        return activos, balances, symbols_info, {
            "fee_taker_bps_por_lado": float(fee) if fee is not None else None,
            "fuente_fee": ("binance_account.commissionRates.taker"
                           if fee is not None else "NO_DISPONIBLE"),
        }
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
        print(f"❌ Error al obtener exchange info de Binance: {describir_error(e)}")
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
