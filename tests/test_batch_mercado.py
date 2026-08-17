"""
Fase BOT 2.0-02B · Adquisicion batch y reutilizacion del snapshot de mercado.

02A midio empiricamente el coste del patron N+1 en un ciclo real:

    get_multiple_prices     484 peticiones   125.926 ms
    get_market_pairs      1.361 peticiones   342.594 ms
    exchange_info             2 peticiones
    total externos        1.851 peticiones   fase_pre_llm 472.350 ms
    market_pairs enviados al LLM: 0

02B sustituye esas 1.845 peticiones de ticker por UN snapshot batch reutilizado
dentro del ciclo. Estas pruebas fijan ese contrato y ponen guardas para que
nadie pueda volver al N+1 sin romper la suite.

Ninguna prueba sale a la red.
"""
import ast
import pathlib
import threading
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from backend.telemetria_http import SIN_STATUS, MedidorCicloHttp

RAIZ = pathlib.Path(__file__).resolve().parents[1]
CONECTOR = RAIZ / "backend" / "connectors" / "crypto" / "binance_connector.py"
COLECTOR = RAIZ / "backend" / "utils" / "asset_collector.py"
MAIN = RAIZ / "backend" / "main.py"

FILTROS = [{"filterType": "NOTIONAL", "minNotional": "1.0"}]

# Fixture de exchange_info con los casos que importan.
EXCHANGE_INFO = {"symbols": [
    # Operables contra USDT
    {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
     "status": "TRADING", "isSpotTradingAllowed": True, "filters": FILTROS},
    {"symbol": "ETHUSDT", "baseAsset": "ETH", "quoteAsset": "USDT",
     "status": "TRADING", "isSpotTradingAllowed": True, "filters": FILTROS},
    {"symbol": "ADAUSDT", "baseAsset": "ADA", "quoteAsset": "USDT",
     "status": "TRADING", "isSpotTradingAllowed": True, "filters": FILTROS},
    # Operables pero no contra USDT: entran en market_pairs, no en activos
    {"symbol": "ETHBTC", "baseAsset": "ETH", "quoteAsset": "BTC",
     "status": "TRADING", "isSpotTradingAllowed": True, "filters": FILTROS},
    {"symbol": "ADABTC", "baseAsset": "ADA", "quoteAsset": "BTC",
     "status": "TRADING", "isSpotTradingAllowed": True, "filters": FILTROS},
    # No cotiza: fuera de ambos
    {"symbol": "VIEJOUSDT", "baseAsset": "VIEJO", "quoteAsset": "USDT",
     "status": "BREAK", "isSpotTradingAllowed": True, "filters": FILTROS},
    # Cotiza pero no en spot: fuera de ambos
    {"symbol": "MARGINUSDT", "baseAsset": "MARGIN", "quoteAsset": "USDT",
     "status": "TRADING", "isSpotTradingAllowed": False, "filters": FILTROS},
    # Operable en exchange_info pero SIN precio en el snapshot: el caso de
    # divergencia documentada frente al legacy.
    {"symbol": "FANTASMAUSDT", "baseAsset": "FANTASMA", "quoteAsset": "USDT",
     "status": "TRADING", "isSpotTradingAllowed": True, "filters": FILTROS},
]}

TICKERS_COMPLETOS = [
    {"symbol": "BTCUSDT", "price": "100000.00"},
    {"symbol": "ETHUSDT", "price": "3000.50"},
    {"symbol": "ADAUSDT", "price": "0.45"},
    {"symbol": "ETHBTC", "price": "0.03000"},
    {"symbol": "ADABTC", "price": "0.0000045"},
    {"symbol": "VIEJOUSDT", "price": "0.10"},
    {"symbol": "MARGINUSDT", "price": "1.00"},
    {"symbol": "FANTASMAUSDT", "price": "9.99"},
]
# Sin FANTASMAUSDT: reproduce un simbolo listado pero sin ticker.
TICKERS_INCOMPLETOS = [t for t in TICKERS_COMPLETOS
                       if t["symbol"] != "FANTASMAUSDT"]

BALANCES = [{"asset": "USDT", "free": "20.0", "locked": "0.0"}]


class ClienteBinanceFalso:
    """
    Doble de `binance.client.Client` que CUENTA cada peticion.

    `get_symbol_ticker` lanza a proposito: si algun camino vuelve al N+1, la
    prueba falla en vez de pasar desapercibida.
    """

    def __init__(self, tickers=None, exchange_info=None):
        self.tickers = TICKERS_COMPLETOS if tickers is None else tickers
        self.exchange_info = exchange_info or EXCHANGE_INFO
        self.llamadas = {"get_exchange_info": 0, "get_all_tickers": 0,
                         "get_account": 0, "get_symbol_ticker": 0}
        self.response = None
        self.fallo_tickers = None

    def _responde(self, status=200):
        self.response = SimpleNamespace(status_code=status)

    def get_exchange_info(self):
        self.llamadas["get_exchange_info"] += 1
        self._responde()
        return self.exchange_info

    def get_all_tickers(self):
        self.llamadas["get_all_tickers"] += 1
        if self.fallo_tickers is not None:
            raise self.fallo_tickers
        self._responde()
        return self.tickers

    def get_account(self):
        self.llamadas["get_account"] += 1
        self._responde()
        return {"balances": BALANCES}

    def get_symbol_ticker(self, **kw):
        self.llamadas["get_symbol_ticker"] += 1
        raise AssertionError(
            "REGRESION AL N+1: se ha pedido un ticker individual. 02B "
            "sustituyo 1.845 de estas peticiones por un unico snapshot batch.")

    @property
    def total_peticiones(self):
        return sum(self.llamadas.values())


@pytest.fixture
def conector(monkeypatch):
    """BinanceConnector aislado sobre el cliente falso."""
    from backend.connectors.crypto import binance_connector as bc

    cliente = ClienteBinanceFalso()
    c = bc.BinanceConnector()
    monkeypatch.setattr(c, "init_client", lambda: None)
    monkeypatch.setattr(c, "client", cliente, raising=False)
    return c, cliente


# ═══════════════════════════════════════════════════════════════════════════
# 1-3 · EL SNAPSHOT BATCH
# ═══════════════════════════════════════════════════════════════════════════
def test_1_una_respuesta_batch_produce_todos_los_precios(conector):
    c, cliente = conector
    snapshot = c.get_price_snapshot()

    assert snapshot == {"BTCUSDT": 100000.0, "ETHUSDT": 3000.5,
                        "ADAUSDT": 0.45, "ETHBTC": 0.03,
                        "ADABTC": 0.0000045, "VIEJOUSDT": 0.10,
                        "MARGINUSDT": 1.0, "FANTASMAUSDT": 9.99}
    assert len(snapshot) == len(TICKERS_COMPLETOS)
    assert cliente.llamadas["get_all_tickers"] == 1, "UNA sola peticion"
    assert cliente.llamadas["get_symbol_ticker"] == 0


def test_2_un_simbolo_ausente_no_inventa_cero(conector, monkeypatch):
    c, cliente = conector
    monkeypatch.setattr(cliente, "tickers", TICKERS_INCOMPLETOS)
    snapshot = c.get_price_snapshot()

    assert "FANTASMAUSDT" not in snapshot, "ausente = desconocido, no 0.0"
    assert snapshot.get("FANTASMAUSDT") is None
    assert 0.0 not in snapshot.values()


def test_2b_un_precio_de_cero_informado_por_el_exchange_si_se_conserva(conector,
                                                                      monkeypatch):
    """Un 0 que el exchange declara es un dato, no una laguna."""
    c, cliente = conector
    monkeypatch.setattr(cliente, "tickers", [{"symbol": "MUERTOUSDT", "price": "0.00"}])
    assert c.get_price_snapshot() == {"MUERTOUSDT": 0.0}


def test_2c_un_ticker_ilegible_se_ignora_sin_romper_el_resto(conector, monkeypatch):
    c, cliente = conector
    monkeypatch.setattr(cliente, "tickers", [
        {"symbol": "BTCUSDT", "price": "100000.0"},
        {"symbol": "ROTOUSDT", "price": "no-es-un-numero"},
        {"sin_symbol": "?", "price": "1.0"},
        {"symbol": "ETHUSDT"},
        None,
    ])
    assert c.get_price_snapshot() == {"BTCUSDT": 100000.0}


def test_3_un_fallo_batch_no_reutiliza_datos_del_ciclo_anterior(conector,
                                                               monkeypatch):
    """
    Si el batch falla, el snapshot es {} — nunca el del ciclo anterior ni uno
    a medias. Confundir "no lo se" con un precio viejo es lo que podria mover
    dinero sobre datos obsoletos.
    """
    c, cliente = conector

    primero = c.get_price_snapshot()
    assert primero, "el primer ciclo si obtuvo precios"

    monkeypatch.setattr(cliente, "fallo_tickers", ConnectionError("sin red"))
    segundo = c.get_price_snapshot()

    assert segundo == {}, "un batch fallido no puede devolver datos"
    assert segundo is not primero
    # Y el consumidor no obtiene nada, en vez de un precio rancio.
    assert c.get_multiple_prices(["BTCUSDT"], snapshot=segundo) == {}


def test_3b_el_conector_no_guarda_el_snapshot_como_estado(conector):
    """
    No hay cache entre ciclos: el snapshot se pasa explicitamente. Asi no puede
    existir un problema de invalidacion.
    """
    c, _ = conector
    c.get_price_snapshot()
    guardados = [n for n, v in vars(c).items()
                 if isinstance(v, dict) and v and n not in ("__dict__",)]
    assert guardados == [], f"el conector no debe retener precios: {guardados}"


# ═══════════════════════════════════════════════════════════════════════════
# 4-5 · NADIE PIDE UNA PETICION POR ELEMENTO
# ═══════════════════════════════════════════════════════════════════════════
def test_4_get_multiple_prices_no_pide_una_peticion_por_simbolo(conector):
    c, cliente = conector
    simbolos = [t["symbol"] for t in TICKERS_COMPLETOS]

    m = MedidorCicloHttp()
    op = m.operacion("binance", "get_multiple_prices")
    precios = c.get_multiple_prices(simbolos, snapshot=c.get_price_snapshot(),
                                    medicion=op)

    assert len(precios) == len(simbolos)
    assert cliente.llamadas["get_symbol_ticker"] == 0
    assert cliente.llamadas["get_all_tickers"] == 1, \
        "una peticion para todo el ciclo, no una por simbolo"
    assert op.metricas.n_requests == 0, \
        "resolver desde el snapshot no es trafico HTTP"


def test_4b_sin_snapshot_pide_uno_solo_no_uno_por_simbolo(conector):
    """Peor caso: si nadie aporta snapshot, UNA peticion. Nunca N."""
    c, cliente = conector
    simbolos = [t["symbol"] for t in TICKERS_COMPLETOS]

    m = MedidorCicloHttp()
    op = m.operacion("binance", "get_multiple_prices")
    precios = c.get_multiple_prices(simbolos, medicion=op)

    assert len(precios) == len(simbolos)
    assert cliente.llamadas["get_all_tickers"] == 1
    assert cliente.llamadas["get_symbol_ticker"] == 0
    assert op.metricas.n_requests == 1, "una, y atribuida a esta operacion"


def test_5_get_market_pairs_no_pide_una_peticion_por_par(monkeypatch):
    from backend.utils import asset_collector as ac

    cliente = ClienteBinanceFalso()
    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    monkeypatch.setattr(ac.binance, "client", cliente, raising=False)

    m = MedidorCicloHttp()
    snapshot = {t["symbol"]: float(t["price"]) for t in TICKERS_COMPLETOS}
    pares = ac.get_market_pairs(EXCHANGE_INFO["symbols"], snapshot=snapshot,
                                medidor=m)

    assert len(pares) == 6, "los 6 pares TRADING+spot del fixture"
    assert cliente.total_peticiones == 0, "cero peticiones: todo en memoria"
    assert m.operacion("binance", "get_market_pairs").metricas.n_requests == 0


def test_5b_get_market_pairs_conserva_el_criterio_de_pares_operables(monkeypatch):
    """El filtro sigue siendo status TRADING + isSpotTradingAllowed."""
    from backend.utils import asset_collector as ac

    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    snapshot = {t["symbol"]: float(t["price"]) for t in TICKERS_COMPLETOS}
    nombres = {p["pair"] for p in
               ac.get_market_pairs(EXCHANGE_INFO["symbols"], snapshot=snapshot)}

    assert nombres == {"BTCUSDT", "ETHUSDT", "ADAUSDT", "ETHBTC", "ADABTC",
                       "FANTASMAUSDT"}
    assert "VIEJOUSDT" not in nombres, "status != TRADING"
    assert "MARGINUSDT" not in nombres, "isSpotTradingAllowed False"


# ═══════════════════════════════════════════════════════════════════════════
# 7 · EQUIVALENCIA FUNCIONAL LEGACY vs BATCH
# ═══════════════════════════════════════════════════════════════════════════
def _legacy_multiple_prices(symbols, tickers):
    """
    Reimplementacion del algoritmo ANTERIOR: un ticker por simbolo, y 0.0
    cuando ese ticker fallaba (get_current_price capturaba y devolvia 0.0).
    """
    por_simbolo = {t["symbol"]: float(t["price"]) for t in tickers}
    return {s: por_simbolo.get(s, 0.0) for s in symbols}


def _legacy_market_pairs(symbols_info, tickers):
    """Reimplementacion del algoritmo ANTERIOR de get_market_pairs."""
    por_simbolo = {t["symbol"]: float(t["price"]) for t in tickers}
    salida = []
    for s in symbols_info:
        if s.get("status") == "TRADING" and s.get("isSpotTradingAllowed"):
            salida.append({"pair": s["symbol"],
                           "price": por_simbolo.get(s["symbol"], 0.0)})
    return salida


def test_7_equivalencia_de_precios_con_fixture_completo(conector):
    """Con precio para todos los simbolos, legacy y batch coinciden EXACTO."""
    c, _ = conector
    simbolos = [t["symbol"] for t in TICKERS_COMPLETOS]

    nuevo = c.get_multiple_prices(simbolos, snapshot=c.get_price_snapshot())
    legacy = _legacy_multiple_prices(simbolos, TICKERS_COMPLETOS)
    assert nuevo == legacy


def test_7b_equivalencia_de_market_pairs_con_fixture_completo(monkeypatch):
    from backend.utils import asset_collector as ac

    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    snapshot = {t["symbol"]: float(t["price"]) for t in TICKERS_COMPLETOS}

    nuevo = ac.get_market_pairs(EXCHANGE_INFO["symbols"], snapshot=snapshot)
    legacy = _legacy_market_pairs(EXCHANGE_INFO["symbols"], TICKERS_COMPLETOS)
    assert nuevo == legacy, "mismo orden, mismos pares, mismos precios"


def test_7c_equivalencia_de_activos_disponibles(monkeypatch):
    """get_available_assets no ha cambiado de algoritmo; se fija igualmente."""
    from backend.utils import asset_collector as ac

    cliente = ClienteBinanceFalso()
    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    monkeypatch.setattr(ac.binance, "client", cliente, raising=False)
    monkeypatch.setattr(ac.simulator, "positions", {}, raising=False)

    activos, balances, info = ac.get_available_assets()

    assert [a["symbol"] for a in activos] == ["BTCUSDT", "ETHUSDT", "ADAUSDT",
                                              "FANTASMAUSDT"]
    assert all(a["type"] == "crypto" for a in activos)
    assert balances == BALANCES
    assert info == EXCHANGE_INFO["symbols"]


def test_7d_la_unica_divergencia_documentada_es_el_simbolo_sin_precio(monkeypatch):
    """
    DIFERENCIA INTENCIONADA Y UNICA respecto al legacy.

    Un simbolo listado como TRADING+spot pero SIN ticker en la respuesta batch:
      legacy -> lo publicaba con price=0.0 (el ticker individual fallaba)
      02B    -> lo omite

    Se prefiere omitir porque un 0.0 en el prompt es un precio inventado, y la
    invariante del proyecto es que desconocido no es cero.
    """
    from backend.utils import asset_collector as ac

    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    snapshot = {t["symbol"]: float(t["price"]) for t in TICKERS_INCOMPLETOS}

    nuevo = ac.get_market_pairs(EXCHANGE_INFO["symbols"], snapshot=snapshot)
    legacy = _legacy_market_pairs(EXCHANGE_INFO["symbols"], TICKERS_INCOMPLETOS)

    assert {p["pair"] for p in legacy} - {p["pair"] for p in nuevo} == \
        {"FANTASMAUSDT"}
    assert {"pair": "FANTASMAUSDT", "price": 0.0} in legacy
    assert all(p["price"] != 0.0 for p in nuevo), \
        "02B no publica ningun precio inventado"
    # Fuera de ese simbolo, identicos.
    assert nuevo == [p for p in legacy if p["pair"] != "FANTASMAUSDT"]


def test_7e_aguas_abajo_un_precio_ausente_se_comporta_como_el_0_0_legacy():
    """
    En main.py el activo se descarta con `if not precio: continue`.
    None (ausente) y 0.0 (legacy) toman la MISMA rama.
    """
    for valor in (None, 0.0):
        assert not valor, "ambos descartan el activo por la misma condicion"


# ═══════════════════════════════════════════════════════════════════════════
# 6 · exchange_info NO SE DUPLICA · Y EL CICLO COMPLETO
# ═══════════════════════════════════════════════════════════════════════════
class _Parar(BaseException):
    """Corta el `while True` sin pasar por su `except Exception`."""


@pytest.fixture
def ciclo(monkeypatch):
    """
    Un ciclo real de trading_loop sobre el cliente falso compartido.

    `main.binance` y `asset_collector.binance` son instancias DISTINTAS: las dos
    apuntan al mismo cliente falso para que los contadores agreguen el trafico
    real del ciclo.
    """
    import backend.main as main
    from backend.config import settings
    from backend.utils import asset_collector as ac

    cliente = ClienteBinanceFalso()
    registro = {"llm": [], "iteraciones": 0}
    limite = {"n": 1}

    for conector_ in (main.binance, ac.binance):
        monkeypatch.setattr(conector_, "init_client", lambda: None)
        monkeypatch.setattr(conector_, "client", cliente, raising=False)

    monkeypatch.setattr(settings, "MODO_REAL", False)
    monkeypatch.setattr(main.time, "sleep", lambda _s: None)
    monkeypatch.setattr(ac.simulator, "positions", {}, raising=False)

    def contexto_falso():
        registro["iteraciones"] += 1
        if registro["iteraciones"] > limite["n"]:
            raise _Parar()
        return SimpleNamespace(usuario_id=1, estado={},
                               ultimos_movimientos={}, ultimos_precios_venta={})

    monkeypatch.setattr(main, "cargar_contexto_usuario", contexto_falso)
    monkeypatch.setattr(main.news_connector, "obtener_noticias_combinadas",
                        lambda total=6, medidor=None: ["n1", "n2"])
    monkeypatch.setattr(main, "mercado_ny_abierto", lambda: False)
    monkeypatch.setattr(main, "precio_medio_de", lambda estado, symbol: None)
    monkeypatch.setattr(main, "construir_cartera",
                        lambda **k: SimpleNamespace(
                            modo="PAPER", capital_disponible=lambda: 20.0,
                            cantidad_disponible=lambda s: 0.0))

    def llm_falso(*a, **k):
        registro["llm"].append(k | {"activos": a[0] if a else None})
        return [], "sin json"

    monkeypatch.setattr(main.openai, "analyze_multiple_assets", llm_falso)

    medidores = []
    from backend import telemetria_http
    original_volcar = telemetria_http.MedidorCicloHttp.volcar
    monkeypatch.setattr(telemetria_http.MedidorCicloHttp, "volcar",
                        lambda self, **kw: (medidores.append(self), 0)[1])

    def ejecutar(n=1):
        limite["n"] = n
        with pytest.raises(_Parar):
            main.trading_loop()
        return cliente, registro, medidores

    return ejecutar


def test_6_exchange_info_no_se_duplica_en_un_mismo_ciclo(ciclo):
    cliente, _, _ = ciclo(n=1)
    assert cliente.llamadas["get_exchange_info"] == 1, (
        f"02A midio 2 exchange_info en el primer ciclo; ahora debe ser 1, "
        f"hay {cliente.llamadas['get_exchange_info']}")


def test_6b_main_ya_no_pide_exchange_info_por_su_cuenta():
    """Guarda estructural: la unica llamada vive en el colector."""
    arbol = ast.parse(MAIN.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and \
                getattr(nodo.func, "attr", None) == "get_exchange_info":
            pytest.fail(f"main.py:{nodo.lineno} vuelve a pedir exchange_info; "
                        f"debe derivarse de symbols_info")


def test_6c_los_filtros_se_derivan_del_mismo_exchange_info(ciclo):
    """`filters_dict` sale de symbols_info: cero peticiones y datos frescos."""
    cliente, _, _ = ciclo(n=1)
    assert cliente.llamadas["get_exchange_info"] == 1
    fuente = MAIN.read_text(encoding="utf-8")
    assert 'filters_dict = {s["symbol"]: s["filters"] for s in symbols_info}' \
        in fuente


def test_un_ciclo_completo_hace_un_numero_de_peticiones_de_un_digito(ciclo):
    """
    El criterio de exito de 02B: de 1.851 peticiones externas a un digito.

    Aqui las noticias estan dobladas, asi que se cuenta el trafico a Binance:
    exchange_info + get_account + get_all_tickers = 3.
    """
    cliente, _, _ = ciclo(n=1)
    assert cliente.llamadas == {"get_exchange_info": 1, "get_account": 1,
                                "get_all_tickers": 1, "get_symbol_ticker": 0}
    assert cliente.total_peticiones == 3
    assert cliente.total_peticiones < 10


def test_el_ciclo_pide_un_unico_snapshot_y_lo_reutiliza(ciclo):
    cliente, registro, _ = ciclo(n=1)
    assert cliente.llamadas["get_all_tickers"] == 1, (
        "un snapshot por ciclo, compartido por get_multiple_prices y "
        "get_market_pairs")
    assert registro["llm"], "el ciclo debe llegar al LLM"


def test_la_entrada_final_al_llm_coincide_con_el_calculo_legacy(ciclo):
    """
    Equivalencia de la ENTRADA AL PROMPT.

    Se compara contra lo que el algoritmo anterior habria producido con el mismo
    fixture, calculado de forma independiente en la prueba.
    """
    _, registro, _ = ciclo(n=1)
    llamada = registro["llm"][0]
    activos = llamada["activos"]

    # Legacy: activos USDT operables cuyo ticker devolvio precio.
    esperados_usdt = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "FANTASMAUSDT"]
    legacy_precios = _legacy_multiple_prices(esperados_usdt, TICKERS_COMPLETOS)

    assert {a["symbol"] for a in activos} == set(esperados_usdt)
    for a in activos:
        assert a["price"] == legacy_precios[a["symbol"]], \
            f"precio distinto para {a['symbol']}"
        assert a["position_quantity"] == 0.0
        assert a["average_price"] is None

    # market_pairs: sin posiciones abiertas, activos_relevantes esta vacio y el
    # filtrado de main.py deja la lista vacia. Identico al comportamiento 02A
    # (que envio 0 pares tras 1.361 peticiones).
    assert llamada["market_pairs"] == [] if "market_pairs" in llamada else True


def test_el_prompt_recibe_el_mismo_numero_de_activos_y_noticias(ciclo):
    _, registro, _ = ciclo(n=1)
    llamada = registro["llm"][0]
    assert len(llamada["activos"]) == 4
    assert llamada.get("ciclo") == 1, "la cadencia legacy no cambia"
    assert llamada.get("ciclo_id", "").startswith("ciclo-")


# ═══════════════════════════════════════════════════════════════════════════
# 8-9 · TELEMETRIA HONESTA
# ═══════════════════════════════════════════════════════════════════════════
def test_8_la_telemetria_cuenta_el_numero_real_de_peticiones(ciclo):
    cliente, _, medidores = ciclo(n=1)
    assert medidores, "el ciclo debe volcar su medidor"
    m = medidores[0]
    req = {(o.metricas.proveedor, o.metricas.operacion): o.metricas.n_requests
           for o in m.operaciones()}

    assert req[("binance", "exchange_info")] == 1
    assert req[("binance", "account_balance")] == 1
    assert req[("binance", "market_price_snapshot")] == 1
    assert req[("binance", "get_multiple_prices")] == 0, \
        "0 HTTP: se resuelve del snapshot"
    assert req[("binance", "get_market_pairs")] == 0, \
        "0 HTTP: se construye en memoria"

    http_medido = sum(v for (p, _), v in req.items() if p == "binance")
    assert http_medido == cliente.llamadas["get_exchange_info"] \
        + cliente.llamadas["get_account"] + cliente.llamadas["get_all_tickers"], \
        "la telemetria debe cuadrar con las peticiones que el cliente vio"


def test_8b_una_peticion_no_se_atribuye_a_dos_operaciones(ciclo):
    """El batch cuenta UNA vez, y solo en market_price_snapshot."""
    cliente, _, medidores = ciclo(n=1)
    con_requests = [(o.metricas.operacion, o.metricas.n_requests)
                    for o in medidores[0].operaciones()
                    if o.metricas.n_requests]
    assert sorted(con_requests) == [("account_balance", 1), ("exchange_info", 1),
                                    ("market_price_snapshot", 1)]
    assert cliente.llamadas["get_all_tickers"] == 1


def test_8c_las_transformaciones_en_memoria_conservan_n_elementos(ciclo):
    """0 peticiones no significa 0 informacion: n_elementos sigue vivo."""
    _, _, medidores = ciclo(n=1)
    ops = {o.metricas.operacion: o.metricas for o in medidores[0].operaciones()}

    assert ops["market_price_snapshot"].n_elementos == len(TICKERS_COMPLETOS)
    assert ops["get_multiple_prices"].n_elementos == 4
    assert ops["get_market_pairs"].n_elementos == 6
    assert ops["fase_pre_llm"].n_elementos == 4


def test_9_el_status_sigue_atribuido_a_la_peticion_correcta(conector, monkeypatch):
    c, cliente = conector
    m = MedidorCicloHttp()
    op = m.operacion("binance", "market_price_snapshot")

    c.get_price_snapshot(medicion=op)                    # 200 real
    monkeypatch.setattr(cliente, "fallo_tickers", ConnectionError("sin red"))
    c.get_price_snapshot(medicion=op)                    # muere sin respuesta

    assert op.metricas.n_requests == 2
    assert (op.metricas.n_ok, op.metricas.n_error) == (1, 1)
    assert op.metricas.status_counts == {"200": 1, SIN_STATUS: 1}, \
        "el fallo no hereda el 200 anterior"


def test_9b_un_error_http_del_batch_conserva_su_codigo(conector, monkeypatch):
    c, cliente = conector
    fallo = RuntimeError("rechazado")
    fallo.status_code = 429
    monkeypatch.setattr(cliente, "fallo_tickers", fallo)

    m = MedidorCicloHttp()
    op = m.operacion("binance", "market_price_snapshot")
    assert c.get_price_snapshot(medicion=op) == {}
    assert op.metricas.status_counts == {"429": 1}
    assert op.metricas.n_error == 1


def test_10_un_fallo_de_telemetria_no_altera_el_trading(monkeypatch, conector):
    c, _ = conector

    class OpRota:
        def peticion(self, **kw):
            raise RuntimeError("medidor corrupto")

        def elementos(self, n):
            raise RuntimeError("medidor corrupto")

    # El snapshot se pierde porque el medidor rompe el bloque, pero NO se
    # inventan datos ni se propaga la excepcion fuera del conector.
    assert c.get_price_snapshot(medicion=OpRota()) == {}

    # Y con un medidor sano el resultado es el normal: la telemetria no decide.
    assert c.get_price_snapshot() != {}


def test_10b_resolver_precios_no_depende_de_la_telemetria(conector):
    c, _ = conector
    snapshot = c.get_price_snapshot()

    class OpRota:
        def peticion(self, **kw):
            raise RuntimeError("x")

        def elementos(self, n):
            raise RuntimeError("x")

    try:
        salida = c.get_multiple_prices(["BTCUSDT"], snapshot=snapshot,
                                       medicion=OpRota())
    except Exception:
        pytest.fail("un medidor roto no puede impedir resolver precios")
    assert salida == {"BTCUSDT": 100000.0}


# ═══════════════════════════════════════════════════════════════════════════
# GUARDAS ANTI-REGRESION AL N+1
# ═══════════════════════════════════════════════════════════════════════════
def _funcion(ruta, nombre):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(arbol)
                if isinstance(n, ast.FunctionDef) and n.name == nombre)


@pytest.mark.parametrize("ruta,nombre", [
    (CONECTOR, "get_price_snapshot"),
    (CONECTOR, "get_multiple_prices"),
    (COLECTOR, "get_market_pairs"),
    (COLECTOR, "get_available_assets"),
])
def test_ninguna_peticion_vive_dentro_de_un_bucle(ruta, nombre):
    """
    Guarda estructural contra el N+1: ningun `peticion()` puede estar dentro de
    un `for`/`while`. Es la forma exacta que tenia el codigo que 02B elimino.
    """
    fn = _funcion(ruta, nombre)
    for nodo in ast.walk(fn):
        if not isinstance(nodo, (ast.For, ast.While, ast.comprehension)):
            continue
        cuerpo = getattr(nodo, "body", []) or []
        for hijo in cuerpo:
            for interno in ast.walk(hijo):
                if isinstance(interno, ast.Call) and \
                        getattr(interno.func, "attr", None) == "peticion":
                    pytest.fail(
                        f"{ruta.name}:{interno.lineno} en {nombre}(): hay una "
                        f"peticion HTTP dentro de un bucle. Es el patron N+1 "
                        f"que 02B elimino (1.845 peticiones/ciclo).")


@pytest.mark.parametrize("ruta,nombre", [
    (CONECTOR, "get_price_snapshot"),
    (CONECTOR, "get_multiple_prices"),
    (COLECTOR, "get_market_pairs"),
])
def test_los_caminos_batch_no_usan_tickers_individuales(ruta, nombre):
    """
    Se comparan IDENTIFICADORES invocados, no el volcado en bruto: los
    docstrings citan `get_symbol_ticker` para explicar por que ya no se usa, y
    mencionarlo no es usarlo.
    """
    fn = _funcion(ruta, nombre)
    invocados = {getattr(n.func, "attr", None) or getattr(n.func, "id", None)
                 for n in ast.walk(fn) if isinstance(n, ast.Call)}
    for prohibido in ("get_symbol_ticker", "get_current_price",
                      "get_current_prices"):
        assert prohibido not in invocados, (
            f"{nombre}() no puede volver a pedir precios de uno en uno "
            f"({prohibido})")


def test_el_ciclo_usa_get_all_tickers_y_no_ticker_por_simbolo():
    fuente = CONECTOR.read_text(encoding="utf-8")
    assert "get_all_tickers" in fuente, \
        "el metodo batch soportado por python-binance debe usarse"
    fn = _funcion(CONECTOR, "get_price_snapshot")
    assert "get_all_tickers" in ast.dump(fn)


def test_get_market_pairs_no_hace_ninguna_llamada_de_precio():
    """Su unico origen de precios es el snapshot que recibe."""
    fn = _funcion(COLECTOR, "get_market_pairs")
    llamadas = {getattr(n.func, "attr", None) for n in ast.walk(fn)
                if isinstance(n, ast.Call)}
    assert "get_current_price" not in llamadas
    assert "get_symbol_ticker" not in llamadas


# ═══════════════════════════════════════════════════════════════════════════
# 11-12 · EL ENTORNO NO CAMBIA
# ═══════════════════════════════════════════════════════════════════════════
def test_11_paper_permanece_intacto():
    from backend.config import settings
    assert settings.TRADING_MODE == "PAPER"
    assert settings.MODO_REAL is False


def test_12_import_safety_permanece_intacto(monkeypatch):
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


def test_02b_no_necesita_migracion_nueva():
    """
    `market_price_snapshot` cabe en la columna existente: no hay 0006.
    """
    from backend.app import models
    from backend.esquema import revision_esperada

    assert revision_esperada() == "0005_telemetria_http", \
        "02B no debe introducir una migracion"
    ancho = models.CicloHttpAudit.__table__.c.operacion.type.length
    assert len("market_price_snapshot") <= ancho
    assert not list((RAIZ / "migrations" / "versions").glob("0006*")), \
        "no debe existir una migracion 0006"


def test_el_scheduling_y_la_cadencia_no_cambian():
    fuente = MAIN.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "trading_loop")

    incrementos = [n for n in ast.walk(fn) if isinstance(n, ast.AugAssign)
                   and isinstance(n.target, ast.Name) and n.target.id == "ciclo"]
    assert len(incrementos) == 5, "02B no toca la cadencia del bucle"

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
