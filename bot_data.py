# bot_data.py

# Variables que el bot actualiza constantemente
bot_status = {
    "capital_usdt": 1000,
    "modo_real": False,
    "sentimiento": "NEUTRAL",
    "ultima_accion": "ESPERAR",
    "noticias_recientes": [
        "Noticias cargando..."
    ],
    "market_prices": {
        "BTCUSDT": 0.0,
        "ETHUSDT": 0.0,
        "SOLUSDT": 0.0
    },
    "acciones_recientes": [
        {"symbol": "BTCUSDT", "accion": "ESPERAR", "precio": 0.0, "fecha_hora": ""}
    ]
}
