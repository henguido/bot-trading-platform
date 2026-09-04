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
from backend import scanner, decision_engine
from backend.economia.profundidad import obtener_order_book
from backend.economia.integracion_05e import (
    PROFITABILITY_GATE_05E_ENABLED,
    aplicar_pre_llm_05e,
    compra_post_llm_permitida_05e,
)
from backend.simulation.paper_api import historial_paper, resumen_paper
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
from backend.observabilidad.ciclos import (
    ResumenCicloDecision, persistir_resumen_ciclo,
)
from contextlib import asynccontextmanager
import sys
import time
import threading
import pytz, traceback

# ─────────────────────────────────────────────────────────────────────────────
# P0-16 · ALEMBIC ES LA UNICA AUTORIDAD DEL ESQUEMA
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app):
    """Unico punto de arranque y parada del bucle de trading (P0-13)."""
    coordinador.iniciar()
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
    allow_origins=list(settings.CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

binance = BinanceConnector()
openai = OpenAIConnector()
simulator = Simulator()
alpaca = AlpacaConnector()
news_connector = NewsConnector()
real_trader = RealTradingConnector()


def priorizar_activos_por_importancia(activos):
    return [a for a in activos if a["position_quantity"] > 0]


motor_riesgo = MotorRiesgo()
stop_trading = threading.Event()


def registrar_rechazo_riesgo(veredicto, *, sentimiento, noticias):
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


def imprimir_resistente(texto, destino=None):
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
    try:
        detalle = f"{type(e).__name__}: {e}"
    except Exception:
        detalle = type(e).__name__
    imprimir_resistente(f"❌ Error inesperado en ciclo de trading: {detalle}")
    try:
        rastro = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    except Exception:
        rastro = f"(no se pudo formatear el traceback de {type(e).__name__})"
    imprimir_resistente(rastro, destino_rastro or sys.stderr)


def get_min_notional(symbol, info_por_symbol):
    filtros = elegibilidad.leer_filtros(info_por_symbol.get(symbol))
    return float(filtros.min_notional) if filtros is not None else None


def _obtener_assets_con_costes(*, medidor=None):
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


def trading_loop():
    ciclo = 0
    EVALUAR_CADA_N_CICLOS = 2
    noticias_cache = None
    timestamp_cache = None

    while not stop_trading.is_set():
        medidor = MedidorCicloHttp(nuevo_ciclo_id(), ciclo_num=ciclo)
        esperar_ciclo = False
        resumen_decision_ciclo = None
        try:
            contexto = cargar_contexto_usuario()

            if contexto.usuario_id is None:
                print("[BOT] Sin usuarios registrados todavia. "
                      "Esperando a que alguien complete /signup...")
                esperar_ciclo = True
                continue

            resumen_decision_ciclo = ResumenCicloDecision(
                ciclo_id=medidor.ciclo_id,
                usuario_id=contexto.usuario_id,
                modo="LIVE" if settings.MODO_REAL else "PAPER",
                decision_engine=settings.DECISION_ENGINE,
            )

            if settings.MODO_REAL:
                reconciliar_pendientes(real_trader, usuario_id=contexto.usuario_id)

            ahora = datetime.now()
            minuto_actual = ahora.minute

            print(f"\n⏳ Ciclo: {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
            simulator.latest_decisions = {}
            precios_actuales = {}

            try:
                (assets_disponibles, balances_reales, symbols_info,
                 costes_cuenta) = _obtener_assets_con_costes(medidor=medidor)
            except Exception as e:
                print(f"❌ Error al inicializar Binance o traer datos: {e}")
                if resumen_decision_ciclo is not None:
                    resumen_decision_ciclo.anotar_omision("DATOS_BINANCE_NO_DISPONIBLES")
                esperar_ciclo = True
                ciclo += 1
                continue

            if not assets_disponibles:
                print("⚠️ No se encontraron activos disponibles.")
                if resumen_decision_ciclo is not None:
                    resumen_decision_ciclo.anotar_omision("SIN_ACTIVOS_DISPONIBLES")
                esperar_ciclo = True
                ciclo += 1
                continue

            filters_dict = {s["symbol"]: s["filters"] for s in symbols_info}
            info_por_symbol = {s["symbol"]: s for s in symbols_info}

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
                if resumen_decision_ciclo is not None:
                    resumen_decision_ciclo.anotar_omision("FUERA_DE_CADENCIA")
                esperar_ciclo = True
                ciclo += 1
                continue

            ciclo += 1

            saldo_real_dict = {
                b["asset"]: float(b["free"]) + float(b["locked"])
                for b in balances_reales
            }

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
                paper_symbol_info_provider=(
                    None if settings.MODO_REAL else
                    lambda symbol: info_por_symbol.get(symbol)
                ),
                estado_persistente=contexto.estado,
                ultimos_movimientos=contexto.ultimos_movimientos,
                ultimos_precios_venta=contexto.ultimos_precios_venta,
            )
            print(f"[CARTERA] modo={cartera.modo} capital={cartera.capital_disponible():.2f} USDT")

            snapshot_precios = binance.get_price_snapshot(
                medicion=medidor.operacion("binance", "market_price_snapshot"))

            metricas_mercado = binance.get_market_metrics(
                medicion=medidor.operacion("binance", "market_metrics"))

            activos_para_gpt = []
            symbols_a_precio = [a["symbol"] for a in activos_evaluar if a["type"] == "crypto"]
            precios_actuales = binance.get_multiple_prices(
                symbols_a_precio,
                snapshot=snapshot_precios,
                medicion=medidor.operacion("binance", "get_multiple_prices"))

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

                posicion_llm = contexto_posicion_para_llm(cartera, symbol)
                qty = posicion_llm.cantidad
                position_detected = qty > 0
                balance_detected = position_detected

                if position_detected:
                    gate.preservar(symbol)
                else:
                    veredicto = elegibilidad.evaluar_compra(
                        symbol,
                        symbol_info=info_por_symbol.get(symbol),
                        precio=precio,
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
            if resumen_decision_ciclo is not None:
                resumen_decision_ciclo.anotar_elegibilidad(gate)

            resumen_scanner = scanner.ResumenScanner()
            inicio_scanner = time.perf_counter()
            activos_para_gpt = scanner.aplicar(
                activos_para_gpt, metricas_mercado,
                top_n=scanner.TOP_N_POR_DEFECTO, resumen=resumen_scanner)
            print(resumen_scanner.linea(
                int((time.perf_counter() - inicio_scanner) * 1000), requests=0))
            if resumen_decision_ciclo is not None:
                resumen_decision_ciclo.anotar_scanner(resumen_scanner)

            notional_rentabilidad = {}
            if PROFITABILITY_GATE_05E_ENABLED:
                estado_pre_llm = cartera.estado_riesgo()
                capital_pre_llm = cartera.capital_disponible()
                for candidato in activos_para_gpt:
                    if candidato.get("_position_detected"):
                        continue
                    sym = candidato.get("symbol")
                    if not sym:
                        continue
                    limite = motor_riesgo.limite_compra(
                        capital_disponible=capital_pre_llm,
                        estado=estado_pre_llm,
                        symbol=sym,
                    )
                    if limite.quote_permitido and limite.quote_permitido > 0:
                        notional_rentabilidad[sym] = limite.quote_permitido

            n_antes_05e = len(activos_para_gpt)
            pre_llm_05e = aplicar_pre_llm_05e(
                activos_para_gpt,
                metricas_mercado,
                fee_taker_bps_por_lado=costes_cuenta.get(
                    "fee_taker_bps_por_lado"),
                notional_por_symbol=notional_rentabilidad,
                binance=binance,
                medidor=medidor,
                enabled=PROFITABILITY_GATE_05E_ENABLED,
                modo_real=settings.MODO_REAL,
            )
            activos_para_gpt = list(pre_llm_05e.activos)
            evaluaciones_rentabilidad_05e = pre_llm_05e.evaluaciones
            if resumen_decision_ciclo is not None:
                resumen_decision_ciclo.anotar_rentabilidad_pre(
                    antes=n_antes_05e,
                    despues=len(activos_para_gpt),
                    aplicado=pre_llm_05e.aplicado,
                    motivo=pre_llm_05e.motivo,
                )
            if pre_llm_05e.aplicado and pre_llm_05e.resumen is not None:
                print(pre_llm_05e.resumen.linea())

            activos_para_gpt.sort(key=lambda a: not (
                a.get("_balance_detected") or a.get("_position_detected")))

            print(f"🎯 Enviando {len(activos_para_gpt)} activos al motor {settings.DECISION_ENGINE}")

            if not activos_para_gpt:
                print("⚠️ No hay activos para analizar con el motor de decisión")
                if resumen_decision_ciclo is not None:
                    resumen_decision_ciclo.anotar_omision("SIN_CANDIDATOS_MOTOR")
                esperar_ciclo = True
                continue

            # Noticias/contexto se consulta SOLO cuando ya existen finalistas.
            # Asi una caida en elegibilidad/scanner no dispara APIs externas que
            # no pueden influir en ninguna decision. El cache conserva el mismo
            # contrato de una hora y un fallo sigue degradando a contexto vacio.
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

            portafolio_contexto = portafolio_para_llm(cartera)
            usdt_disponible = cartera.capital_disponible()

            market_pairs = get_market_pairs(symbols_info,
                                            snapshot=snapshot_precios,
                                            medidor=medidor)

            activos_relevantes = {
                a["symbol"].replace("USDT", "") for a in activos_para_gpt
                if a["position_quantity"] > 0 or a.get("_balance_detected")
            }

            market_pairs_filtrados = [
                p for p in market_pairs
                if any(activo in p["pair"] for activo in activos_relevantes)
            ]
            for a in activos_para_gpt:
                a.pop("_balance_detected", None)
                a.pop("_position_detected", None)

            if settings.DECISION_ENGINE == decision_engine.ENGINE_GPT:
                medidor.marcar_fase_pre_llm(len(activos_para_gpt))

            resultados, explicacion_gpt = decision_engine.decidir(
                settings.DECISION_ENGINE,
                openai=openai,
                activos=activos_para_gpt,
                usdt_disponible=usdt_disponible,
                sentimiento=sentimiento,
                noticias_str=noticias_str,
                portafolio_contexto=portafolio_contexto,
                market_pairs_filtrados=market_pairs_filtrados,
                ciclo=ciclo,
                ciclo_id=medidor.ciclo_id,
            )

            if not resultados:
                if resumen_decision_ciclo is not None:
                    resumen_decision_ciclo.anotar_omision("MOTOR_SIN_RESULTADOS")
                print("⚠️ El motor no devolvió resultados válidos. Respuesta completa:")
                print(explicacion_gpt)
                simulator.audit_log.append({
                    "symbol": "MOTOR",
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
            print("🧠 Resultados motor:", resultados)

            for resultado in resultados:
                symbol = resultado.get("symbol")
                decision = resultado.get("decision", "ESPERAR")
                if resumen_decision_ciclo is not None:
                    resumen_decision_ciclo.anotar_decision(decision)
                base_quantity = resultado.get("quantity", 0.0)
                risk_score = resultado.get("risk_score", 0.0)
                economics = {}

                if not symbol:
                    if resumen_decision_ciclo is not None:
                        resumen_decision_ciclo.anotar_omision("RESULTADO_SIN_SYMBOL")
                    continue

                precio_actual = precios_actuales.get(symbol)
                if precio_actual is None:
                    print(f"⚠️ Precio no disponible para {symbol}. Se omite.")
                    if resumen_decision_ciclo is not None:
                        resumen_decision_ciclo.anotar_omision("PRECIO_NO_DISPONIBLE")
                    continue

                if decision in ("COMPRAR", "VENDER"):
                    economics, diagnostico_economia = (
                        decision_engine.contexto_economico_para_ejecucion(
                            settings.DECISION_ENGINE, resultado)
                    )
                    if diagnostico_economia:
                        if resumen_decision_ciclo is not None:
                            resumen_decision_ciclo.anotar_omision(
                                diagnostico_economia)
                        imprimir_resistente(
                            f"[ECONOMIA] {symbol}: {diagnostico_economia}; "
                            "ejecucion continua sin metadata expected")

                    lado = Lado.COMPRA if decision == "COMPRAR" else Lado.VENTA

                    if lado is Lado.COMPRA:
                        permitida_05e, motivo_05e = compra_post_llm_permitida_05e(
                            symbol, evaluaciones_rentabilidad_05e,
                            enabled=PROFITABILITY_GATE_05E_ENABLED,
                        )
                        if not permitida_05e:
                            print(f"[RENTABILIDAD-05E] {symbol} bloqueada: {motivo_05e}")
                            if resumen_decision_ciclo is not None:
                                resumen_decision_ciclo.anotar_rentabilidad_post_bloqueada(motivo_05e)
                            continue

                    estado_riesgo = cartera.estado_riesgo()

                    min_notional = (
                        get_min_notional(symbol, info_por_symbol)
                        if lado is Lado.COMPRA else 0.0
                    )
                    if lado is Lado.COMPRA and min_notional is None:
                        imprimir_resistente(
                            f"[EXCHANGE] {symbol}: filtros LOT_SIZE/NOTIONAL desconocidos; compra bloqueada")
                        if resumen_decision_ciclo is not None:
                            resumen_decision_ciclo.anotar_omision(
                                "FILTROS_EXCHANGE_DESCONOCIDOS")
                        continue

                    propuesta = PropuestaOperacion(
                        symbol=symbol, side=lado, precio=precio_actual,
                        base_quantity_modelo=base_quantity,
                        min_notional=min_notional,
                    )
                    veredicto = motor_riesgo.evaluar(
                        propuesta,
                        capital_disponible=cartera.capital_disponible(),
                        estado=estado_riesgo,
                    )
                    if resumen_decision_ciclo is not None:
                        resumen_decision_ciclo.anotar_riesgo(veredicto)

                    if not veredicto.aprobado:
                        print(f"⛔ {veredicto}")
                        registrar_rechazo_riesgo(veredicto, sentimiento=sentimiento,
                                                 noticias=noticias_str)
                        continue

                    ejecucion = cartera.ejecutar(
                        veredicto,
                        precio_actual,
                        trader=real_trader,
                        economics=economics,
                    )
                    if resumen_decision_ciclo is not None:
                        resumen_decision_ciclo.anotar_ejecucion(
                            success=bool(ejecucion.success),
                            motivo=None if ejecucion.success else type(ejecucion).__name__,
                        )
                    if not ejecucion.success:
                        print(f"⛔ {decision} {symbol} NO registrada: {ejecucion}")

                elif decision == "ESPERAR":
                    if cartera.cantidad_disponible(symbol) <= 0:
                        print(f"⛔ ESPERAR ignorado: no hay posicion en {symbol} "
                              f"segun la cartera {cartera.modo}")
                        if resumen_decision_ciclo is not None:
                            resumen_decision_ciclo.anotar_omision("ESPERAR_SIN_POSICION")
                        continue

                simulator.latest_decisions[symbol] = decision
                simulator.audit_log.append({
                    "symbol": symbol,
                    "action": decision,
                    "price": precio_actual,
                    "quantity": base_quantity,
                    "timestamp": ahora.astimezone(pytz.timezone("America/Costa_Rica")).strftime("%Y-%m-%d %H:%M:%S"),
                    "context": {
                        "sentimiento": sentimiento,
                        "noticias": noticias_str,
                        "risk_score": risk_score,
                        "economics": economics,
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
                    print(f"⚠️ Error guardando auditoría de decisión: {e}")

        except Exception as e:
            if resumen_decision_ciclo is not None:
                resumen_decision_ciclo.anotar_omision(f"ERROR_CICLO:{type(e).__name__}")
            reportar_error_de_ciclo(e)
            esperar_ciclo = True
            ciclo += 1
        finally:
            medidor.volcar()

            if resumen_decision_ciclo is not None:
                try:
                    with SessionLocal() as db:
                        persistir_resumen_ciclo(db, resumen_decision_ciclo)
                except Exception as e:
                    imprimir_resistente(
                        f"[OBSERVABILIDAD] no se pudo persistir ciclo: "
                        f"{type(e).__name__}: {e}")

            if esperar_ciclo and sys.exc_info()[0] is None:
                stop_trading.wait(settings.WAIT_TIME)


def _precondicion_esquema():
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
    stop_event=stop_trading,
)


@app.get("/health")
def health():
    return {
        "trading_mode": settings.TRADING_MODE,
        "modo_real": settings.MODO_REAL,
        "bucle_activo": coordinador.activo,
        "es_lider": coordinador.es_lider,
        "motivo_inactivo": coordinador.motivo_inactivo or None,
        "esquema": _estado_esquema_serializado(),
    }


def _estado_esquema_serializado():
    from backend.esquema import estado_esquema
    e = estado_esquema()
    return {"estado": e.estado, "revision_actual": e.revision_actual,
            "revision_esperada": e.revision_esperada, "detalle": e.detalle}


@app.get("/api/historial")
def get_historial(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not settings.MODO_REAL:
        return historial_paper(db, usuario_id=current_user.id)

    auditorias = db.query(models.DecisionAudit).order_by(models.DecisionAudit.timestamp.desc()).all()
    historial = []

    for a in auditorias:
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
def resumen_portafolio(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not settings.MODO_REAL:
        return resumen_paper(
            db,
            usuario_id=current_user.id,
            initial_capital_usd=settings.INITIAL_CAPITAL_USD,
            obtener_precio=binance.get_current_price,
        )

    balances = binance.get_account_balance()
    resumen = []
    valor_total = 0.0
    pnl_total = None
    pnl_total_conocido = True
    motivo_sin_coste = (None if settings.MODO_REAL else
                        "en PAPER el saldo del exchange no tiene coste base en "
                        "el libro simulado")

    estado = cargar_contexto_usuario().estado

    for b in balances:
        asset = b["asset"]
        total = float(b["free"]) + float(b["locked"])

        if total == 0:
            continue

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

    resumen.sort(key=lambda x: 0 if x["symbol"] == "USDT" else 1)

    salida = {"modo": settings.TRADING_MODE, "resumen": resumen,
              "valor_total_usd": round(valor_total, 2)}
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
        "nombre": user.nombre
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

    return {"mensaje": "Usuario creado correctamente", "usuario_id": nuevo_usuario.id}
