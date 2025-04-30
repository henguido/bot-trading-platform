from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app import models, schemas, auth
from app.database import engine, SessionLocal
from app.auth import get_password_hash, verify_password, create_access_token, get_db
from binance_api.binance_connector import BinanceConnector
from openai_api.openai_connector import OpenAIConnector
from simulation.simulator import Simulator
from config import settings
import threading, time, datetime

# Inicializar la base de datos
models.Base.metadata.create_all(bind=engine)

# Crear instancia FastAPI
app = FastAPI(
    title="BOT Trading Platform",
    description="API de trading con login/signup",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cámbialo por el dominio de producción en frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================
# Instancias globales
# ========================
binance = BinanceConnector()
openai = OpenAIConnector()
simulator = Simulator()

# ========================
# BOT EN HILO DE FONDO
# ========================
def trading_loop():
    ciclo = 0
    while True:
        print(f"\n⏳ Ciclo: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        precios = binance.get_current_prices(settings.CRYPTO_LIST)
        simulator.latest_decisions = {}  # Reiniciar decisiones

        for i, symbol in enumerate(settings.CRYPTO_LIST):
            precio_actual = precios.get(symbol)
            if not precio_actual:
                continue

            market_data = {"precio": precio_actual}
            decision = openai.analyze_market(symbol, market_data)
            simulator.simulate_trade(symbol, decision, precio_actual)
            simulator.latest_decisions[symbol] = decision

            if i < len(settings.CRYPTO_LIST) - 1:
                time.sleep(20)

        ciclo += 1
        if ciclo % 12 == 0:
            simulator.show_summary(precios)
        time.sleep(settings.WAIT_TIME)

threading.Thread(target=trading_loop, daemon=True).start()

# ========================
# Rutas existentes
# ========================
@app.get("/")
def read_root():
    return {"message": "Bienvenido a BOT Trading Platform"}

@app.post("/signup", response_model=schemas.Token)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El correo ya está registrado.")
    hashed_pw = get_password_hash(user.password)
    new_user = models.User(nombre=user.nombre, email=user.email, password_hash=hashed_pw)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    token = create_access_token(data={"sub": new_user.email})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/login", response_model=schemas.Token)
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    token = create_access_token(data={"sub": db_user.email})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/balance")
def get_balance():
    try:
        balance_info = binance.client.get_asset_balance(asset="USDT")
        return {"usdt": balance_info.get("free")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener balance: {e}")

# ========================
# NUEVOS ENDPOINTS API BOT
# ========================
@app.get("/api/saldo")
def get_saldo():
    return {"capital_actual": simulator.capital}

@app.get("/api/historial")
def get_historial():
    return simulator.history

@app.get("/api/estado")
def get_estado():
    return simulator.latest_decisions if hasattr(simulator, "latest_decisions") else {}
