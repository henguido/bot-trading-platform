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
from backend.finanzas import campos, pnl_no_realizado, precio_medio_de
from backend import scanner
from backend.economia.profundidad import obtener_order_book
from backend.risk import elegibilidad
from backend.risk.motor import MotorRiesgo, PropuestaOperacion
from backend.portafolio.carteras import (
    construir_cartera,
    contexto_posicion_para_llm,
    portafolio_para_llm,
)
from backend.coordinador import CoordinadorTrading, candado_por_defecto
from backend.reconciliacion import reconciliar_pendientes
from backend.telemetria_http import MedidorCicloHttp, nuevo_ciclo_id
from contextlib import asynccontextmanager
import sys
import time
import pytz, traceback

# ─────────────────────────────────────────────────────────────────────────────
# P0-16 · ALEMBIC ES LA UNICA AUTORIDAD DEL ESQUEMA
#
# Aqui habia un models.Base.metadata.create_all(bind=engine) que se ejecutaba
# AL IMPORTAR el modulo. Con DATABASE_URL apuntando a produccion, un simple
# `import backend.main` (o arrancar uvicorn) abria conexion contra Render y
# habria creado alli las tablas `ordenes` y `fills` FUERA de Alembic: la base
# habria quedado con el esquema nuevo pero sin fila en alembic_version, y el
# procedimiento `stamp 0001_baseline` ya no encajaria.
#
# El codigo de aplicacion NO modifica el esquema. Migrar es una operacion
# explicita de despliegue:  alembic upgrade head
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app):
    """
    Unico punto de arranque y parada del bucle de trading (P0-13).

    `coordinador` se resuelve como global EN TIEMPO DE EJECUCION, no al definir
    esta funcion: se instancia mas abajo, cuando trading_loop ya existe.
    """
    coordinador.iniciar()          # no arranca si otro proceso es lider
    try:
        yield
    finally:
        coordinador.detener()


app = FastAPI(
    title="BOT Trading Platform",
    description="API de trading con login/signup",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
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


# ─────────────────────────────────────────────────────────────────────────────
# ROBUSTEZ · INFORMAR DE UN ERROR NO PUEDE MATAR EL BUCLE
#
# Hallazgo de la validacion funcional de BOT 2.0-02A. El manejador de errores
# del ciclo hacia directamente:
#
#     print(f"❌ Error inesperado en ciclo de trading: ...")
#     traceback.print_exc()
#
# Con un stdout que no sabe codificar el emoji -cp1252, que es lo que se
# obtiene en cuanto la salida se redirige a un fichero o a un pipe- el propio
# print lanzaba UnicodeEncodeError DENTRO del except y mataba el hilo de
# trading. Observado: el bot murio en el primer error en lugar de esperar y
# reintentar.
#
# No cambia NADA de lo que se informa, ni el scheduling, ni las decisiones.
# Solo garantiza que informar no pueda ser lo que tumbe el bot.
# ─────────────────────────────────────────────────────────────────────────────
def imprimir_resistente(texto, destino=None):
    """
    Imprime `texto` sin que un stdout limitado pueda hacer fallar al llamador.

    Si la codificacion del destino no admite algun caracter, se reintenta en
    ASCII con escapes: `backslashreplace` conserva el caracter perdido de forma
    legible (\\u274c) en lugar de borrarlo. Si tampoco se puede, no se imprime.
    Devuelve si se logro imprimir; nadie deberia necesitar comprobarlo.
    """
    try:
        print(texto, file=destino)
        return True
    except Exception:
        pass
    try:
        print(str(texto).encode("ascii", "backslashreplace").decode("ascii"),
              file=destino)
        return True
    except Exception:
        return False


def reportar_error_de_ciclo(e, *, destino_rastro=None):
    """
    Deja constancia de una excepcion del ciclo SIN poder matar el bucle.

    Informa lo mismo que antes -clase, mensaje y traceback completo- por un
    camino que no puede lanzar. `traceback.print_exc()` se sustituye por
    `format_exception` + impresion resistente porque escribe en el stream por
    su cuenta y falla por el mismo motivo que el print.

    La excepcion original NO se oculta: si su `__str__` es el que falla, al
    menos se informa de su TIPO.
    """
    try:
        detalle = f"{type(e).__name__}: {e}"
    except Exception:
        detalle = type(e).__name__
    imprimir_resistente(f"❌ Error inesperado en ciclo de trading: {detalle}")

    try:
        rastro = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    except Exception:
        rastro = f"(no se pudo formatear el traceback de {type(e).__name__})"
    # El traceback iba a stderr con print_exc(); se conserva ese destino.
    imprimir_resistente(rastro, destino_rastro or sys.stderr)


def get_min_notional(symbol, filters_dict):
    symbol_filters = filters_dict.get(symbol)
    if not symbol_filters:
        return 1.0  # Valor por defecto

    for f in symbol_filters:
        if f["filterType"] in ["NOTIONAL", "MIN_NOTIONAL"]:
            return float(f.get("minNotional", 1.0))
    return 1.0

def _obtener_assets_con_costes(*, medidor=None):
    """Normaliza 3/4 valores sin inventar costes."""
    try:
        resultado = get_available_assets(
            medidor=medidor, incluir_costes_cuenta=True)
    except TypeError as e:
        if "incluir_costes_cuenta" not in str(e):
            raise
        resultado = get_available_assets(medidor=medidor)

    if len(resultado) == 4:
        return resultado
    if len(resultado) == 3:
        assets, balances, symbols_info = resultado
        return assets, balances, symbols_info, {
            "fee_taker_bps_por_lado": None,
            "fee_maker_bps_por_lado": None,
            "fuente_fee": "NO_DISPONIBLE",
            "fuente_fee_maker": "NO_DISPONIBLE",
        }
    raise ValueError(
        f"get_available_assets devolvio {len(resultado)} elementos; "
        "se esperaban 3 o 4")


# Lógica principal del bot
def trading_loop():
    ciclo = 0
    EVALUAR_CADA_N_CICLOS = 2  # Puedes ajustar este valor
    noticias_cache = None
    timestamp_cache = None
    # `filters_dict` ya NO se cachea entre ciclos: se deriva en cada iteracion
    # del mismo exchange_info que trae get_available_assets, sin coste HTTP
    # adicional (02B). Antes se pedia aparte -02A midio 2 exchange_info en el
    # primer ciclo- y luego quedaba congelado para toda la vida del proceso.

    while True:
        # ── Telemetria HTTP del ciclo (Fase BOT 2.0-02A) ─────────────────────
        # `ciclo_id` es EXCLUSIVAMENTE TELEMETRICO: no sustituye a `ciclo` ni
        # participa en EVALUAR_CADA_N_CICLOS, las decisiones, el riesgo, las
        # ordenes ni el scheduling. Existe porque `ciclo` se incrementa en
        # cinco ramas distintas -varias dentro de un `continue`- y por tanto no
        # identifica un recorrido. `ciclo` se guarda como `ciclo_num`, solo
        # como dato diagnostico legacy.
        medidor = MedidorCicloHttp(nuevo_ciclo_id(), ciclo_num=ciclo)
        # ── PERSISTIR ANTES DE ESPERAR ────────────────────────────────────────
        # Las salidas tempranas del ciclo hacian `time.sleep(WAIT_TIME)` DENTRO
        # del try, o sea ANTES del `finally` que vuelca la telemetria. El
        # `finally` garantizaba que se volcase, pero no que se volcase pronto:
        # con WAIT_TIME=14400 el dato tardaba 4 horas en aparecer.
        #
        # Con 03A "0 elegibles" es un resultado NORMAL del ciclo, asi que ese
        # retraso dejaba sin observar justo el caso que interesa. Ahora las
        # ramas solo MARCAN que hay que esperar y el sueno ocurre en el
        # `finally`, detras del volcado:
        #
        #     fin logico del ciclo -> volcar() -> WAIT_TIME -> siguiente
        #
        # La cadencia no cambia: cada rama espera exactamente las veces que
        # esperaba antes -una-, y la salida normal sigue sin esperar.
        esperar_ciclo = False
        try:
            # ── Contexto FRESCO en cada iteracion (P0-5) ──────────────────
            contexto = cargar_contexto_usuario()

            # La ausencia de usuario es un estado normal, no un error (P0-4).
            # El bot espera y se reincorpora solo en cuanto alguien se registre.
            if contexto.usuario_id is None:
                print("[BOT] Sin usuarios registrados todavia. "
                      "Esperando a que alguien complete /signup...")
                esperar_ciclo = True
                continue

            # ── RECONCILIACION antes de operar (P0-14) ───────────────────
            # Solo en LIVE: en PAPER no existen ordenes de broker. Si queda
            # alguna sin resolver, el MotorRiesgo bloqueara toda compra al ver
            # estado.ordenes_pendientes > 0.
            if settings.MODO_REAL:
                reconciliar_pendientes(real_trader, usuario_id=contexto.usuario_id)

            ahora = datetime.now()
            minuto_actual = ahora.minute

            print(f"\n⏳ Ciclo: {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
            simulator.latest_decisions = {}
            precios_actuales = {}

            # Cachear noticias por 1 hora para evitar exceso de llamadas
            if not noticias_cache or (ahora - timestamp_cache).total_seconds() > 3600:
                noticias = news_connector.obtener_noticias_combinadas(6, medidor=medidor)
                noticias_cache = noticias if noticias else []
                timestamp_cache = ahora
            else:
                noticias = noticias_cache

            textos = noticias if noticias else []
            noticias_str = "\n".join(textos) if textos else "No hay noticias disponibles"
            sentimiento = "NO DISPONIBLE"
            print(f"🧑‍🤖 Sentimiento del mercado: {sentimiento}")

            try:
                # Reutiliza el MISMO GET /account que ya obtiene balances.
                # Los adaptadores legacy conservan fee desconocida, nunca cero.
                (assets_disponibles, balances_reales, symbols_info,
                 costes_cuenta) = _obtener_assets_con_costes(medidor=medidor)
            except Exception as e:
                print(f"❌ Error al inicializar Binance o traer datos: {e}")
                esperar_ciclo = True
                ciclo += 1
                continue

            if not assets_disponibles:
                print("⚠️ No se encontraron activos disponibles.")
                esperar_ciclo = True
                ciclo += 1
                continue

            # Los filtros salen del MISMO exchange_info que acaba de traer
            # get_available_assets: cero peticiones extra, y ademas se
            # refrescan cada ciclo en lugar de quedar congelados en el arranque
            # del proceso (02B). Aqui es la unica vez que se construyen.
            filters_dict = {s["symbol"]: s["filters"] for s in symbols_info}

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
                esperar_ciclo = True
                ciclo += 1
                continue

            # Este bloque fue movido hacia arriba

            ciclo += 1  # Aquí avanzamos el ciclo después de haber intentado ejecutar

            # Crear diccionario de saldos reales para acceso rápido. Solo la
            # CarteraLive los consume; CarteraPaper no tiene parametro por el
            # que puedan entrar a su estado ni a su contexto para IA.
            saldo_real_dict = {
                b["asset"]: float(b["free"]) + float(b["locked"])
                for b in balances_reales
            }

            # ── Unico punto donde se decide el modo (P0-15) ──────────────────
            # A partir de aqui el bucle no vuelve a preguntar si es PAPER o
            # LIVE. La cartera activa es tambien la fuente del contexto
            # financiero que vera el LLM.
            cartera = construir_cartera(
                modo_real=settings.MODO_REAL,
                simulador=simulator,
                usuario_id=contexto.usuario_id,
                saldos_broker=saldo_real_dict,
                usdt_broker=saldo_real_dict.get("USDT", 0.0),
                session_factory=SessionLocal,
                paper_initial_capital_usd=settings.INITIAL_CAPITAL_USD,
                paper_fee_taker_bps_por_lado=costes_cuenta.get(
                    "fee_taker_bps_por_lado"),
                paper_order_book_provider=(
                    None if settings.MODO_REAL else
                    lambda symbol: obtener_order_book(
                        binance, symbol, limit=20,
                        medicion=medidor.operacion(
                            "binance", "paper_order_book"),
                    )
                ),
                estado_persistente=contexto.estado,
                ultimos_movimientos=contexto.ultimos_movimientos,
                ultimos_precios_venta=contexto.ultimos_precios_venta,
            )
            print(f"[CARTERA] modo={cartera.modo} capital={cartera.capital_disponible():.2f} USDT")

            # ── UN SOLO SNAPSHOT DE PRECIOS POR CICLO (02B) ──────────────────
            # Una peticion REST para todos los simbolos del exchange, reutilizada
            # por get_multiple_prices y por get_market_pairs. 02A midio 484 +
            # 1.361 tickers individuales haciendo exactamente este trabajo.
            #
            # Efecto lateral deseado: el snapshot es temporalmente COHERENTE
            # -todos los precios del mismo instante- en vez de 1.845 precios
            # tomados a lo largo de 7,8 minutos.
            snapshot_precios = binance.get_price_snapshot(
                medicion=medidor.operacion("binance", "market_price_snapshot"))

            # Metricas de mercado del ciclo: UNA peticion (ticker/24hr completo)
            # que alimenta al scanner. Reutilizada para los 484 activos; aqui se
            # paga una vez y no vuelve a haber trafico (03B).
            metricas_mercado = binance.get_market_metrics(
                medicion=medidor.operacion("binance", "market_metrics"))

            activos_para_gpt = []
            symbols_a_precio = [a["symbol"] for a in activos_evaluar if a["type"] == "crypto"]
            precios_actuales = binance.get_multiple_prices(
                symbols_a_precio,
                snapshot=snapshot_precios,
                medicion=medidor.operacion("binance", "get_multiple_prices"))

            # ── ELIGIBILITY GATE (Fase BOT 2.0-03A) ──────────────────────────
            # Estado y filtros se resuelven UNA vez por ciclo; el resto es
            # aritmetica pura por activo. El gate solo QUITA candidatos: el
            # MotorRiesgo sigue siendo la unica autoridad y vuelve a evaluar de
            # cero cada decision aprobada por el LLM.
            #
            # El estado es el del INICIO del ciclo, igual que el que usaria la
            # primera decision. Si durante el ciclo se libera margen, el gate
            # habra sido algo mas estricto de lo necesario; nunca al contrario,
            # y nunca autoriza nada por su cuenta.
            info_por_symbol = {s["symbol"]: s for s in symbols_info}
            estado_gate = cartera.estado_riesgo()
            capital_gate = cartera.capital_disponible()
            gate = elegibilidad.ResumenElegibilidad(universo=len(activos_evaluar))
            inicio_gate = time.perf_counter()

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

                # Cantidad, coste base y movimientos salen de la MISMA cartera
                # activa. En PAPER, exclusivamente del ledger persistente;
                # en LIVE, saldo broker + contexto persistente. El bucle no mezcla.
                posicion_llm = contexto_posicion_para_llm(cartera, symbol)
                qty = posicion_llm.cantidad
                position_detected = qty > 0
                balance_detected = position_detected

                # ── Puerta de elegibilidad (03A) ──────────────────────────
                # Una posicion ABIERTA entra SIEMPRE, aunque no fuese elegible
                # para comprar: el bot nunca puede quedarse sin poder analizar
                # -y por tanto vender- lo que ya tiene. La elegibilidad es de
                # COMPRA NUEVA y solo se aplica a quien no tiene posicion.
                if position_detected:
                    gate.preservar(symbol)
                else:
                    veredicto = elegibilidad.evaluar_compra(
                        symbol,
                        symbol_info=info_por_symbol.get(symbol),
                        precio=precio,
                        # Mismo calculo que usara despues el MotorRiesgo: se le
                        # pregunta a el, no se replica su formula.
                        max_notional_autorizado=motor_riesgo.limite_compra(
                            capital_disponible=capital_gate,
                            estado=estado_gate,
                            symbol=symbol).quote_permitido,
                    )
                    gate.anotar(veredicto)
                    if not veredicto.elegible:
                        continue

                activos_para_gpt.append({
                    "symbol": symbol,
                    "price": precio,
                    "position_quantity": qty,
                    "average_price": posicion_llm.precio_medio,
                    "last_movement": posicion_llm.ultimo_movimiento,
                    "last_sell_price": posicion_llm.ultimo_precio_venta,
                    "_balance_detected": balance_detected,
                    "_position_detected": position_detected
                })

            print(gate.linea(int((time.perf_counter() - inicio_gate) * 1000)))

            # ── SCANNER DETERMINISTICO (Fase BOT 2.0-03B) ────────────────────
            # Recorta los candidatos de COMPRA NUEVA al Top N por score. No
            # decide, no dimensiona y no autoriza: solo ordena y recorta. Las
            # posiciones abiertas se conservan intactas para poder analizar su
            # salida, igual que en 03A.
            #
            # Todas las metricas salen de UNA peticion (ticker/24hr completo),
            # pedida arriba junto al snapshot de precios. Aqui no hay red.
            resumen_scanner = scanner.ResumenScanner()
            inicio_scanner = time.perf_counter()
            activos_para_gpt = scanner.aplicar(
                activos_para_gpt, metricas_mercado,
                top_n=scanner.TOP_N_POR_DEFECTO, resumen=resumen_scanner)
            print(resumen_scanner.linea(
                int((time.perf_counter() - inicio_scanner) * 1000), requests=0))

            activos_para_gpt.sort(key=lambda a: not (a.get("balance_detected") or a.get("position_detected")))

            print(f"🎯 Enviando {len(activos_para_gpt)} activos a GPT para análisis")

            if not activos_para_gpt:
                print("⚠️ No hay activos para analizar con GPT")
                esperar_ciclo = True
                continue

            # El contexto auxiliar del portafolio y el capital salen de la
            # cartera ACTIVA. `portafolio_real` era construido siempre desde
            # balances_reales de Binance, de modo que PAPER podia enviar al LLM
            # saldos LIVE. La firma del conector se conserva por compatibilidad,
            # pero su argumento ahora es coherente con el modo.
            portafolio_contexto = portafolio_para_llm(cartera)
            usdt_disponible = cartera.capital_disponible()

            # Mismo snapshot, cero peticiones: se construye en memoria (02B).
            market_pairs = get_market_pairs(symbols_info,
                                            snapshot=snapshot_precios,
                                            medidor=medidor)

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

            # Sella el tiempo de PARED consumido ANTES de gastar un solo token.
            # Es la metrica que explica los ~8 m 10 s del baseline frente a los
            # 1296 ms que costo la llamada al LLM.
            medidor.marcar_fase_pre_llm(len(activos_para_gpt))

            resultados, explicacion_gpt = openai.analyze_multiple_assets(
                activos_para_gpt,
                usdt_disponible,
                sentimiento,
                noticias_str,
                portafolio_contexto,
                market_pairs_filtrados,
                ciclo=ciclo,   # solo telemetria: permite agregar por ciclo
                ciclo_id=medidor.ciclo_id,   # solo telemetria: correlacion HTTP
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
                    # ordenes. Cada cartera sabe cual es SU fuente de verdad.
                    estado_riesgo = cartera.estado_riesgo()

                    # base_quantity viene del modelo y NO ES AUTORITATIVA para
                    # el tamano: el motor lo recalcula desde cero.
                    propuesta = PropuestaOperacion(
                        symbol=symbol, side=lado, precio=precio_actual,
                        base_quantity_modelo=base_quantity,
                        min_notional=get_min_notional(symbol, filters_dict),
                    )
                    veredicto = motor_riesgo.evaluar(
                        propuesta,
                        capital_disponible=cartera.capital_disponible(),
                        estado=estado_riesgo,
                    )

                    if not veredicto.aprobado:
                        print(f"⛔ {veredicto}")
                        registrar_rechazo_riesgo(veredicto, sentimiento=sentimiento,
                                                 noticias=noticias_str)
                        continue

                    # Un unico punto de ejecucion para ambos modos. La cartera
                    # decide si es un apunte en memoria o una orden real
                    # persistida tras confirmacion del broker.
                    ejecucion = cartera.ejecutar(veredicto, precio_actual,
                                                 trader=real_trader)
                    if not ejecucion.success:
                        print(f"⛔ {decision} {symbol} NO registrada: {ejecucion}")

                elif decision == "ESPERAR":
                    # Una unica fuente, la de la cartera activa. Antes se
                    # consultaban a la vez el saldo del broker y el simulador.
                    if cartera.cantidad_disponible(symbol) <= 0:
                        print(f"⛔ ESPERAR ignorado: no hay posicion en {symbol} "
                              f"segun la cartera {cartera.modo}")
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
            # Con solo str(e) el NameError de P0-4 fue invisible 15 meses: se
            # sigue informando de la clase, el mensaje y el traceback completo.
            # Lo unico que cambia es que informar ya no puede lanzar y matar el
            # hilo antes de llegar a la espera (ver reportar_error_de_ciclo).
            reportar_error_de_ciclo(e)
            esperar_ciclo = True
            ciclo += 1
        finally:
            # El bucle sale de la iteracion por muchas rutas distintas (varios
            # `continue` y el manejador de excepciones). El `finally` es lo
            # unico que garantiza que se mida TAMBIEN el ciclo que aborto
            # pronto, que es precisamente el caso que interesa diagnosticar.
            #
            # `volcar` nunca lanza y nada depende de su retorno: si la
            # persistencia falla, este ciclo termina exactamente igual que sin
            # telemetria.
            medidor.volcar()

            # La espera va DESPUES del volcado. No se espera si estamos saliendo
            # por una excepcion que el bucle no controla (Ctrl-C, cierre del
            # proceso): dormir 4 horas antes de propagarla dejaria el apagado
            # colgado. `sys.exc_info()` en un finally solo trae algo cuando hay
            # una excepcion en vuelo sin manejar.
            if esperar_ciclo and sys.exc_info()[0] is None:
                time.sleep(settings.WAIT_TIME)


# ─────────────────────────────────────────────────────────────────────────────
# CICLO DE VIDA (P0-13)
#
# Importar este modulo NO arranca a operar. El bucle solo se pone en marcha
# desde el lifespan de FastAPI y unicamente si este proceso gana el candado de
# liderazgo. Con --reload o --workers N, solo uno opera; los demas lo registran
# y se quedan sirviendo la API.
# ─────────────────────────────────────────────────────────────────────────────
def _precondicion_esquema():
    """
    El bucle NO arranca si el esquema no esta alineado con las migraciones.

    Fallo cerrado: operar contra una base cuyo esquema no conocemos podria
    escribir transacciones u ordenes en tablas que no existen o que tienen otra
    forma. Con MODO_REAL=True eso significaria dinero real sobre un ledger que
    no podemos garantizar. La API si arranca, para permitir diagnostico.

    Esta comprobacion SOLO LEE: nunca aplica una migracion.
    """
    from backend.esquema import ALINEADO, estado_esquema

    e = estado_esquema()
    if e.estado == ALINEADO:
        return True, ""
    return False, (
        f"esquema no alineado [{e.estado}] actual={e.revision_actual} "
        f"esperada={e.revision_esperada}. {e.detalle or ''} "
        f"Migrar es una operacion explicita de despliegue: alembic upgrade head."
    )


coordinador = CoordinadorTrading(
    objetivo=trading_loop,
    candado=candado_por_defecto(settings.DATABASE_URL),
    precondiciones=(_precondicion_esquema,),
)


@app.get("/health")
def health():
    """Permite ver desde fuera quien es el lider y por que no opera un proceso."""
    return {
        "trading_mode": settings.TRADING_MODE,
        "modo_real": settings.MODO_REAL,
        "bucle_activo": coordinador.activo,
        "es_lider": coordinador.es_lider,
        "motivo_inactivo": coordinador.motivo_inactivo or None,
        # Solo INFORMA. La app nunca migra por su cuenta (P0-16).
        "esquema": _estado_esquema_serializado(),
    }


def _estado_esquema_serializado():
    from backend.esquema import estado_esquema
    e = estado_esquema()
    return {"estado": e.estado, "revision_actual": e.revision_actual,
            "revision_esperada": e.revision_esperada, "detalle": e.detalle}

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
    valor_total = 0.0
    pnl_total = None
    pnl_total_conocido = True
    # En PAPER el saldo del exchange no pertenece al libro simulado, asi que no
    # tiene coste base publicable aqui. No se inventa cero.
    motivo_sin_coste = (None if settings.MODO_REAL else
                        "en PAPER el saldo del exchange no tiene coste base en "
                        "el libro simulado")

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

        # Precio medio y P&L solo si hay coste base registrado. Sin el no hay
        # P&L: no es cero (Fase 6).
        medio = precio_medio_de(estado, symbol)
        motivo = motivo_sin_coste or (None if medio is not None
                                      else f"sin coste base registrado para {symbol}")
        pnl = pnl_no_realizado(precio_actual, medio, total)
        valor_actual = round(total * precio_actual, 2)

        fila = {"symbol": symbol, "cantidad": round(total, 6),
                "precio_actual": round(precio_actual, 4),
                "valor_actual": valor_actual}
        fila.update(campos("average_price", medio, redondeo=6, motivo=motivo))
        fila.update(campos("pnl", pnl, redondeo=2, motivo=motivo))
        resumen.append(fila)

        valor_total += valor_actual
        if pnl is None:
            pnl_total_conocido = False
        else:
            pnl_total = (pnl_total or 0.0) + pnl

    # Mostrar USDT primero
    resumen.sort(key=lambda x: 0 if x["symbol"] == "USDT" else 1)

    salida = {"modo": settings.TRADING_MODE, "resumen": resumen,
              "valor_total_usd": round(valor_total, 2)}
    # El campo antiguo se llamaba `ganancia_total` pero sumaba el VALOR de la
    # cartera, no una ganancia. Se publica con su nombre correcto y el P&L real
    # se expone aparte, con su estado.
    salida.update(campos("pnl_total", pnl_total if pnl_total_conocido else None,
                         redondeo=2,
                         motivo="al menos un activo carece de coste base"))
    return salida

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
