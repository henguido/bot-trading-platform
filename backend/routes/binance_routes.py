from fastapi import APIRouter, Depends
from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.config import settings
from backend.app.auth import get_current_user
from backend.app import models
from backend.finanzas import campos, pnl_no_realizado, precio_medio_de
from backend.release_readiness import evaluar as evaluar_readiness, resumen_publico
from backend.economia.integracion_05e import PROFITABILITY_GATE_05E_ENABLED
from backend.esquema import estado_esquema

router = APIRouter()
binance = BinanceConnector()


def _coste_base_del_modo():
    """
    Precios medios de la fuente que corresponde al modo activo.

    LIVE  -> transacciones reconciliadas en la base de datos.
    PAPER -> no hay coste base publicable aqui: este endpoint expone el saldo
             REAL del exchange, que no pertenece al libro simulado. Mezclarlos
             produciria un P&L sin sentido, asi que se declara NO_DISPONIBLE.

    Antes se leia backend.state.simulator, una instancia que NADIE escribia
    nunca: average_price y pnl salian siempre 0.0 presentados como calculados.
    """
    if not settings.MODO_REAL:
        return {}, ("en PAPER el saldo del exchange no tiene coste base en el "
                    "libro simulado")
    from backend.app.services.real_trading import cargar_contexto_usuario
    return cargar_contexto_usuario().estado, None


@router.get("/balance", tags=["Binance"])
def get_binance_balance(current_user: models.User = Depends(get_current_user)):
    """
    Saldos REALES del exchange, con precio actual y valor en USD.

    El precio medio y el P&L solo se rellenan si existe una fuente fiable para
    el modo activo. Si no la hay, se devuelve null con estado NO_DISPONIBLE:
    un dato desconocido nunca se presenta como cero.
    """
    balances = binance.get_account_balance()
    estado, motivo_sin_coste = _coste_base_del_modo()
    summary = []

    symbols = [b["asset"] + "USDT" for b in balances if b["asset"] != "USDT"]
    prices = binance.get_current_prices(symbols)

    for b in balances:
        asset = b["asset"]
        free = float(b["free"])
        locked = float(b["locked"])
        total = free + locked

        if total == 0:
            continue

        symbol = "USDT" if asset == "USDT" else asset + "USDT"
        price_usdt = 1.0 if asset == "USDT" else prices.get(symbol)

        medio = precio_medio_de(estado, symbol)
        motivo = motivo_sin_coste or ("sin coste base registrado para "
                                      f"{symbol}" if medio is None else None)
        pnl = pnl_no_realizado(price_usdt, medio, total)

        fila = {"asset": asset, "free": free, "locked": locked,
                "symbol": symbol, "modo": settings.TRADING_MODE}
        fila.update(campos("price_usdt", price_usdt, redondeo=6,
                           motivo="el exchange no devolvio precio"))
        fila.update(campos("total_usd",
                           (price_usdt * total) if price_usdt is not None else None,
                           redondeo=2, motivo="sin precio actual"))
        fila.update(campos("average_price", medio, redondeo=6, motivo=motivo))
        fila.update(campos("pnl", pnl, redondeo=2, motivo=motivo))
        summary.append(fila)

    return {"modo": settings.TRADING_MODE, "balances": summary}


@router.get("/api/readiness", tags=["Sistema"])
def get_paper_readiness(current_user: models.User = Depends(get_current_user)):
    """Resumen seguro de readiness PAPER; no hace red ni expone checks sensibles."""
    _ = current_user
    resultado = evaluar_readiness(
        settings,
        estado_esquema(),
        profitability_gate_enabled=PROFITABILITY_GATE_05E_ENABLED,
    )
    return resumen_publico(resultado)
