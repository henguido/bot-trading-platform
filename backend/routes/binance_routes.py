from fastapi import APIRouter, Depends
from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.config import settings
from backend.state import simulator  # ✅ Usamos el nuevo archivo state.py
from backend.app.auth import get_current_user
from backend.app import models

router = APIRouter()
binance = BinanceConnector()

@router.get("/balance", tags=["Binance"])
def get_binance_balance(current_user: models.User = Depends(get_current_user)):
    """
    Retorna balances con datos ampliados: precio actual, valor USD, precio promedio y ganancia/pérdida.
    """
    balances = binance.get_account_balance()
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

        price_usdt = 1.0 if asset == "USDT" else prices.get(asset + "USDT", None)

        if price_usdt is None:
            continue  # ❗ Salta activos sin precio para evitar errores

        total_usd = round(price_usdt * total, 2)

        # ✅ Obtener precio promedio desde el nuevo simulator global
        avg_price = 0.0
        if asset + "USDT" in simulator.positions:
            avg_price = simulator.positions[asset + "USDT"].average_price

        pnl = 0.0
        if avg_price and price_usdt:
            pnl = round((price_usdt - avg_price) * total, 2)

        summary.append({
            "asset": asset,
            "free": free,
            "locked": locked,
            "price_usdt": round(price_usdt, 4) if price_usdt else None,
            "total_usd": total_usd,
            "average_price": round(avg_price, 4),
            "pnl": pnl
        })

    return {"balances": summary}
