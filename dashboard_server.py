# dashboard_server.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Aquí importas donde guardes la información del bot
from bot_data import bot_status

app = FastAPI(title="Trading Bot Dashboard API", version="1.0.0")

# 🔥 Permitir acceso desde cualquier origen (CORS abierto mientras desarrollamos)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoint principal
@app.get("/status")
async def status_general():
    return {
        "capital_usdt": bot_status["capital_usdt"],
        "modo_real": bot_status["modo_real"],
        "sentimiento": bot_status["sentimiento"],
        "ultima_accion": bot_status["ultima_accion"]
    }

@app.get("/news")
async def noticias():
    return {
        "noticias": bot_status["noticias_recientes"]
    }

@app.get("/market")
async def mercado():
    return {
        "cripto_precios": bot_status["market_prices"]
    }

@app.get("/last-actions")
async def acciones():
    return {
        "acciones_recientes": bot_status["acciones_recientes"]
    }

# Ejecutar servidor si corres este archivo directamente
if __name__ == "__main__":
    uvicorn.run("dashboard_server:app", host="0.0.0.0", port=8000, reload=True)
