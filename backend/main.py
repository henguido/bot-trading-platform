from fastapi import FastAPI, Body, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from backend.app.auth import get_db, verify_password, create_access_token
from backend.app.database import engine, SessionLocal
from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.connectors.apis.openai_connector import OpenAIConnector
from backend.connectors.stocks.alpaca_connector import AlpacaConnector
from backend.simulation.simulator import Simulator, CryptoPosition
from backend.config import settings
from backend.app.schemas import UserCreate
from datetime import datetime
from backend.app import models, schemas
from backend.app.auth import get_password_hash
from backend.connectors.apis.news_connector import NewsConnector
from backend.utils.asset_collector import get_available_assets, get_market_pairs
from backend.app.services.real_trading import obtener_ultimo_movimiento
from backend.utils.time_utils import mercado_ny_abierto
from backend.app.services.real_trading import (
    cargar_estado_portafolio,
    guardar_transaccion_real,
    guardar_auditoria_decision,
    obtener_ultimo_precio_venta 
)
from backend.routes import transacciones_routes, binance_routes
from backend.connectors.apis.real_trading_connector import RealTradingConnector
from backend.app.auth import get_current_user
import time
import threading, pytz

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="BOT Trading Platform",
    description="API de trading con login/signup",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.include_router(transacciones_routes.router)
app.include_router(binance_routes.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instancias globales
binance = BinanceConnector()
openai = OpenAIConnector()
simulator = Simulator()
alpaca = AlpacaConnector()
news_connector = NewsConnector()
real_trader = RealTradingConnector()

# Cargar estado del primer usuario registrado (asumido como activo)
with SessionLocal() as db:
    primer_usuario = db.query(models.User).order_by(models.User.id.asc()).first()
    if primer_usuario:
        usuario_id = primer_usuario.id
        estado = cargar_estado_portafolio(db, usuario_id)
        ultimos_movimientos = obtener_ultimo_movimiento(db, usuario_id)
        ultimos_precios_venta = obtener_ultimo_precio_venta(db, usuario_id)
        for symbol, info in estado.items():
            if symbol not in simulator.positions:
                simulator.positions[symbol] = CryptoPosition()
            simulator.positions[symbol].quantity = info["cantidad"]
            simulator.positions[symbol].average_price = info["precio_promedio"]
    else:
        print("⚠️ No hay usuarios registrados. Solo disponible el endpoint /signup.")
        usuario_id = None


def priorizar_activos_por_importancia(activos):
    return [a for a in activos if a["position_quantity"] > 0]

def get_min_notional(symbol, filters_dict):
    symbol_filters = filters_dict.get(symbol)
    if not symbol_filters:
        return 1.0  # Valor por defecto

    for f in symbol_filters:
        if f["filterType"] in ["NOTIONAL", "MIN_NOTIONAL"]:
            return float(f.get("minNotional", 1.0))
    return 1.0

# Lógica principal del bot
def trading_loop():
    ciclo = 0
    EVALUAR_CADA_N_CICLOS = 2  # Puedes ajustar este valor
    noticias_cache = None
    timestamp_cache = None
    binance.init_client()
    exchange_info = binance.client.get_exchange_info()
    filters_dict = {s["symbol"]: s["filters"] for s in exchange_info["symbols"]}

    while True:
        try:
            ahora = datetime.now()
            minuto_actual = ahora.minute

            print(f"\n⏳ Ciclo: {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
            simulator.latest_decisions = {}
            precios_actuales = {}

            # Cachear noticias por 1 hora para evitar exceso de llamadas
            if not noticias_cache or (ahora - timestamp_cache).total_seconds() > 3600:
                noticias = news_connector.obtener_noticias_combinadas(6)
                noticias_cache = noticias if noticias else []
                timestamp_cache = ahora
            else:
                noticias = noticias_cache

            textos = noticias if noticias else []
            noticias_str = "\n".join(textos) if textos else "No hay noticias disponibles"
            sentimiento = "NO DISPONIBLE"
            print(f"🧑‍🤖 Sentimiento del mercado: {sentimiento}")

            try:
                assets_disponibles, balances_reales, symbols_info = get_available_assets()
            except Exception as e:
                print(f"❌ Error al inicializar Binance o traer datos: {e}")
                time.sleep(settings.WAIT_TIME)
                ciclo += 1
                continue

            if not assets_disponibles:
                print("⚠️ No se encontraron activos disponibles.")
                time.sleep(settings.WAIT_TIME)
                ciclo += 1
                continue

            print("🔢 Total activos disponibles:", len(assets_disponibles))
            for a in assets_disponibles[:10]:
                print(" -", a["symbol"], "| tipo:", a["type"])

            activos_crypto = [a for a in assets_disponibles if a["type"] == "crypto"]
            activos_forex = [a for a in assets_disponibles if a["type"] == "forex"]
            activos_stocks = [a for a in assets_disponibles if a["type"] == "stock" and mercado_ny_abierto()]

            ejecutar_crypto = (ciclo % EVALUAR_CADA_N_CICLOS) == 0
            ejecutar_forex = minuto_actual % 5 == 0
            ejecutar_stock = minuto_actual % 15 == 0 and mercado_ny_abierto()

            activos_evaluar = []
            if ejecutar_crypto:
                activos_evaluar += activos_crypto

            if not activos_evaluar:
                print("⌛ Esperando el siguiente ciclo válido...")
                time.sleep(settings.WAIT_TIME)
                ciclo += 1
                continue

            # Este bloque fue movido hacia arriba

            ciclo += 1  # Aquí avanzamos el ciclo después de haber intentado ejecutar

            # Crear diccionario de saldos reales para acceso rápido
            saldo_real_dict = {
                b["asset"]: float(b["free"]) + float(b["locked"])
                for b in balances_reales
            }

            # 🧹 Limpiar posiciones simuladas y base de datos que ya no tienen saldo real
            with SessionLocal() as db_limpieza:
                for symbol, pos in list(simulator.positions.items()):
                    base_asset = symbol.replace("USDT", "")
                    saldo_real = saldo_real_dict.get(base_asset, 0.0)
                    if saldo_real == 0:
                        if pos.quantity > 0 or pos.average_price > 0:
                            print(f"🧹 Limpiando simulador y BD: sin saldo real para {symbol}, reseteando posición")
                            pos.quantity = 0.0
                            pos.average_price = 0.0

                            # Limpiar también en la base de datos
                            portafolio = db_limpieza.query(models.Portfolio).filter(
                                models.Portfolio.usuario_id == usuario_id,
                                models.Portfolio.nombre == symbol
                            ).first()

                            if portafolio:
                                portafolio.balance_inicial = 0.0
                                db_limpieza.commit()

            activos_para_gpt = []
            symbols_a_precio = [a["symbol"] for a in activos_evaluar if a["type"] == "crypto"]
            precios_actuales = binance.get_multiple_prices(symbols_a_precio)

            for asset in activos_evaluar:
                symbol = asset["symbol"]
                tipo = asset["type"]

                try:
                    precio = precios_actuales.get(symbol) if tipo == "crypto" else alpaca.get_current_price(symbol)
                except Exception as e:
                    print(f"❌ Error obteniendo precio de {symbol}: {e}")
                    continue

                if not precio:
                    continue

                precios_actuales[symbol] = precio

                # Calcular cantidad real detectada
                base_asset = symbol.replace("USDT", "")
                saldo_detectado = saldo_real_dict.get(base_asset, 0.0)

                # Obtener posición en el simulador si existe
                position_sim = simulator.positions.get(symbol)
                posicion_qty = position_sim.quantity if position_sim else 0.0
                balance_detected = saldo_detectado > 0
                position_detected = posicion_qty > 0

                # Si no hay saldo, usar cantidad en simulador (si existe)
                qty = saldo_detectado if saldo_detectado > 0 else posicion_qty

                avg_price = estado.get(symbol, {}).get("precio_promedio", 0.0)
                last_movement = ultimos_movimientos.get(symbol)
                last_sell_price = ultimos_precios_venta.get(symbol)

                activos_para_gpt.append({
                    "symbol": symbol,
                    "price": precio,
                    "position_quantity": qty,
                    "average_price": avg_price,
                    "last_movement": last_movement,
                    "last_sell_price": last_sell_price,
                    "_balance_detected": balance_detected,
                    "_position_detected": position_detected
                })

            activos_para_gpt.sort(key=lambda a: not (a.get("balance_detected") or a.get("position_detected")))

            print(f"🎯 Enviando {len(activos_para_gpt)} activos a GPT para análisis")

            if not activos_para_gpt:
                print("⚠️ No hay activos para analizar con GPT")
                time.sleep(settings.WAIT_TIME)
                continue

            # Obtener portafolio y pares
            portafolio_real = [
                {
                    "moneda": b["asset"],
                    "cantidad": round(float(b["free"]) + float(b["locked"]), 6)
                }
                for b in balances_reales
                if float(b["free"]) + float(b["locked"]) > 0
            ]

            market_pairs = get_market_pairs(symbols_info)
            usdt_disponible = next((b["cantidad"] for b in portafolio_real if b["moneda"] == "USDT"), 0.0)

            # Enviar a análisis
            # 🔍 Identificar activos relevantes
            activos_relevantes = {
                a["symbol"].replace("USDT", "") for a in activos_para_gpt
                if a["position_quantity"] > 0 or a.get("balance_detected")
            }

            # 🧹 Filtrar solo pares que involucren activos relevantes
            market_pairs_filtrados = [
                p for p in market_pairs
                if any(activo in p["pair"] for activo in activos_relevantes)
            ]
            # Limpiar campos internos que no se deben enviar a GPT
            for a in activos_para_gpt:
                a.pop("_balance_detected", None)
                a.pop("_position_detected", None)
            resultados, explicacion_gpt = openai.analyze_multiple_assets(
                activos_para_gpt,
                usdt_disponible,
                sentimiento,
                noticias_str,
                portafolio_real,
                market_pairs_filtrados
            )

            if not resultados:
                print("⚠️ GPT no devolvió JSON válido. Respuesta completa:")
                print(explicacion_gpt)
                simulator.audit_log.append({
                    "symbol": "GPT",
                    "action": "EXPLICACION",
                    "price": 0.0,
                    "quantity": 0.0,
                    "timestamp": ahora.astimezone(pytz.timezone("America/Costa_Rica")).strftime("%Y-%m-%d %H:%M:%S"),
                    "context": {
                        "sentimiento": sentimiento,
                        "noticias": noticias_str,
                        "risk_score": 0.0
                    },
                    "decision_gpt": explicacion_gpt,
                    "risk_score": 0.0
                })
                continue
            print("🧠 Resultados GPT:", resultados)

            for resultado in resultados:
                symbol = resultado.get("symbol")
                decision = resultado.get("decision", "ESPERAR")
                quantity = resultado.get("quantity", 0.0)
                risk_score = resultado.get("risk_score", 0.0)

                if not symbol:
                    continue

                precio_actual = precios_actuales.get(symbol)
                if precio_actual is None:
                    print(f"⚠️ Precio no disponible para {symbol}. Se omite.")
                    continue

                if decision == "COMPRAR":
                    print(f"🚀 COMPRA de {symbol} a {precio_actual}")
                    
                    notional = precio_actual * quantity
                    min_notional = get_min_notional(symbol, filters_dict)

                    if notional < min_notional:
                        print(f"⚠️ Orden ignorada: NOTIONAL ${notional:.6f} menor a mínimo requerido ${min_notional:.2f} para {symbol}")
                        continue

                    if settings.MODO_REAL:
                        try:
                            real_trader.comprar(symbol, cantidad_usdt=precio_actual * quantity)
                            simulator.simulate_trade(symbol, "COMPRAR", precio_actual, quantity)
                            with SessionLocal() as db:
                                guardar_transaccion_real(db, usuario_id=usuario_id, symbol=symbol, action="COMPRAR", price=precio_actual, quantity=quantity)
                        except Exception as e:
                            print(f"⚠️ Error en compra real: {e}")
                    else:
                        simulator.simulate_trade(symbol, "COMPRAR", precio_actual, quantity)

                elif decision == "VENDER":
                    print(f"🔻 VENTA de {symbol} a {precio_actual}")
                    if settings.MODO_REAL:
                        try:
                            real_trader.vender(symbol, cantidad_usdt=precio_actual * quantity)
                            simulator.simulate_trade(symbol, "VENDER", precio_actual, quantity)
                            with SessionLocal() as db:
                                guardar_transaccion_real(db, usuario_id=usuario_id, symbol=symbol, action="VENDER", price=precio_actual, quantity=quantity)
                        except Exception as e:
                            print(f"⚠️ Error en venta real: {e}")
                    else:
                        simulator.simulate_trade(symbol, "VENDER", precio_actual, quantity)

                elif decision == "ESPERAR":
                    # En modo real, también considerar si hay saldo real
                    base_asset = symbol.replace("USDT", "")
                    saldo_real = saldo_real_dict.get(base_asset, 0.0)
                    simulador_pos = simulator.positions.get(symbol)
                    qty_simulador = simulador_pos.quantity if simulador_pos else 0.0

                    if qty_simulador <= 0 and saldo_real <= 0:
                        print(f"⛔ ESPERAR ignorado: no hay posición ni saldo real para {symbol}")
                        continue

                simulator.latest_decisions[symbol] = decision
                simulator.audit_log.append({
                    "symbol": symbol,
                    "action": decision,
                    "price": precio_actual,
                    "quantity": quantity,
                    "timestamp": ahora.astimezone(pytz.timezone("America/Costa_Rica")).strftime("%Y-%m-%d %H:%M:%S"),

                    "context": {
                        "sentimiento": sentimiento,
                        "noticias": noticias_str,
                        "risk_score": risk_score
                    },
                    "decision_gpt": explicacion_gpt,
                    "risk_score": risk_score
                })

                try:
                    with SessionLocal() as db:
                        guardar_auditoria_decision(
                            db,
                            symbol=symbol,
                            action=decision,
                            quantity=quantity,
                            price=precio_actual,
                            sentimiento=sentimiento,
                            noticias=noticias_str,
                            risk_score=risk_score,
                            decision_gpt=explicacion_gpt
                        )
                except Exception as e:
                    print(f"⚠️ Error guardando auditoría GPT: {e}")


        except Exception as e:
            print(f"❌ Error inesperado en ciclo de trading: {e}")
            time.sleep(settings.WAIT_TIME)
            ciclo += 1

if usuario_id is not None:
    threading.Thread(target=trading_loop, daemon=True).start()
else:
    print("⏳ Bot desactivado porque no hay usuario registrado.")

# Rutas
@app.get("/api/historial")
def get_historial(db: Session = Depends(get_db)):
    auditorias = db.query(models.DecisionAudit).order_by(models.DecisionAudit.timestamp.desc()).all()
    historial = []

    for a in auditorias:
        # Ignorar ESPERAR si no hay cantidad
        if a.action == "ESPERAR" and (not a.quantity or a.quantity == 0):
            continue

        historial.append({
            "symbol": a.symbol,
            "action": a.action,
            "quantity": a.quantity,
            "price": a.price,
            "timestamp": a.timestamp.astimezone(
                pytz.timezone("America/Costa_Rica")
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "context": {
                "sentimiento": a.sentimiento,
                "noticias": a.noticias,
                "risk_score": a.risk_score
            },
            "decision_gpt": a.decision_gpt,
            "risk_score": a.risk_score
        })

    return historial

@app.get("/api/resumen")
def resumen_portafolio():
    balances = binance.get_account_balance()
    resumen = []
    ganancia_total = 0.0

    # Obtener precios promedio desde la BD
    with SessionLocal() as db:
        estado = cargar_estado_portafolio(db, usuario_id=usuario_id)

    for b in balances:
        asset = b["asset"]
        total = float(b["free"]) + float(b["locked"])

        if total == 0:
            continue

        # Corrección: manejo especial para USDT
        if asset == "USDT":
            precio_actual = 1.0
            symbol = "USDT"
        else:
            symbol = asset + "USDT"
            try:
                precio_actual = binance.get_current_price(symbol)
            except Exception as e:
                print(f"❌ No se pudo obtener precio para {symbol}: {e}")
                continue

        # Obtener precio promedio desde el estado
        average_price = estado.get(symbol, {}).get("precio_promedio", 0.0)
        pnl = (precio_actual - average_price) * total if average_price else 0.0
        valor_actual = round(total * precio_actual, 2)

        resumen.append({
            "symbol": symbol,
            "cantidad": round(total, 6),
            "precio_actual": round(precio_actual, 4),
            "valor_actual": valor_actual,
            "average_price": round(average_price, 4),
            "pnl": round(pnl, 2)
        })

        ganancia_total += valor_actual

    # Mostrar USDT primero
    resumen.sort(key=lambda x: 0 if x["symbol"] == "USDT" else 1)

    return {
        "resumen": resumen,
        "ganancia_total": round(ganancia_total, 2)
    }

@app.post("/login")
def login(form_data: dict = Body(...), db: Session = Depends(get_db)):
    email = form_data.get("email")
    password = form_data.get("password")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    access_token = create_access_token(data={"sub": user.email})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "nombre": user.nombre  # ✅ esto asume que ya tienes el campo `nombre` en el modelo
    }

@app.post("/signup")
def signup(form_data: UserCreate, db: Session = Depends(get_db)):
    global usuario_id  # necesario para modificar la variable global

    if db.query(models.User).filter(models.User.email == form_data.email).first():
        raise HTTPException(status_code=400, detail="El usuario ya existe")

    hashed_password = get_password_hash(form_data.password)
    nuevo_usuario = models.User(
        nombre=form_data.nombre,
        email=form_data.email,
        password_hash=hashed_password
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)

    # ✅ Activar ciclo si no estaba corriendo aún
    if usuario_id is None:
        usuario_id = nuevo_usuario.id
        print(f"🟢 Primer usuario registrado. Iniciando ciclo de trading para usuario_id={usuario_id}...")
        threading.Thread(target=trading_loop, daemon=True).start()

    return {"mensaje": "Usuario creado correctamente", "usuario_id": nuevo_usuario.id}

