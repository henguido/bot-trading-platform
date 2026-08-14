from fastapi import FastAPI, Body, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from backend.app.auth import get_db, verify_password, create_access_token
from backend.app.database import engine, SessionLocal
from backend.connectors.crypto.binance_connector import BinanceConnector
from backend.connectors.apis.openai_connector import OpenAIConnector
from backend.connectors.stocks.alpaca_connector import AlpacaConnector
from backend.simulation.simulator import Simulator
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
    obtener_ultimo_precio_venta,
    cargar_contexto_usuario,
    ejecutar_y_registrar_compra,
    ejecutar_y_registrar_venta,
)
from backend.routes import transacciones_routes, binance_routes
from backend.connectors.apis.real_trading_connector import RealTradingConnector
from backend.app.auth import get_current_user
from backend.app.services.ordenes import Lado, es_cantidad_valida, validar_peticion_venta
from backend.risk.estado import calcular_estado_riesgo, calcular_estado_riesgo_paper
from backend.risk.motor import MotorRiesgo, PropuestaOperacion
import time
import threading, pytz, traceback

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

# ─────────────────────────────────────────────────────────────────────────────
# P0-4 / P0-5
#
# Aqui habia un bloque que leia el estado del portafolio UNA SOLA VEZ, al
# importar el modulo, y lo dejaba en las globales `usuario_id`, `estado`,
# `ultimos_movimientos` y `ultimos_precios_venta`. Producia dos fallos:
#
#   P0-4: si no habia usuarios al arrancar, tres de esas globales no llegaban
#         a definirse. Si alguien se registraba despues, el bucle lanzaba
#         NameError en cada iteracion.
#   P0-5: si si habia usuario, el precio promedio quedaba congelado en el valor
#         del arranque para siempre, asi que el bot nunca conocia su coste base.
#
# El bloque no se ha reinicializado: se ha SUPRIMIDO. El estado persistente
# vive ahora exclusivamente en la base de datos y se lee fresco en cada
# iteracion mediante cargar_contexto_usuario(). Tampoco se siembran las
# posiciones del Simulator desde la BD: el Simulator es un libro en memoria
# para PAPER, no una fuente de estado persistente.
# ─────────────────────────────────────────────────────────────────────────────


def priorizar_activos_por_importancia(activos):
    return [a for a in activos if a["position_quantity"] > 0]

motor_riesgo = MotorRiesgo()


def capital_disponible_actual(usdt_disponible):
    """
    Capital operable, en USDT. En LIVE manda el saldo real del exchange; en
    PAPER, el capital del libro en memoria. Nunca se mezclan.
    """
    if settings.MODO_REAL:
        return float(usdt_disponible or 0.0)
    return float(simulator.capital_usd)


def registrar_rechazo_riesgo(veredicto, *, sentimiento, noticias):
    """
    Deja constancia de una operacion vetada por el motor.

    Se reutiliza DecisionAudit, que ya existe: no hace falta migracion. Se
    guarda con quantity=0 y action='RECHAZADA_RIESGO' para que jamas pueda
    confundirse con una transaccion ejecutada.
    """
    try:
        with SessionLocal() as db:
            guardar_auditoria_decision(
                db,
                symbol=veredicto.symbol,
                action="RECHAZADA_RIESGO",
                quantity=0.0,
                price=0.0,
                sentimiento=sentimiento,
                noticias=noticias,
                risk_score=0.0,
                decision_gpt={
                    "resultado": "RECHAZADA_POR_RIESGO",
                    "side": veredicto.side.value,
                    "motivo": veredicto.motivo,
                    "limite_violado": veredicto.limite_violado,
                    "requested_by_model": veredicto.requested_by_model,
                    "capital_available": veredicto.capital_available,
                    "current_exposure": veredicto.current_exposure,
                    "exposure_symbol": veredicto.exposure_symbol,
                    "daily_realized_pnl": veredicto.daily_realized_pnl,
                    "kill_switch_activo": veredicto.kill_switch_activo,
                    "reglas_aplicadas": list(veredicto.reglas_aplicadas),
                },
            )
    except Exception as e:
        print(f"⚠️ No se pudo auditar el rechazo de riesgo: {type(e).__name__}: {e}")


def posicion_disponible(symbol, saldo_real_dict):
    """
    Cantidad de ACTIVO BASE disponible para vender, en las unidades correctas.

    En LIVE manda el saldo real del exchange; en PAPER, el libro en memoria del
    simulador. Nunca se mezclan: una posicion simulada no autoriza una venta
    real, ni al reves.
    """
    if settings.MODO_REAL:
        return float(saldo_real_dict.get(symbol.replace("USDT", ""), 0.0))
    posicion = simulator.positions.get(symbol)
    return float(posicion.quantity) if posicion else 0.0


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
    # Los filtros del exchange se piden de forma perezosa: si todavia no hay
    # usuario no hace falta contactar con Binance.
    filters_dict = None

    while True:
        try:
            # ── Contexto FRESCO en cada iteracion (P0-5) ──────────────────
            contexto = cargar_contexto_usuario()

            # La ausencia de usuario es un estado normal, no un error (P0-4).
            # El bot espera y se reincorpora solo en cuanto alguien se registre.
            if contexto.usuario_id is None:
                print("[BOT] Sin usuarios registrados todavia. "
                      "Esperando a que alguien complete /signup...")
                time.sleep(settings.WAIT_TIME)
                continue

            if filters_dict is None:
                binance.init_client()
                exchange_info = binance.client.get_exchange_info()
                filters_dict = {s["symbol"]: s["filters"] for s in exchange_info["symbols"]}

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
                                models.Portfolio.usuario_id == contexto.usuario_id,
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

                # Coste base leido de la BD en ESTA iteracion, no en el arranque.
                avg_price = contexto.estado.get(symbol, {}).get("precio_promedio", 0.0)
                last_movement = contexto.ultimos_movimientos.get(symbol)
                last_sell_price = contexto.ultimos_precios_venta.get(symbol)

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
                # GPT devuelve la cantidad en ACTIVO BASE (BTC en BTCUSDT).
                base_quantity = resultado.get("quantity", 0.0)
                risk_score = resultado.get("risk_score", 0.0)

                if not symbol:
                    continue

                precio_actual = precios_actuales.get(symbol)
                if precio_actual is None:
                    print(f"⚠️ Precio no disponible para {symbol}. Se omite.")
                    continue

                if decision in ("COMPRAR", "VENDER"):
                    lado = Lado.COMPRA if decision == "COMPRAR" else Lado.VENTA

                    # Estado de riesgo FRESCO por decision: la exposicion puede
                    # cambiar dentro del propio ciclo si se ejecutan varias
                    # ordenes. Se reconstruye desde operaciones confirmadas.
                    estado_riesgo = (
                        calcular_estado_riesgo(contexto.usuario_id)
                        if settings.MODO_REAL
                        else calcular_estado_riesgo_paper(simulator)
                    )

                    # base_quantity viene del modelo y NO ES AUTORITATIVA para
                    # el tamano: el motor lo recalcula desde cero.
                    propuesta = PropuestaOperacion(
                        symbol=symbol, side=lado, precio=precio_actual,
                        base_quantity_modelo=base_quantity,
                        min_notional=get_min_notional(symbol, filters_dict),
                    )
                    veredicto = motor_riesgo.evaluar(
                        propuesta,
                        capital_disponible=capital_disponible_actual(usdt_disponible),
                        estado=estado_riesgo,
                    )

                    if not veredicto.aprobado:
                        print(f"⛔ {veredicto}")
                        registrar_rechazo_riesgo(veredicto, sentimiento=sentimiento,
                                                 noticias=noticias_str)
                        continue

                    if lado is Lado.COMPRA:
                        if settings.MODO_REAL:
                            # LIVE: persiste solo tras confirmacion del broker.
                            ejecucion = ejecutar_y_registrar_compra(
                                trader=real_trader, usuario_id=contexto.usuario_id,
                                symbol=symbol,
                                quote_amount=veredicto.approved_quote_amount,
                                precio_referencia=precio_actual,
                            )
                            if not ejecucion.success:
                                print(f"⛔ COMPRA {symbol} NO registrada: {ejecucion}")
                        else:
                            # PAPER: solo el libro en memoria. Nunca toca la BD.
                            simulator.simulate_trade(symbol, "COMPRAR", precio_actual,
                                                     veredicto.approved_base_quantity)
                    else:
                        if settings.MODO_REAL:
                            ejecucion = ejecutar_y_registrar_venta(
                                trader=real_trader, usuario_id=contexto.usuario_id,
                                symbol=symbol,
                                base_quantity=veredicto.approved_base_quantity,
                                precio_referencia=precio_actual,
                            )
                            if not ejecucion.success:
                                print(f"⛔ VENTA {symbol} NO registrada: {ejecucion}")
                        else:
                            simulator.simulate_trade(symbol, "VENDER", precio_actual,
                                                     veredicto.approved_base_quantity)

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
                    # Cantidad DECIDIDA por GPT, en activo base. Es la intencion,
                    # no una ejecucion: la auditoria registra decisiones.
                    "quantity": base_quantity,
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
                            quantity=base_quantity,
                            price=precio_actual,
                            sentimiento=sentimiento,
                            noticias=noticias_str,
                            risk_score=risk_score,
                            decision_gpt=explicacion_gpt
                        )
                except Exception as e:
                    print(f"⚠️ Error guardando auditoría GPT: {e}")


        except Exception as e:
            # Con solo str(e) el NameError de P0-4 fue invisible 15 meses.
            print(f"❌ Error inesperado en ciclo de trading: {type(e).__name__}: {e}")
            traceback.print_exc()
            time.sleep(settings.WAIT_TIME)
            ciclo += 1


# El hilo arranca SIEMPRE. Si aun no hay usuarios, el propio bucle lo trata
# como estado normal y espera; ya no hace falta relanzarlo desde /signup.
threading.Thread(target=trading_loop, daemon=True).start()

# Rutas
@app.get("/api/historial")
def get_historial(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
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
def resumen_portafolio(current_user: models.User = Depends(get_current_user)):
    balances = binance.get_account_balance()
    resumen = []
    ganancia_total = 0.0

    # Coste base leido de la BD, de la MISMA fuente que usa el bot, para que
    # el resumen y las decisiones nunca discrepen.
    # NOTA: el balance de Binance es de una unica cuenta compartida, asi que
    # este endpoint es inherentemente monousuario. La separacion por usuario
    # sigue pendiente (ver riesgo A-4 de la auditoria).
    estado = cargar_contexto_usuario().estado

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

    # Ya no se arranca ningun hilo aqui. El bucle corre siempre y detecta al
    # nuevo usuario por si mismo en la siguiente iteracion, leyendo la BD.
    # Antes, este arranque tardio dejaba sin definir estado/ultimos_* y el
    # bucle moria con NameError en cada ciclo (P0-4). Ademas, dos altas
    # simultaneas podian lanzar dos hilos de trading a la vez.
    return {"mensaje": "Usuario creado correctamente", "usuario_id": nuevo_usuario.id}

