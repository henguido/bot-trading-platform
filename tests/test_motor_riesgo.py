"""
P0-8 y P0-6 · Motor deterministico de gestion de riesgo.

P0-8  GPT decidia el tamano economico de las ordenes sin ningun tope.
P0-6  MAX_DAILY_LOSS estaba declarado en .env y ningun codigo lo leia.

Todo sin red: broker espia, SQLite en memoria y configuracion inyectada.
"""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.services.ordenes import Lado
from backend.app.services.real_trading import (
    ejecutar_y_registrar_compra,
    guardar_transaccion_real,
)
from backend.risk import reloj
from backend.risk.estado import EstadoRiesgo, Posicion, calcular_estado_riesgo
from backend.risk.motor import DecisionRiesgo, MotorRiesgo, PropuestaOperacion

RAIZ = Path(__file__).resolve().parents[1]
SIMBOLO = "BTCUSDT"
PRECIO = 100000.0


def config(*, monto_max=20.0, asignacion=0.1, perdida_max=20.0,
           exp_total=100.0, exp_activo=50.0):
    return SimpleNamespace(
        MONTO_MAXIMO_USDT=monto_max,
        LIMITE_ASIGNACION_POR_OPERACION=asignacion,
        MAX_DAILY_LOSS_USDT=perdida_max,
        MAX_EXPOSICION_TOTAL_USDT=exp_total,
        MAX_EXPOSICION_POR_ACTIVO_USDT=exp_activo,
    )


def estado(*, posiciones=None, pnl=0.0):
    return EstadoRiesgo(dia=reloj.dia_de_riesgo(),
                        posiciones=posiciones or {}, pnl_realizado_dia=pnl)


def propuesta(side=Lado.COMPRA, cantidad=1.0, precio=PRECIO, min_notional=0.0):
    return PropuestaOperacion(symbol=SIMBOLO, side=side, precio=precio,
                              base_quantity_modelo=cantidad, min_notional=min_notional)


@pytest.fixture
def fabrica():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    models.Base.metadata.create_all(bind=engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def usuario(fabrica):
    with fabrica() as db:
        u = models.User(nombre="T", email="t@e.com", password_hash="x")
        db.add(u); db.commit(); db.refresh(u)
        return u.id


# ═══ 1 · GPT NO CONTROLA EL TAMANO ═══════════════════════════════════════════
def test_1_el_modelo_no_influye_en_el_tamano_autorizado():
    motor = MotorRiesgo(config=config())
    ctx = dict(capital_disponible=1000.0, estado=estado())

    a = motor.evaluar(propuesta(cantidad=10000), **ctx)
    b = motor.evaluar(propuesta(cantidad=0.000001), **ctx)

    assert a.aprobado and b.aprobado
    assert a.approved_quote_amount == b.approved_quote_amount
    assert a.approved_base_quantity == b.approved_base_quantity
    assert a.requested_by_model != b.requested_by_model, "se conserva para auditoria"


@pytest.mark.parametrize("cantidad_modelo", [999999, 0.00000001, 1, 0, -5, None])
def test_1b_cualquier_cantidad_del_modelo_da_el_mismo_tamano(cantidad_modelo):
    motor = MotorRiesgo(config=config())
    d = motor.evaluar(propuesta(cantidad=cantidad_modelo),
                      capital_disponible=1000.0, estado=estado())
    assert d.approved_quote_amount == pytest.approx(20.0)


# ═══ 2 · HARD CAP ════════════════════════════════════════════════════════════
def test_2_hard_cap_por_operacion():
    motor = MotorRiesgo(config=config(monto_max=20.0))
    d = motor.evaluar(propuesta(cantidad=10_000),
                      capital_disponible=1_000_000.0, estado=estado())
    assert d.approved_quote_amount == pytest.approx(20.0)
    assert d.approved_quote_amount <= 20.0


# ═══ 3 · CAPITAL PEQUENO ═════════════════════════════════════════════════════
def test_3_capital_pequeno_limita_por_asignacion():
    """Capital 50, asignacion 10% -> 5 USDT, no 20."""
    motor = MotorRiesgo(config=config(monto_max=20.0, asignacion=0.1))
    d = motor.evaluar(propuesta(), capital_disponible=50.0, estado=estado())
    assert d.aprobado
    assert d.approved_quote_amount == pytest.approx(5.0)
    assert d.approved_base_quantity == pytest.approx(5.0 / PRECIO)


# ═══ 4 · MIN NOTIONAL ════════════════════════════════════════════════════════
def test_4_min_notional_rechaza_y_no_eleva():
    motor = MotorRiesgo(config=config(monto_max=20.0, asignacion=0.1))
    d = motor.evaluar(propuesta(min_notional=10.0),
                      capital_disponible=50.0, estado=estado())  # autorizado = 5
    assert d.aprobado is False
    assert d.limite_violado == "min_notional"
    assert d.approved_quote_amount == 0.0, "jamas se eleva hasta el minimo"


# ═══ 5 · CANTIDADES RESULTANTES SANAS ════════════════════════════════════════
@pytest.mark.parametrize("capital", [0.0, -10.0, float("nan"),
                                     float("inf"), float("-inf")])
def test_5_capital_invalido_se_rechaza_siempre(capital):
    """
    Ninguno de estos capitales puede producir una orden. Ojo con NaN: min()
    lo ignora en silencio, asi que sin validacion explicita el motor habria
    aprobado el tope por operacion como si el capital fuera valido.
    """
    motor = MotorRiesgo(config=config())
    d = motor.evaluar(propuesta(), capital_disponible=capital, estado=estado())
    assert d.aprobado is False, f"capital={capital!r} no debe autorizar ninguna orden"
    assert d.approved_quote_amount == 0.0
    assert d.approved_base_quantity == 0.0


def test_5c_las_cantidades_aprobadas_son_siempre_finitas_y_positivas():
    import math
    motor = MotorRiesgo(config=config())
    for capital in (10.0, 50.0, 1000.0, 1_000_000.0):
        d = motor.evaluar(propuesta(), capital_disponible=capital, estado=estado())
        if d.aprobado:
            assert math.isfinite(d.approved_base_quantity) and d.approved_base_quantity > 0
            assert math.isfinite(d.approved_quote_amount) and d.approved_quote_amount > 0


@pytest.mark.parametrize("precio", [0.0, -1.0, float("nan"), float("inf")])
def test_5b_precio_invalido_se_rechaza(precio):
    motor = MotorRiesgo(config=config())
    d = motor.evaluar(propuesta(precio=precio), capital_disponible=1000.0, estado=estado())
    assert d.aprobado is False


# ═══ 6 · EXPOSICION ACUMULADA ════════════════════════════════════════════════
def test_6_la_exposicion_acumulada_acaba_bloqueando():
    """20 USDT por ciclo con tope total de 100 -> la 6a compra se rechaza."""
    motor = MotorRiesgo(config=config(monto_max=20.0, asignacion=1.0,
                                      exp_total=100.0, exp_activo=1000.0))
    aprobadas = 0
    cantidad, coste = 0.0, PRECIO
    for _ in range(10):
        pos = {SIMBOLO: Posicion(cantidad=cantidad, coste_medio=coste)}
        d = motor.evaluar(propuesta(), capital_disponible=100000.0,
                          estado=estado(posiciones=pos))
        if not d.aprobado:
            assert d.limite_violado == "MAX_EXPOSICION_TOTAL_USDT"
            break
        aprobadas += 1
        cantidad += d.approved_base_quantity
    assert aprobadas == 5, f"con 20 por operacion y tope 100 deben caber 5, hubo {aprobadas}"
    assert d.aprobado is False, "la siguiente compra debe rechazarse"


def test_6b_limite_por_activo():
    motor = MotorRiesgo(config=config(exp_total=1000.0, exp_activo=50.0))
    pos = {SIMBOLO: Posicion(cantidad=50.0 / PRECIO, coste_medio=PRECIO)}  # 50 USDT
    d = motor.evaluar(propuesta(), capital_disponible=100000.0, estado=estado(posiciones=pos))
    assert d.aprobado is False
    assert d.limite_violado == "MAX_EXPOSICION_POR_ACTIVO_USDT"


# ═══ 7 · PERDIDA DIARIA ══════════════════════════════════════════════════════
def test_7_kill_switch_por_perdida_diaria():
    motor = MotorRiesgo(config=config(perdida_max=20.0))

    d = motor.evaluar(propuesta(), capital_disponible=1000.0, estado=estado(pnl=-19.0))
    assert d.aprobado is True, "con -19 y limite 20 aun se puede operar"
    assert d.kill_switch_activo is False

    d = motor.evaluar(propuesta(), capital_disponible=1000.0, estado=estado(pnl=-21.0))
    assert d.aprobado is False
    assert d.kill_switch_activo is True
    assert d.limite_violado == "MAX_DAILY_LOSS_USDT"


# ═══ 8 · VENTA CON KILL SWITCH ACTIVO ════════════════════════════════════════
def test_8_el_kill_switch_bloquea_compras_pero_permite_vender():
    motor = MotorRiesgo(config=config(perdida_max=20.0))
    pos = {SIMBOLO: Posicion(cantidad=0.001, coste_medio=PRECIO)}
    est = estado(posiciones=pos, pnl=-21.0)

    compra = motor.evaluar(propuesta(Lado.COMPRA), capital_disponible=1000.0, estado=est)
    assert compra.aprobado is False, "no se puede aumentar exposicion"

    venta = motor.evaluar(propuesta(Lado.VENTA, cantidad=0.001),
                          capital_disponible=1000.0, estado=est)
    assert venta.aprobado is True, "salir de una posicion siempre debe permitirse"
    assert venta.approved_base_quantity == pytest.approx(0.001)
    assert venta.kill_switch_activo is True


# ═══ 9 · NUNCA VENDER MAS QUE LA POSICION ════════════════════════════════════
def test_9_no_se_puede_vender_mas_que_la_posicion():
    motor = MotorRiesgo(config=config(perdida_max=20.0))
    pos = {SIMBOLO: Posicion(cantidad=0.001, coste_medio=PRECIO)}

    d = motor.evaluar(propuesta(Lado.VENTA, cantidad=0.01),
                      capital_disponible=1000.0, estado=estado(posiciones=pos, pnl=-21.0))
    assert d.aprobado is True
    assert d.approved_base_quantity == pytest.approx(0.001), "acotado a la posicion"
    assert d.approved_base_quantity < 0.01, "nunca se abre un corto"


def test_9b_venta_sin_posicion_se_rechaza():
    motor = MotorRiesgo(config=config())
    d = motor.evaluar(propuesta(Lado.VENTA, cantidad=0.001),
                      capital_disponible=1000.0, estado=estado())
    assert d.aprobado is False
    assert d.limite_violado == "posicion_disponible"


# ═══ 10 · CAMBIO DE DIA ══════════════════════════════════════════════════════
def test_10_el_cambio_de_dia_reinicia_el_pnl_sin_estado_global(fabrica, usuario):
    """Sin ningun booleano en memoria: el dia se deriva de las transacciones."""
    ayer = reloj.dia_de_riesgo() - timedelta(days=1)
    inicio_ayer, _ = reloj.ventana_utc(ayer)
    momento_ayer = inicio_ayer + timedelta(hours=2)

    with fabrica() as db:
        t1 = guardar_transaccion_real(db, usuario_id=usuario, symbol=SIMBOLO,
                                      action="COMPRAR", price=PRECIO, quantity=0.001)
        t1.fecha_operacion = momento_ayer
        t2 = guardar_transaccion_real(db, usuario_id=usuario, symbol=SIMBOLO,
                                      action="VENDER", price=80000.0, quantity=0.001)
        t2.fecha_operacion = momento_ayer + timedelta(minutes=1)
        db.commit()

    motor = MotorRiesgo(config=config(perdida_max=15.0))

    est_ayer = calcular_estado_riesgo(usuario, dia=ayer, session_factory=fabrica)
    assert est_ayer.pnl_realizado_dia == pytest.approx(-20.0)
    assert motor.kill_switch_activo(est_ayer) is True, "dia 1: bloqueado"

    est_hoy = calcular_estado_riesgo(usuario, dia=reloj.dia_de_riesgo(), session_factory=fabrica)
    assert est_hoy.pnl_realizado_dia == pytest.approx(0.0)
    assert motor.kill_switch_activo(est_hoy) is False, "dia 2: disponible de nuevo"
    assert est_ayer.pnl_realizado_dia == pytest.approx(-20.0), "el historico permanece"


# ═══ 11 · REINICIO DEL PROCESO ═══════════════════════════════════════════════
def test_11_el_estado_se_reconstruye_identico_tras_reiniciar(fabrica, usuario):
    with fabrica() as db:
        guardar_transaccion_real(db, usuario_id=usuario, symbol=SIMBOLO,
                                 action="COMPRAR", price=PRECIO, quantity=0.002)
        guardar_transaccion_real(db, usuario_id=usuario, symbol=SIMBOLO,
                                 action="VENDER", price=90000.0, quantity=0.001)

    primero = calcular_estado_riesgo(usuario, session_factory=fabrica)
    # "Reinicio": nada en memoria, se recalcula solo desde persistencia.
    segundo = calcular_estado_riesgo(usuario, session_factory=fabrica)

    assert primero.pnl_realizado_dia == segundo.pnl_realizado_dia == pytest.approx(-10.0)
    assert primero.exposicion_total == pytest.approx(segundo.exposicion_total)
    assert primero.cantidad_disponible(SIMBOLO) == pytest.approx(0.001)

    motor = MotorRiesgo(config=config(perdida_max=5.0))
    assert motor.kill_switch_activo(primero) == motor.kill_switch_activo(segundo) is True


def test_11b_pnl_del_ejemplo_documentado(fabrica, usuario):
    """Compra 0.001 @100000, venta 0.0005 @110000 -> +5.00 USDT realizados."""
    with fabrica() as db:
        guardar_transaccion_real(db, usuario_id=usuario, symbol=SIMBOLO,
                                 action="COMPRAR", price=100000.0, quantity=0.001)
        guardar_transaccion_real(db, usuario_id=usuario, symbol=SIMBOLO,
                                 action="VENDER", price=110000.0, quantity=0.0005)

    est = calcular_estado_riesgo(usuario, session_factory=fabrica)
    assert est.pnl_realizado_dia == pytest.approx(5.0)
    assert est.cantidad_disponible(SIMBOLO) == pytest.approx(0.0005)
    assert est.posiciones[SIMBOLO].coste_medio == pytest.approx(100000.0)


# ═══ 12 · EL BROKER NUNCA RECIBE UNA OPERACION RECHAZADA ═════════════════════
class BrokerEspia:
    def __init__(self):
        self.llamadas = 0

    def comprar(self, symbol, quote_amount):
        self.llamadas += 1
        raise AssertionError("el broker no deberia recibir nada")

    def vender(self, symbol, base_quantity):
        self.llamadas += 1
        raise AssertionError("el broker no deberia recibir nada")


def test_12_operacion_rechazada_no_llega_al_broker(fabrica, usuario):
    espia = BrokerEspia()
    motor = MotorRiesgo(config=config(perdida_max=20.0))
    d = motor.evaluar(propuesta(), capital_disponible=1000.0, estado=estado(pnl=-50.0))

    assert d.aprobado is False
    # El flujo real solo ejecuta si aprobado; se reproduce esa condicion.
    if d.aprobado:
        ejecutar_y_registrar_compra(trader=espia, usuario_id=usuario, symbol=SIMBOLO,
                                    quote_amount=d.approved_quote_amount,
                                    session_factory=fabrica)
    assert espia.llamadas == 0
    with fabrica() as db:
        assert db.query(models.Transaction).count() == 0


# ═══ 13 · REGRESION P0-8 ═════════════════════════════════════════════════════
def test_13_regresion_p0_8_el_modelo_ya_no_fija_el_importe():
    """
    Antes: quote_amount = precio * quantity_de_GPT. Con quantity=10 y BTC a
    100.000 eso eran 1.000.000 USDT. Ahora el motor lo ignora por completo.
    """
    cantidad_gpt = 10.0
    importe_antiguo = PRECIO * cantidad_gpt          # 1.000.000 USDT
    assert importe_antiguo == pytest.approx(1_000_000.0)

    motor = MotorRiesgo(config=config(monto_max=20.0))
    d = motor.evaluar(propuesta(cantidad=cantidad_gpt),
                      capital_disponible=1_000_000.0, estado=estado())

    assert d.approved_quote_amount == pytest.approx(20.0)
    assert d.approved_quote_amount < importe_antiguo / 1000


def test_13b_la_ejecucion_no_deriva_el_importe_de_la_cantidad_del_modelo():
    """AST: la ejecucion usa el veredicto del motor, no precio * base_quantity."""
    ruta = Path(RAIZ, "backend", "portafolio", "carteras.py")
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    encontradas = 0
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Call)
                and getattr(nodo.func, "id", None) in ("ejecutar_y_registrar_compra",
                                                       "ejecutar_y_registrar_venta")):
            continue
        for kw in nodo.keywords:
            if kw.arg in ("quote_amount", "base_quantity"):
                encontradas += 1
                assert isinstance(kw.value, ast.Attribute), (
                    f"{kw.arg} debe venir del veredicto del motor, no de una expresion"
                )
                assert kw.value.attr.startswith("approved_"), (
                    f"{kw.arg}={kw.value.attr}: debe ser un campo approved_* del motor"
                )
    # Sin esto la prueba pasaria vacuamente si la ejecucion se moviera de sitio.
    assert encontradas == 2, (
        f"se esperaban 2 importes (compra y venta) tomados del veredicto, "
        f"se encontraron {encontradas} en {ruta.name}"
    )


# ═══ 14 · REGRESION P0-6 ═════════════════════════════════════════════════════
def test_14_regresion_p0_6_max_daily_loss_ahora_si_bloquea():
    """Antes MAX_DAILY_LOSS no aparecia en ningun .py; no afectaba a nada."""
    fuentes = [p for p in (RAIZ / "backend").rglob("*.py")]
    usos = [p for p in fuentes
            if "MAX_DAILY_LOSS_USDT" in p.read_text(encoding="utf-8", errors="replace")]
    assert usos, "MAX_DAILY_LOSS_USDT debe existir en el codigo"

    motor = MotorRiesgo(config=config(perdida_max=20.0))
    sin_perdida = motor.evaluar(propuesta(), capital_disponible=1000.0, estado=estado(pnl=0.0))
    con_perdida = motor.evaluar(propuesta(), capital_disponible=1000.0, estado=estado(pnl=-25.0))

    assert sin_perdida.aprobado is True
    assert con_perdida.aprobado is False, "ahora si bloquea el aumento de exposicion"
    assert con_perdida.limite_violado == "MAX_DAILY_LOSS_USDT"


# ═══ 15 · INTEGRACION ESTRUCTURAL ════════════════════════════════════════════
def test_15_ninguna_ejecucion_sin_veredicto_aprobado():
    """
    AST: dentro de trading_loop, toda llamada a ejecutar_y_registrar_* debe
    estar dominada por una comprobacion de `veredicto.aprobado`, y el motor
    debe invocarse antes.
    """
    arbol = ast.parse(Path(RAIZ, "backend", "main.py").read_text(encoding="utf-8"))
    bucle = next(n for n in ast.walk(arbol)
                 if isinstance(n, ast.FunctionDef) and n.name == "trading_loop")

    evaluaciones = [n for n in ast.walk(bucle)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == "evaluar"]
    assert evaluaciones, "trading_loop debe invocar al motor de riesgo"

    # Tras P0-15 la ejecucion pasa por la cartera del modo activo.
    ejecuciones = [n for n in ast.walk(bucle)
                   if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute)
                   and n.func.attr == "ejecutar"]
    assert ejecuciones, "no se encontro ninguna ejecucion en trading_loop"

    # Ninguna ejecucion puede alcanzarse sin veredicto: el patron es
    # `if not veredicto.aprobado: ... continue` antes de ejecutar.
    guardas = [n for n in ast.walk(bucle)
               if isinstance(n, ast.If) and "aprobado" in ast.dump(n.test)]
    assert guardas, "debe existir un guard sobre veredicto.aprobado"
    assert any(isinstance(s, ast.Continue) for g in guardas for s in ast.walk(g)), (
        "el guard del veredicto debe cortar el flujo con continue antes de ejecutar"
    )

    # Y el guard debe aparecer ANTES que la ejecucion en el cuerpo del bucle.
    linea_guard = min(g.lineno for g in guardas)
    linea_exec = min(e.lineno for e in ejecuciones)
    assert linea_guard < linea_exec, (
        f"el guard del veredicto (linea {linea_guard}) debe preceder a la "
        f"ejecucion (linea {linea_exec})"
    )


def test_15b_el_motor_se_instancia_una_sola_vez_y_es_obligatorio():
    fuente = Path(RAIZ, "backend", "main.py").read_text(encoding="utf-8")
    assert "motor_riesgo = MotorRiesgo()" in fuente
    assert "motor_riesgo.evaluar(" in fuente


# ═══ Extra · el rechazo se audita sin parecer una transaccion ════════════════
def test_el_rechazo_se_audita_con_cantidad_cero():
    fuente = Path(RAIZ, "backend", "main.py").read_text(encoding="utf-8")
    assert "RECHAZADA_RIESGO" in fuente
    arbol = ast.parse(fuente)
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "registrar_rechazo_riesgo")
    llamada = next(n for n in ast.walk(fn)
                   if isinstance(n, ast.Call)
                   and getattr(n.func, "id", None) == "guardar_auditoria_decision")
    kwargs = {k.arg: k.value for k in llamada.keywords}
    assert isinstance(kwargs["quantity"], ast.Constant) and kwargs["quantity"].value == 0.0, \
        "un rechazo jamas puede registrarse con cantidad distinta de cero"
