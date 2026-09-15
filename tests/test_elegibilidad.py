"""
Fase BOT 2.0-03A · Eligibility Gate deterministico antes de IA.

CASO EMPIRICO QUE MOTIVA LA FASE (ciclo PAPER real de 02B)

    GPT analizo          484 activos / 14.521 tokens de entrada
    decidio              BUY ETCUSDT
    RiskEngine autorizo  0,400000 USDT
    minNotional Binance  5,000000 USDT
    resultado            RECHAZADA_RIESGO / min_notional

El motor actuo bien. El desperdicio era anterior: se pago el analisis de IA de
un candidato demostrablemente inejecutable.

Todo aqui es aritmetica pura: sin red, sin IA, sin BD, sin aleatoriedad.
"""
import ast
import pathlib
import threading
from decimal import Decimal
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from backend.risk import elegibilidad as el
from backend.risk import reloj
from backend.risk.estado import EstadoRiesgo, Posicion
from backend.risk.motor import Lado, MotorRiesgo, PropuestaOperacion

RAIZ = pathlib.Path(__file__).resolve().parents[1]
GATE = RAIZ / "backend" / "risk" / "elegibilidad.py"
MAIN = RAIZ / "backend" / "main.py"


# Centinela: permite pedir explicitamente `filters=None`, que es distinto de
# "usa los filtros por defecto".
POR_DEFECTO = object()


def simbolo(*, status="TRADING", spot=True, min_qty="0.00001",
            max_qty="9000.00000000", step="0.00001", min_notional="5.00000000",
            nombre="XUSDT", filtros=POR_DEFECTO):
    """Entrada de exchange_info a medida."""
    info = {"symbol": nombre, "baseAsset": "X", "quoteAsset": "USDT",
            "status": status, "isSpotTradingAllowed": spot}
    info["filters"] = [
        {"filterType": "LOT_SIZE", "minQty": min_qty, "maxQty": max_qty,
         "stepSize": step},
        {"filterType": "NOTIONAL", "minNotional": min_notional},
    ] if filtros is POR_DEFECTO else filtros
    return info


def _metricas_sanas(precios):
    """
    Metricas de ticker/24hr que pasan todos los filtros duros del scanner (03B).

    Se generan a partir del precio de cada simbolo para que los fixtures del
    bucle sigan midiendo lo que median antes del scanner.
    """
    return {s: {"lastPrice": str(p), "bidPrice": str(p * 0.9995),
                "askPrice": str(p * 1.0005), "quoteVolume": "1000000",
                "count": "5000", "highPrice": str(p * 1.05),
                "lowPrice": str(p), "priceChangePercent": "2.5"}
            for s, p in precios.items()}


def estado_vacio():
    return EstadoRiesgo(dia=reloj.dia_de_riesgo())


# ═══════════════════════════════════════════════════════════════════════════
# 1 · max_notional < min_notional  → INELEGIBLE
# ═══════════════════════════════════════════════════════════════════════════
def test_1_el_caso_real_de_etcusdt_queda_inelegible():
    """Reproduce el desperdicio observado: 0,40 autorizado contra 5,00 minimo."""
    v = el.evaluar_compra("ETCUSDT", symbol_info=simbolo(nombre="ETCUSDT"),
                          precio=100.0, max_notional_autorizado=0.4)

    assert v.elegible is False
    assert v.motivo == el.MIN_NOTIONAL_INALCANZABLE
    assert v.max_notional_autorizado == 0.4
    assert v.min_notional == 5.0
    assert v.notional_minimo_valido >= 5.0, \
        "debe informar cuanto haria falta, sin autorizarlo"


def test_1b_el_motivo_es_un_codigo_estable_no_un_texto():
    v = el.evaluar_compra("XUSDT", symbol_info=simbolo(), precio=100.0,
                          max_notional_autorizado=0.4)
    assert v.motivo in el.MOTIVOS
    assert v.motivo.isupper() and " " not in v.motivo


# ═══════════════════════════════════════════════════════════════════════════
# 2 · La cantidad minima cabe EXACTAMENTE en el riesgo  → ELEGIBLE
# ═══════════════════════════════════════════════════════════════════════════
def test_2_cabe_exactamente_en_el_riesgo():
    v = el.evaluar_compra("XUSDT",
                          symbol_info=simbolo(min_qty="1", max_qty="1000",
                                              step="1", min_notional="5"),
                          precio=1.0, max_notional_autorizado=5.0)

    assert v.elegible is True
    assert v.motivo == el.ELEGIBLE
    assert v.cantidad_minima_valida == 5.0
    assert v.notional_minimo_valido == 5.0
    assert v.notional_minimo_valido <= v.max_notional_autorizado


def test_2b_un_centimo_menos_de_riesgo_lo_vuelve_inelegible():
    """La frontera es exacta, no aproximada."""
    comun = dict(symbol_info=simbolo(min_qty="1", max_qty="1000", step="1",
                                     min_notional="5"), precio=1.0)
    assert el.evaluar_compra("XUSDT", max_notional_autorizado=5.0, **comun).elegible
    assert not el.evaluar_compra("XUSDT", max_notional_autorizado=4.99, **comun).elegible


# ═══════════════════════════════════════════════════════════════════════════
# 3 · stepSize impide alcanzar minNotional sin superar el riesgo
# ═══════════════════════════════════════════════════════════════════════════
def test_3_el_escalon_obliga_a_saltar_por_encima_del_riesgo():
    """
    minNotional 5, precio 4,99999999 y paso 1.

    q=1 daria notional 4,99999999 -> NO alcanza el minimo.
    q=2 daria notional 9,99999998 -> supera lo autorizado (5).
    No existe cantidad valida.
    """
    v = el.evaluar_compra("XUSDT",
                          symbol_info=simbolo(min_qty="1", max_qty="1000",
                                              step="1", min_notional="5"),
                          precio="4.99999999", max_notional_autorizado=5.0)

    assert v.elegible is False
    assert v.motivo == el.LOT_SIZE_INCOMPATIBLE
    assert v.cantidad_minima_valida == 2.0, "el escalon fuerza saltar a 2"
    assert v.notional_minimo_valido > v.max_notional_autorizado


def test_3b_un_notional_de_4_99999999_no_puede_pasar_por_5():
    """
    La trampa que exige Decimal: con float, 1 * 4.99999999 comparado de forma
    laxa podria darse por bueno frente a un minimo de 5.
    """
    v = el.evaluar_compra("XUSDT",
                          symbol_info=simbolo(min_qty="1", max_qty="1000",
                                              step="1", min_notional="5"),
                          precio="4.99999999", max_notional_autorizado=5.0)
    assert v.elegible is False
    # Y la cantidad que SI seria valida nunca es la que se queda corta.
    assert v.cantidad_minima_valida != 1.0


def test_3c_el_piso_al_paso_es_exacto_con_decimal():
    """
    Con float, floor(0.3 / 0.1) da 2 porque 0.3/0.1 == 2.9999999999999996.
    Con Decimal da 3. Un error asi convertiria una cantidad valida en otra
    distinta y podria mover dinero sobre una orden que el exchange rechaza.
    """
    import math

    assert math.floor(0.3 / 0.1) == 2, "asi de mal se porta el float"
    assert el._piso_a_paso(Decimal("0.3"), Decimal("0.1")) == Decimal("0.3")
    assert el._techo_a_paso(Decimal("0.3"), Decimal("0.1")) == Decimal("0.3")
    assert el._piso_a_paso(Decimal("0.35"), Decimal("0.1")) == Decimal("0.3")
    assert el._techo_a_paso(Decimal("0.31"), Decimal("0.1")) == Decimal("0.4")


def test_3d_el_precio_se_convierte_desde_texto_no_desde_binario():
    """`Decimal(0.1)` arrastra el error binario; `Decimal("0.1")` no."""
    assert el._a_decimal(0.1) == Decimal("0.1")
    assert el._a_decimal("0.1") == Decimal("0.1")
    assert el._a_decimal(0.1) != Decimal(0.1)


def test_3e_la_cuantizacion_replica_la_de_la_ejecucion_y_nunca_sube():
    """
    La ejecucion trunca a 6 decimales (`round(q - q % step, 6)`). El gate hace
    lo mismo pero SIEMPRE a la baja: subir significaria superar el autorizado.
    """
    q = el._como_ejecutaria(Decimal("0.0000019"), Decimal("0.0000001"))
    assert q == Decimal("0.000001"), "trunca, no redondea al alza"
    assert q <= Decimal("0.0000019")


# ═══════════════════════════════════════════════════════════════════════════
# 4 · minQty fuerza un notional superior al maximo
# ═══════════════════════════════════════════════════════════════════════════
def test_4_min_qty_excede_el_riesgo():
    v = el.evaluar_compra("XUSDT",
                          symbol_info=simbolo(min_qty="100", max_qty="1000",
                                              step="1", min_notional="1"),
                          precio=1.0, max_notional_autorizado=50.0)

    assert v.elegible is False
    assert v.motivo == el.MIN_QTY_INALCANZABLE
    assert v.cantidad_minima_valida == 100.0
    assert v.notional_minimo_valido == 100.0 > v.max_notional_autorizado


def test_4b_max_qty_puede_impedir_alcanzar_el_minimo():
    """maxQty por debajo de la cantidad que exige minNotional."""
    v = el.evaluar_compra("XUSDT",
                          symbol_info=simbolo(min_qty="1", max_qty="3",
                                              step="1", min_notional="10"),
                          precio=1.0, max_notional_autorizado=1000.0)
    assert v.elegible is False
    assert v.motivo == el.MAX_QTY_INCOMPATIBLE


def test_4c_max_qty_acota_la_cantidad_pero_permite_operar():
    v = el.evaluar_compra("XUSDT",
                          symbol_info=simbolo(min_qty="1", max_qty="20",
                                              step="1", min_notional="10"),
                          precio=1.0, max_notional_autorizado=1000.0)
    assert v.elegible is True


# ═══════════════════════════════════════════════════════════════════════════
# 5-7 · PRECIO, TRADING, SPOT
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("precio", [None, 0, 0.0, -1.0, "0", float("nan"),
                                    float("inf"), "no-es-un-numero", ""])
def test_5_precio_ausente_o_invalido_es_inelegible(precio):
    v = el.evaluar_compra("XUSDT", symbol_info=simbolo(), precio=precio,
                          max_notional_autorizado=1000.0)
    assert v.elegible is False
    assert v.motivo == el.SIN_PRECIO


def test_6_simbolo_que_no_cotiza_es_inelegible():
    for estado in ("BREAK", "HALT", "PENDING_TRADING", None, ""):
        v = el.evaluar_compra("XUSDT", symbol_info=simbolo(status=estado),
                              precio=100.0, max_notional_autorizado=1000.0)
        assert v.elegible is False and v.motivo == el.NO_TRADING


def test_7_spot_no_permitido_es_inelegible():
    v = el.evaluar_compra("XUSDT", symbol_info=simbolo(spot=False), precio=100.0,
                          max_notional_autorizado=1000.0)
    assert v.elegible is False
    assert v.motivo == el.NO_SPOT


# ═══════════════════════════════════════════════════════════════════════════
# 8 · FILTROS INCOMPLETOS  → FAIL-CLOSED
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("filtros,caso", [
    ([], "sin filtros"),
    (None, "filters ausente"),
    ("no-es-una-lista", "filters no iterable"),
    ([{"filterType": "NOTIONAL", "minNotional": "5"}], "sin LOT_SIZE"),
    ([{"filterType": "LOT_SIZE", "minQty": "1", "maxQty": "9", "stepSize": "1"}],
     "sin NOTIONAL"),
    ([{"filterType": "LOT_SIZE", "minQty": "1", "maxQty": "9"},
      {"filterType": "NOTIONAL", "minNotional": "5"}], "LOT_SIZE sin stepSize"),
    ([{"filterType": "LOT_SIZE", "minQty": "1", "maxQty": "9", "stepSize": "0"},
      {"filterType": "NOTIONAL", "minNotional": "5"}], "stepSize cero"),
    ([{"filterType": "LOT_SIZE", "minQty": "x", "maxQty": "9", "stepSize": "1"},
      {"filterType": "NOTIONAL", "minNotional": "5"}], "minQty ilegible"),
    ([{"filterType": "LOT_SIZE", "minQty": "10", "maxQty": "1", "stepSize": "1"},
      {"filterType": "NOTIONAL", "minNotional": "5"}], "maxQty < minQty"),
])
def test_8_filtros_incompletos_son_fail_closed(filtros, caso):
    """
    Sin filtros no se puede DEMOSTRAR que la orden seria valida, asi que no se
    gasta IA en el candidato. La direccion segura es no comprar.
    """
    v = el.evaluar_compra("XUSDT", symbol_info=simbolo(filtros=filtros),
                          precio=100.0, max_notional_autorizado=1000.0)
    assert v.elegible is False, caso
    assert v.motivo == el.FILTROS_INVALIDOS, caso


def test_8b_min_notional_legacy_tambien_se_acepta():
    """Binance migro MIN_NOTIONAL a NOTIONAL; el bucle acepta ambos."""
    v = el.evaluar_compra("XUSDT", symbol_info=simbolo(filtros=[
        {"filterType": "LOT_SIZE", "minQty": "1", "maxQty": "1000", "stepSize": "1"},
        {"filterType": "MIN_NOTIONAL", "minNotional": "5"}]),
        precio=1.0, max_notional_autorizado=10.0)
    assert v.elegible is True
    assert v.min_notional == 5.0


def test_8c_symbol_info_ausente_es_fail_closed():
    for info in (None, {}, "texto", 42):
        v = el.evaluar_compra("XUSDT", symbol_info=info, precio=100.0,
                              max_notional_autorizado=1000.0)
        assert v.elegible is False


def test_8d_capital_o_riesgo_no_utilizable_es_inelegible():
    for autorizado in (0, 0.0, -5.0, None, float("nan"), float("inf")):
        v = el.evaluar_compra("XUSDT", symbol_info=simbolo(), precio=100.0,
                              max_notional_autorizado=autorizado)
        assert v.elegible is False
        assert v.motivo == el.CAPITAL_RIESGO_INSUFICIENTE


def test_8e_riesgo_que_no_alcanza_ni_un_step():
    """
    Una sola unidad cuesta 1.000 y solo hay 10 autorizados. minNotional (1) SI
    cabria, asi que la causa primaria es la cantidad minima del lote, no el
    minimo del exchange.
    """
    v = el.evaluar_compra("XUSDT",
                          symbol_info=simbolo(min_qty="1", max_qty="1000",
                                              step="1", min_notional="1"),
                          precio=1000.0, max_notional_autorizado=10.0)
    assert v.elegible is False
    assert v.motivo == el.MIN_QTY_INALCANZABLE
    assert v.cantidad_minima_valida == 1.0
    assert v.notional_minimo_valido == 1000.0


def test_8f_la_precedencia_pone_min_notional_por_delante():
    """
    Regla auditada contra Binance: si el minimo del exchange no cabe en el
    riesgo, ESA es la causa primaria, aunque tambien falle la granularidad.

    Es el caso de BTCUSDT: minNotional 5 contra 0,40 autorizados, y ademas
    0,40/64.083 no alcanza ni un stepSize. Una version anterior devolvia
    LOT_SIZE_INCOMPATIBLE para 40 simbolos asi.
    """
    v = el.evaluar_compra("BTCUSDT",
                          symbol_info=simbolo(nombre="BTCUSDT",
                                              min_qty="0.00001",
                                              max_qty="9000",
                                              step="0.00001",
                                              min_notional="5"),
                          precio="64083.29", max_notional_autorizado=0.4)
    assert v.elegible is False
    assert v.motivo == el.MIN_NOTIONAL_INALCANZABLE, (
        "con minNotional > autorizado la causa primaria es el notional")
    # Y ahora el diagnostico esta completo, no a None.
    assert v.cantidad_minima_valida == 0.00008
    assert v.notional_minimo_valido > 5.0


def test_8g_lot_size_solo_cuando_ambos_minimos_cabrian():
    """
    LOT_SIZE_INCOMPATIBLE significa: el notional cabria y la cantidad minima
    tambien, pero ningun multiplo de stepSize satisface los dos a la vez.
    """
    v = el.evaluar_compra("XUSDT",
                          symbol_info=simbolo(min_qty="1", max_qty="1000",
                                              step="1", min_notional="5"),
                          precio="4.99999999", max_notional_autorizado=5.0)
    assert v.motivo == el.LOT_SIZE_INCOMPATIBLE
    f = el.leer_filtros(simbolo(min_qty="1", max_qty="1000", step="1",
                                min_notional="5"))
    assert float(f.min_notional) <= v.max_notional_autorizado,         "el notional minimo SI cabia"
    assert float(f.min_qty) * 4.99999999 <= v.max_notional_autorizado,         "la cantidad minima SI cabia"


# ═══════════════════════════════════════════════════════════════════════════
# 9 · NUNCA SE AUMENTA EL TAMANO PARA ALCANZAR minNotional
# ═══════════════════════════════════════════════════════════════════════════
def test_9_no_se_eleva_el_tamano_para_llegar_al_minimo():
    """
    El gate informa cuanto haria falta, pero eso NO lo convierte en elegible.
    Es la misma negativa que el MotorRiesgo: "no se aumenta el tamano para
    alcanzarlo".
    """
    v = el.evaluar_compra("XUSDT", symbol_info=simbolo(min_notional="5"),
                          precio=100.0, max_notional_autorizado=0.4)

    assert v.elegible is False
    assert v.notional_minimo_valido > v.max_notional_autorizado, \
        "se conoce el importe necesario y se rechaza igualmente"
    assert v.max_notional_autorizado == 0.4, "el autorizado no se ha tocado"


def test_9b_ningun_veredicto_elegible_supera_el_importe_autorizado():
    """Barrido: si es elegible, el notional minimo SIEMPRE cabe."""
    for precio in ("0.45", "1", "9.99", "100", "3000.5", "100000"):
        for autorizado in (0.4, 5.0, 20.0, 100.0, 1000.0):
            v = el.evaluar_compra("XUSDT", symbol_info=simbolo(min_notional="5"),
                                  precio=precio,
                                  max_notional_autorizado=autorizado)
            if v.elegible:
                assert v.notional_minimo_valido <= v.max_notional_autorizado
                assert v.notional_minimo_valido >= v.min_notional


# ═══════════════════════════════════════════════════════════════════════════
# 10 · UNA SOLA ARITMETICA DE RIESGO
# ═══════════════════════════════════════════════════════════════════════════
def test_10_el_gate_y_el_motor_usan_el_mismo_importe():
    """
    El gate no recalcula nada: pide el importe a `MotorRiesgo.limite_compra`, la
    misma llamada que usa `_evaluar_compra` para decidir.
    """
    motor = MotorRiesgo()
    estado = estado_vacio()
    capital = 1000.0

    lim = motor.limite_compra(capital_disponible=capital, estado=estado,
                              symbol="XUSDT")
    decision = motor.evaluar(
        PropuestaOperacion(symbol="XUSDT", side=Lado.COMPRA, precio=1.0,
                           base_quantity_modelo=999.0, min_notional=0.0),
        capital_disponible=capital, estado=estado)

    assert decision.aprobado is True
    assert decision.approved_quote_amount == lim.quote_permitido, \
        "el motor debe autorizar exactamente lo que limite_compra anuncia"


def test_10b_el_limite_que_manda_coincide_con_el_del_rechazo():
    motor = MotorRiesgo()
    estado = estado_vacio()
    lim = motor.limite_compra(capital_disponible=20.0, estado=estado,
                              symbol="XUSDT")
    decision = motor.evaluar(
        PropuestaOperacion(symbol="XUSDT", side=Lado.COMPRA, precio=100.0,
                           min_notional=5.0),
        capital_disponible=20.0, estado=estado)

    assert decision.aprobado is False
    assert decision.limite_violado == "min_notional"
    # El importe citado en el rechazo es el de limite_compra.
    assert f"{lim.quote_permitido:.6f}" in decision.motivo


def test_10c_la_exposicion_existente_reduce_el_importe_en_ambos():
    motor = MotorRiesgo()
    con_posicion = EstadoRiesgo(
        dia=reloj.dia_de_riesgo(),
        posiciones={"XUSDT": Posicion(cantidad=1.0, coste_medio=49.0)})

    lim = motor.limite_compra(capital_disponible=1000.0, estado=con_posicion,
                              symbol="XUSDT")
    assert lim.limite == "MAX_EXPOSICION_POR_ACTIVO_USDT"
    assert lim.quote_permitido == pytest.approx(1.0)

    v = el.evaluar_compra("XUSDT", symbol_info=simbolo(min_notional="5"),
                          precio=100.0,
                          max_notional_autorizado=lim.quote_permitido)
    assert v.elegible is False and v.motivo == el.MIN_NOTIONAL_INALCANZABLE


def test_10d_el_gate_no_contiene_ninguna_formula_de_riesgo():
    """
    Guarda estructural: los limites de riesgo NO pueden aparecer en el gate. Si
    alguien los copia aqui, habria dos aritmeticas que podrian divergir.
    """
    fuente = GATE.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    identificadores = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            identificadores.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            identificadores.add(nodo.attr)

    for prohibido in ("MONTO_MAXIMO_USDT", "LIMITE_ASIGNACION_POR_OPERACION",
                      "MAX_EXPOSICION_TOTAL_USDT", "MAX_EXPOSICION_POR_ACTIVO_USDT",
                      "MAX_DAILY_LOSS_USDT", "settings", "exposicion_total",
                      "exposicion_de", "pnl_realizado_dia"):
        assert prohibido not in identificadores, (
            f"el gate no puede replicar el riesgo ({prohibido}); debe pedirlo a "
            f"MotorRiesgo.limite_compra")


def test_10e_el_gate_es_puro_no_toca_red_ni_bd():
    arbol = ast.parse(GATE.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            volcado = ast.dump(nodo)
            for prohibido in ("requests", "binance", "database", "SessionLocal",
                              "models", "openai", "telemetria"):
                assert prohibido not in volcado, \
                    f"el gate debe ser puro; importa {prohibido}"


# ═══════════════════════════════════════════════════════════════════════════
# 11 · UNA POSICION ABIERTA NUNCA DESAPARECE POR UN FILTRO DE COMPRA
# ═══════════════════════════════════════════════════════════════════════════
class _Parar(BaseException):
    """Corta el `while True` sin pasar por su `except Exception`."""


SIMBOLOS_CICLO = [
    {"symbol": "CAROUSDT", "baseAsset": "CARO", "quoteAsset": "USDT",
     "status": "TRADING", "isSpotTradingAllowed": True,
     "filters": [{"filterType": "LOT_SIZE", "minQty": "0.00001",
                  "maxQty": "9000", "stepSize": "0.00001"},
                 # Minimo alto: con 0,40 autorizado JAMAS es elegible para comprar.
                 {"filterType": "NOTIONAL", "minNotional": "5.00000000"}]},
    {"symbol": "BARATOUSDT", "baseAsset": "BARATO", "quoteAsset": "USDT",
     "status": "TRADING", "isSpotTradingAllowed": True,
     "filters": [{"filterType": "LOT_SIZE", "minQty": "0.00001",
                  "maxQty": "9000", "stepSize": "0.00001"},
                 {"filterType": "NOTIONAL", "minNotional": "0.10000000"}]},
]


@pytest.fixture
def ciclo(monkeypatch):
    """trading_loop sobre dobles, con posiciones configurables."""
    import backend.main as main
    from backend.config import settings
    from backend.utils import asset_collector as ac

    registro = {"llm": [], "iteraciones": 0}
    posiciones = {}
    capital = {"v": 20.0}

    monkeypatch.setattr(settings, "MODO_REAL", False)
    main.stop_trading.clear()
    monkeypatch.setattr(main.stop_trading, "wait", lambda _s: False)
    monkeypatch.setattr(ac.simulator, "positions", {}, raising=False)

    def contexto_falso():
        registro["iteraciones"] += 1
        if registro["iteraciones"] > 1:
            raise _Parar()
        return SimpleNamespace(usuario_id=1, estado={},
                               ultimos_movimientos={}, ultimos_precios_venta={})

    monkeypatch.setattr(main, "cargar_contexto_usuario", contexto_falso)
    monkeypatch.setattr(main.binance, "init_client", lambda: None)
    monkeypatch.setattr(main.binance, "get_price_snapshot",
                        lambda medicion=None: {"CAROUSDT": 100.0,
                                               "BARATOUSDT": 1.0})
    monkeypatch.setattr(main.binance, "get_market_metrics",
                        lambda medicion=None: _metricas_sanas(
                            {"CAROUSDT": 100.0, "BARATOUSDT": 1.0}))
    monkeypatch.setattr(main.binance, "get_multiple_prices",
                        lambda symbols, snapshot=None, medicion=None: {
                            s: (snapshot or {}).get(s) for s in symbols
                            if (snapshot or {}).get(s)})
    monkeypatch.setattr(main.news_connector, "obtener_noticias_combinadas",
                        lambda total=6, medidor=None: ["n1"])
    monkeypatch.setattr(main, "get_available_assets",
                        lambda medidor=None: (
                            [{"symbol": s["symbol"], "type": "crypto"}
                             for s in SIMBOLOS_CICLO],
                            [{"asset": "USDT", "free": "20.0", "locked": "0.0"}],
                            SIMBOLOS_CICLO))
    monkeypatch.setattr(main, "get_market_pairs",
                        lambda symbols_info=None, snapshot=None, medidor=None: [])
    monkeypatch.setattr(main, "mercado_ny_abierto", lambda: False)
    monkeypatch.setattr(main, "precio_medio_de", lambda estado, symbol: None)
    monkeypatch.setattr(main, "construir_cartera",
                        lambda **k: SimpleNamespace(
                            modo="PAPER",
                            capital_disponible=lambda: capital["v"],
                            cantidad_disponible=lambda s: posiciones.get(s, 0.0),
                            estado_riesgo=lambda: EstadoRiesgo(
                                dia=reloj.dia_de_riesgo())))
    monkeypatch.setattr(main.openai, "analyze_multiple_assets",
                        lambda *a, **k: (registro["llm"].append(
                            {"activos": a[0] if a else None} | k), ([], "sin json"))[1])

    from backend import telemetria_http
    monkeypatch.setattr(telemetria_http.MedidorCicloHttp, "volcar",
                        lambda self, **kw: 0)

    def ejecutar(**pos):
        posiciones.update(pos)
        with pytest.raises(_Parar):
            main.trading_loop()
        return registro

    ejecutar.capital = capital
    return ejecutar


def test_11_una_posicion_abierta_sobrevive_al_filtro_de_compra(ciclo):
    """
    CAROUSDT no es elegible para comprar (minNotional 5 contra 0,40 autorizado),
    pero hay posicion abierta: debe llegar al LLM para poder analizar su SALIDA.
    El bot nunca puede quedarse sin poder vender.
    """
    registro = ciclo(CAROUSDT=2.5)
    assert registro["llm"], "el ciclo debe llegar al LLM"
    enviados = {a["symbol"] for a in registro["llm"][0]["activos"]}

    assert "CAROUSDT" in enviados, (
        "una posicion abierta NO puede desaparecer por un filtro pensado para "
        "compras nuevas")
    caro = next(a for a in registro["llm"][0]["activos"]
                if a["symbol"] == "CAROUSDT")
    assert caro["position_quantity"] == 2.5


def test_11b_sin_posicion_el_inelegible_no_se_envia(ciclo):
    registro = ciclo()
    enviados = {a["symbol"] for a in registro["llm"][0]["activos"]}
    assert "CAROUSDT" not in enviados, "sin posicion y sin poder comprar: no se envia"
    assert "BARATOUSDT" in enviados, "este si puede producir una orden valida"


def test_11c_si_nada_es_elegible_ni_hay_posiciones_no_se_llama_al_llm(ciclo):
    """
    Comportamiento CORRECTO, no un fallo: sin candidato ejecutable no se gasta
    ni un token.
    """
    ciclo.capital["v"] = 1.0        # 1 * 0.02 = 0.02 USDT autorizados
    registro = ciclo()
    assert registro["llm"] == [], "no debe haber ninguna llamada al LLM"


def test_11d_el_universo_enviado_es_elegibles_mas_preservados(ciclo):
    registro = ciclo(CAROUSDT=1.0)
    enviados = {a["symbol"] for a in registro["llm"][0]["activos"]}
    assert enviados == {"CAROUSDT", "BARATOUSDT"}


def test_11e_el_gate_solo_se_aplica_a_quien_no_tiene_posicion():
    """Guarda AST: la rama de preservacion precede a la de elegibilidad."""
    arbol = ast.parse(MAIN.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "trading_loop")
    for nodo in ast.walk(fn):
        if not isinstance(nodo, ast.If):
            continue
        prueba = ast.dump(nodo.test)
        if "position_detected" not in prueba:
            continue
        cuerpo = "\n".join(ast.dump(n) for n in nodo.body)
        alterno = "\n".join(ast.dump(n) for n in nodo.orelse)
        if "preservar" in cuerpo:
            assert "evaluar_compra" in alterno, (
                "la elegibilidad de compra debe evaluarse SOLO en la rama sin "
                "posicion")
            assert "evaluar_compra" not in cuerpo
            return
    pytest.fail("no se encontro la rama que preserva las posiciones abiertas")


# ═══════════════════════════════════════════════════════════════════════════
# 12 · LA TELEMETRIA DEL GATE NO CAMBIA DECISIONES
# ═══════════════════════════════════════════════════════════════════════════
def test_12_el_resumen_no_lanza_con_entradas_absurdas():
    r = el.ResumenElegibilidad(universo=3)
    r.anotar(None)
    r.anotar(SimpleNamespace())
    r.anotar("no soy un veredicto")
    r.preservar(None)
    r.por_motivo = "corrompido"
    r.anotar(el.Veredicto("X", True, el.ELEGIBLE))
    assert isinstance(r.linea(), str)
    assert isinstance(r.linea(12), str)


def test_12b_los_contadores_cuadran():
    r = el.ResumenElegibilidad(universo=5)
    r.anotar(el.Veredicto("A", True, el.ELEGIBLE))
    r.anotar(el.Veredicto("B", True, el.ELEGIBLE))
    r.anotar(el.Veredicto("C", False, el.MIN_NOTIONAL_INALCANZABLE))
    r.preservar("D")

    assert r.elegibles_compra == 2
    assert r.descartados == 1
    assert r.preservados_venta == 1
    assert r.enviados == 3
    assert r.por_motivo == {el.ELEGIBLE: 2, el.MIN_NOTIONAL_INALCANZABLE: 1,
                            "POSICION_ABIERTA": 1}


def test_12c_la_linea_incluye_el_desglose_por_motivo():
    r = el.ResumenElegibilidad(universo=484)
    for _ in range(484):
        r.anotar(el.Veredicto("X", False, el.MIN_NOTIONAL_INALCANZABLE))
    linea = r.linea(9)
    assert "universo=484" in linea
    assert "elegibles_compra=0" in linea
    assert "a_GPT=0" in linea
    assert f"{el.MIN_NOTIONAL_INALCANZABLE}=484" in linea


def test_12d_un_contador_corrupto_no_altera_el_universo_enviado(ciclo, monkeypatch):
    """
    Contar no puede cambiar lo que se envia.

    Se corrompe el estado INTERNO del resumen -no se sustituye por un doble que
    lanza a proposito-, que es el fallo realista: el propio `anotar` revienta
    por dentro, se lo traga, y el universo tiene que salir identico.
    """
    class ResumenCorrupto(el.ResumenElegibilidad):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.por_motivo = "corrompido"      # dejara de ser contable

    import backend.main as main
    monkeypatch.setattr(main.elegibilidad, "ResumenElegibilidad", ResumenCorrupto)

    registro = ciclo(CAROUSDT=1.0)
    enviados = {a["symbol"] for a in registro["llm"][0]["activos"]}
    assert enviados == {"CAROUSDT", "BARATOUSDT"}, (
        "el universo debe ser el mismo que con los contadores sanos "
        "(ver test_11d)")


def test_12e_el_gate_no_persiste_nada():
    """03A sigue puro; la migracion 0006 pertenece exclusivamente a PAPER."""
    migracion_paper = RAIZ / "migrations" / "versions" / "0006_paper_ledger.py"
    assert migracion_paper.exists()
    texto = migracion_paper.read_text(encoding="utf-8").lower()
    assert "paper" in texto
    for termino in ("elegibilidad", "eligibility", "gate"):
        assert termino not in texto

    arbol = ast.parse(GATE.read_text(encoding="utf-8"))
    importados = "\n".join(ast.dump(n) for n in ast.walk(arbol)
                            if isinstance(n, (ast.Import, ast.ImportFrom)))
    for prohibido in ("alembic", "sqlalchemy", "database", "models"):
        assert prohibido not in importados.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 13-14 · EL ENTORNO NO CAMBIA
# ═══════════════════════════════════════════════════════════════════════════
def test_13_paper_intacto():
    from backend.config import settings
    assert settings.TRADING_MODE == "PAPER"
    assert settings.MODO_REAL is False


def test_14_import_safety_intacto(monkeypatch):
    conexiones, ddl = [], []
    original = sa.engine.Engine.connect
    monkeypatch.setattr(sa.engine.Engine, "connect",
                        lambda self, *a, **k: (conexiones.append(1),
                                               original(self, *a, **k))[1])
    monkeypatch.setattr(sa.MetaData, "create_all", lambda self, *a, **k: ddl.append(1))
    monkeypatch.setattr(sa.MetaData, "drop_all", lambda self, *a, **k: ddl.append(1))

    import importlib

    import backend.main
    importlib.reload(backend.main)

    assert conexiones == [] and ddl == []
    assert not [t for t in threading.enumerate() if t.name != "MainThread"]


def test_el_scheduling_y_la_cadencia_siguen_intactos():
    arbol = ast.parse(MAIN.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "trading_loop")

    incrementos = [n for n in ast.walk(fn) if isinstance(n, ast.AugAssign)
                   and isinstance(n.target, ast.Name) and n.target.id == "ciclo"]
    assert len(incrementos) == 5

    valores = [n.value.value for n in ast.walk(fn)
               if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "EVALUAR_CADA_N_CICLOS"
                       for t in n.targets)
               and isinstance(n.value, ast.Constant)]
    assert valores == [2]

    for nodo in ast.walk(fn):
        if isinstance(nodo, ast.Call) and getattr(nodo.func, "attr", None) == "sleep":
            assert ast.dump(nodo.args[0]) == ast.dump(
                ast.parse("settings.WAIT_TIME", mode="eval").body)


def test_el_gate_no_toca_el_prompt_ni_el_modelo():
    """El universo puede ser menor; la plantilla del prompt no cambia."""
    fuente = (RAIZ / "backend" / "connectors" / "apis" /
              "openai_connector.py").read_text(encoding="utf-8")
    assert "elegib" not in fuente.lower(), \
        "el conector del LLM no debe saber nada del gate"
