"""
Fase BOT 2.0-02A · Telemetria HTTP de mercado y diagnostico del ciclo.

MIDE, NO OPTIMIZA. Ninguna prueba de este modulo contacta con Binance, OpenAI
ni ningun servicio de noticias: todo se sustituye por dobles.

Lo que se protege aqui:
  · la agregacion es correcta y no fabrica datos,
  · `ciclo_id` es SOLO telemetrico y no toca el scheduling ni las decisiones,
  · la telemetria es fail-open: si falla, el ciclo termina exactamente igual,
  · no se filtran secretos ni por consola ni a la base de datos.
"""
import ast
import json
import pathlib
import re
import threading
import time
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.telemetria_http import (
    MEDIDOR_NULO,
    OPERACION_NULA,
    SIN_STATUS,
    MedidorCicloHttp,
    describir_error,
    nuevo_ciclo_id,
    redactar,
)

RAIZ = pathlib.Path(__file__).resolve().parents[1]
MAIN = RAIZ / "backend" / "main.py"

# Credenciales SINTETICAS. No existen y no valen para nada.
AUTH_TOKEN_FALSO = "abcdef0123456789-TOKEN-SINTETICO-NO-REAL"
API_KEY_FALSA = "sk-CLAVE-SINTETICA-DE-PRUEBA-NO-REAL-000000"


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


class _ClienteConResponse:
    """
    Doble de python-binance: expone la ULTIMA respuesta en `.response`.

    Reproduce la trampa real: si una peticion falla antes de producir
    respuesta, `.response` conserva la de la peticion anterior.
    """

    def __init__(self):
        self.response = None

    def responde(self, status):
        """Simula una respuesta HTTP nueva (objeto distinto cada vez)."""
        self.response = SimpleNamespace(status_code=status)
        return self.response

    def observador(self):
        from backend.telemetria_http import ObservadorRespuesta
        return ObservadorRespuesta(lambda: self.response)


@pytest.fixture
def bd():
    """SQLite en memoria con el esquema de los modelos. Nunca toca app.db."""
    engine = sa.create_engine("sqlite://",
                              connect_args={"check_same_thread": False},
                              poolclass=StaticPool)
    models.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


# ═══════════════════════════════════════════════════════════════════════════
# AGREGACION
# ═══════════════════════════════════════════════════════════════════════════
def test_agrega_por_ciclo_id_proveedor_y_operacion(bd):
    """Una fila por (ciclo_id, proveedor, operacion). Ni una mas."""
    m = MedidorCicloHttp("ciclo-fijo", ciclo_num=7)
    for _ in range(3):
        with m.operacion("binance", "get_multiple_prices").peticion() as p:
            p.anotar_status(200)
    with m.operacion("binance", "exchange_info").peticion() as p:
        p.anotar_status(200)
    with m.operacion("cryptopanic", "noticias").peticion() as p:
        p.anotar_status(200)

    assert m.volcar(session_factory=bd) == 3, "3 claves distintas, 3 filas"

    with bd() as db:
        filas = db.query(models.CicloHttpAudit).all()
        claves = {(f.ciclo_id, f.proveedor, f.operacion) for f in filas}
        assert claves == {
            ("ciclo-fijo", "binance", "get_multiple_prices"),
            ("ciclo-fijo", "binance", "exchange_info"),
            ("ciclo-fijo", "cryptopanic", "noticias"),
        }
        assert {f.ciclo_num for f in filas} == {7}
        precios = next(f for f in filas if f.operacion == "get_multiple_prices")
        assert precios.n_requests == 3, "las 3 peticiones caen en UNA fila"


def test_la_misma_clave_devuelve_siempre_el_mismo_acumulador():
    m = MedidorCicloHttp()
    assert m.operacion("binance", "x") is m.operacion("binance", "x")
    assert m.operacion("binance", "x") is not m.operacion("newsapi", "x")


def test_contadores_ok_error_cuadran_con_las_peticiones():
    m = MedidorCicloHttp()
    op = m.operacion("binance", "get_multiple_prices")
    for _ in range(5):
        with op.peticion() as p:
            p.anotar_status(200)
    for _ in range(2):
        with op.peticion() as p:
            p.marcar_error(429)
    with pytest.raises(ValueError):
        with op.peticion():
            raise ValueError("la red se cayo")

    met = op.metricas
    assert met.n_requests == 8
    assert met.n_ok == 5
    assert met.n_error == 3
    assert met.n_ok + met.n_error == met.n_requests, "no se pierde ninguna"


def test_una_excepcion_dentro_de_peticion_se_relanza_intacta():
    """Medir no puede alterar el flujo de control."""
    m = MedidorCicloHttp()
    original = KeyError("clave")
    with pytest.raises(KeyError) as capturada:
        with m.operacion("binance", "x").peticion():
            raise original
    assert capturada.value is original


def test_status_counts_refleja_la_mezcla_real(bd):
    m = MedidorCicloHttp("ciclo-mezcla")
    op = m.operacion("binance", "get_multiple_prices")
    for _ in range(488):
        with op.peticion() as p:
            p.anotar_status(200)
    for _ in range(2):
        with op.peticion() as p:
            p.marcar_error(429)

    assert op.metricas.status_counts == {"200": 488, "429": 2}
    m.volcar(session_factory=bd)
    with bd() as db:
        fila = db.query(models.CicloHttpAudit).one()
        assert json.loads(fila.status_counts) == {"200": 488, "429": 2}


def test_sin_codigo_http_no_se_fabrica_un_200():
    """Desconocido no es exito: se marca SIN_STATUS."""
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    with op.peticion():
        pass
    assert op.metricas.status_counts == {SIN_STATUS: 1}
    assert op.metricas.n_ok == 1, "la peticion si fue bien, solo se ignora el codigo"


def test_el_observador_recupera_el_codigo_a_posteriori():
    """python-binance solo expone el codigo en client.response."""
    cliente = _ClienteConResponse()
    m = MedidorCicloHttp()
    op = m.operacion("binance", "exchange_info")
    with op.peticion(observador=cliente.observador()):
        cliente.responde(200)
    assert op.metricas.status_counts == {"200": 1}


def test_un_observador_roto_no_rompe_la_medicion():
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")

    class Roto:
        def antes(self):
            raise RuntimeError("acceso invalido")

        def status(self):
            raise RuntimeError("acceso invalido")

    with op.peticion(observador=Roto()):
        pass
    assert op.metricas.n_requests == 1 and op.metricas.n_ok == 1
    assert op.metricas.status_counts == {SIN_STATUS: 1}


def test_el_codigo_http_de_la_excepcion_se_conserva():
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    fallo = RuntimeError("rechazado")
    fallo.status_code = 418
    with pytest.raises(RuntimeError):
        with op.peticion():
            raise fallo
    assert op.metricas.status_counts == {"418": 1}
    assert op.metricas.n_error == 1


# ═══════════════════════════════════════════════════════════════════════════
# ATRIBUCION DEL CODIGO HTTP
#
# El riesgo: los clientes que exponen la ultima respuesta en un atributo
# global -python-binance lo hace en `client.response`- permiten atribuir el
# codigo de una peticion a la SIGUIENTE. Se comprobo que ocurria: A=200 y
# luego B fallida producia status_counts {"200": 2}.
# ═══════════════════════════════════════════════════════════════════════════
def test_atribucion_1_request_exitoso_200():
    cliente = _ClienteConResponse()
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    with op.peticion(observador=cliente.observador()):
        cliente.responde(200)

    assert op.metricas.status_counts == {"200": 1}
    assert (op.metricas.n_ok, op.metricas.n_error) == (1, 0)


def test_atribucion_2_request_http_429():
    """Un 429 observado se cuenta como ERROR aunque nada haya lanzado."""
    cliente = _ClienteConResponse()
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    with op.peticion(observador=cliente.observador()):
        cliente.responde(429)

    assert op.metricas.status_counts == {"429": 1}
    assert (op.metricas.n_ok, op.metricas.n_error) == (0, 1), \
        "el exito no se infiere de que Python no propagara una excepcion"


def test_atribucion_3_excepcion_sin_response():
    cliente = _ClienteConResponse()
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    with pytest.raises(ConnectionError):
        with op.peticion(observador=cliente.observador()):
            raise ConnectionError("la conexion murio antes de responder")

    assert op.metricas.status_counts == {SIN_STATUS: 1}
    assert (op.metricas.n_ok, op.metricas.n_error) == (0, 1)


def test_atribucion_4_un_200_anterior_no_se_hereda():
    """EL CASO OBLIGATORIO: A=200, B falla sin respuesta nueva."""
    cliente = _ClienteConResponse()
    observador = cliente.observador()
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")

    with op.peticion(observador=observador):          # A
        cliente.responde(200)

    with op.peticion(observador=observador,           # B
                     exige_evidencia=True) as p:
        p.marcar_error()
        # cliente.response NO se actualiza: sigue siendo la de A.

    assert op.metricas.status_counts == {"200": 1, SIN_STATUS: 1}, (
        "B no puede heredar el 200 de A")
    assert op.metricas.status_counts.get("200") == 1
    assert (op.metricas.n_ok, op.metricas.n_error) == (1, 1)


def test_atribucion_4b_si_hay_respuesta_nueva_si_se_atribuye():
    """Cuando el fallo SI produjo respuesta, el codigo real se conserva."""
    cliente = _ClienteConResponse()
    observador = cliente.observador()
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")

    with op.peticion(observador=observador):
        cliente.responde(200)
    with op.peticion(observador=observador, exige_evidencia=True) as p:
        cliente.responde(429)                 # el servidor SI contesto
        p.marcar_error()

    assert op.metricas.status_counts == {"200": 1, "429": 1}


def test_atribucion_5_metodo_legacy_que_traga_la_excepcion(monkeypatch):
    """
    `get_price_snapshot` captura la excepcion del batch y devuelve {}.

    La peticion ya quedo anotada como error con su codigo REAL antes de que el
    metodo se la tragase, porque `get_all_tickers` si propaga. El codigo no
    puede ser el de una peticion anterior.
    """
    from backend.connectors.crypto import binance_connector as bc

    conector = bc.BinanceConnector()
    cliente = _ClienteConResponse()
    monkeypatch.setattr(conector, "init_client", lambda: None)
    monkeypatch.setattr(conector, "client", cliente, raising=False)

    m = MedidorCicloHttp()

    # 1) Peticion buena: 200 real.
    cliente.get_all_tickers = lambda: (cliente.responde(200),
                                       [{"symbol": "BTCUSDT", "price": "100000.0"}])[1]
    op = m.operacion("binance", "market_price_snapshot")
    assert conector.get_price_snapshot(medicion=op) == {"BTCUSDT": 100000.0}

    # 2) Peticion que muere ANTES de producir respuesta nueva.
    def revienta():
        raise ConnectionError("la conexion murio antes de responder")

    cliente.get_all_tickers = revienta
    assert conector.get_price_snapshot(medicion=op) == {}, \
        "un batch fallido devuelve vacio, nunca datos a medias"

    assert (op.metricas.n_ok, op.metricas.n_error) == (1, 1)
    assert op.metricas.status_counts == {"200": 1, SIN_STATUS: 1}, \
        "el fallo no puede heredar el 200 de la peticion anterior"


def test_atribucion_5b_get_account_balance_vacio_sin_respuesta_no_es_exito(
        monkeypatch):
    """`[]` es ambiguo: sin evidencia positiva no se afirma que fue bien."""
    from backend.utils import asset_collector as ac

    cliente = _ClienteConResponse()
    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    monkeypatch.setattr(ac.binance, "client", cliente, raising=False)
    monkeypatch.setattr(cliente, "get_exchange_info",
                        lambda: (cliente.responde(200), {"symbols": []})[1],
                        raising=False)
    monkeypatch.setattr(ac.binance, "get_account_balance", lambda: [])

    m = MedidorCicloHttp()
    ac.get_available_assets(medidor=m)

    saldos = m.operacion("binance", "account_balance").metricas
    assert saldos.n_error == 1 and saldos.n_ok == 0
    assert saldos.status_counts == {SIN_STATUS: 1}


def test_atribucion_6_sin_status_nunca_cuenta_como_200():
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    for _ in range(4):
        with op.peticion():
            pass
    assert "200" not in op.metricas.status_counts
    assert op.metricas.status_counts == {SIN_STATUS: 4}


def test_atribucion_7_la_suma_sigue_cuadrando_en_todos_los_casos():
    cliente = _ClienteConResponse()
    observador = cliente.observador()
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")

    with op.peticion(observador=observador):                  # 200
        cliente.responde(200)
    with op.peticion(observador=observador):                  # 429
        cliente.responde(429)
    with pytest.raises(ConnectionError):                      # excepcion
        with op.peticion(observador=observador):
            raise ConnectionError("sin red")
    with op.peticion(observador=observador,                   # legacy tragado
                     exige_evidencia=True) as p:
        p.marcar_error()
    with op.peticion():                                       # sin observador
        pass

    met = op.metricas
    assert met.n_requests == 5
    assert met.n_ok + met.n_error == met.n_requests
    assert (met.n_ok, met.n_error) == (2, 3)
    assert sum(met.status_counts.values()) == met.n_requests


def test_una_excepcion_anula_cualquier_marca_previa_de_exito():
    """Si el bloque lanza, fallo: ninguna marca anterior puede taparlo."""
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    with pytest.raises(RuntimeError):
        with op.peticion() as p:
            p.marcar_ok(200)
            raise RuntimeError("reventó despues")
    assert (op.metricas.n_ok, op.metricas.n_error) == (0, 1)
    assert op.metricas.status_counts == {"200": 1}, \
        "el codigo observado se conserva; el veredicto es fallo"


def test_el_observador_no_confunde_objetos_reciclados():
    """
    Se compara por identidad conservando la referencia previa: mientras el
    observador la retiene, el recolector no puede reutilizar su direccion.
    """
    from backend.telemetria_http import ObservadorRespuesta

    caja = {"r": None}
    obs = ObservadorRespuesta(lambda: caja["r"])

    caja["r"] = SimpleNamespace(status_code=200)
    obs.antes()
    assert obs.status() is None, "la misma respuesta no es una respuesta nueva"

    caja["r"] = SimpleNamespace(status_code=503)
    assert obs.status() == 503


def test_ningun_punto_de_medicion_usa_ultima_respuesta_directamente():
    """
    Guarda: leer `client.response` sin observador reintroduce el bug.
    """
    for ruta in ("backend/main.py", "backend/utils/asset_collector.py",
                 "backend/connectors/crypto/binance_connector.py"):
        arbol = ast.parse((RAIZ / ruta).read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not (isinstance(nodo, ast.Call)
                    and getattr(nodo.func, "attr", None) == "peticion"):
                continue
            volcado = ast.dump(nodo)
            assert "ultima_respuesta" not in volcado, (
                f"{ruta}:{nodo.lineno}: peticion() no puede leer la ultima "
                f"respuesta del cliente sin un observador de por medio")
            assert "status_de" not in volcado, (
                f"{ruta}:{nodo.lineno}: `status_de` ya no existe; usar "
                f"observador=")


# ═══════════════════════════════════════════════════════════════════════════
# CARDINALIDAD PROTEGIDA POR LA BASE DE DATOS
# ═══════════════════════════════════════════════════════════════════════════
NOMBRE_UNICO = "uq_ciclo_http_audit_ciclo_proveedor_operacion"


def test_el_modelo_declara_la_unica():
    unicas = {c.name: sorted(col.name for col in c.columns)
              for c in models.CicloHttpAudit.__table__.constraints
              if isinstance(c, sa.UniqueConstraint)}
    assert NOMBRE_UNICO in unicas, f"restricciones declaradas: {list(unicas)}"
    assert unicas[NOMBRE_UNICO] == ["ciclo_id", "operacion", "proveedor"]


def test_la_migracion_crea_la_unica(url_tmp):
    from alembic import command

    command.upgrade(_alembic(url_tmp), "head")
    insp = sa.inspect(sa.create_engine(url_tmp))
    unicas = {u["name"]: sorted(u["column_names"])
              for u in insp.get_unique_constraints("ciclo_http_audit")}
    assert NOMBRE_UNICO in unicas, f"en la BD hay: {list(unicas)}"
    assert unicas[NOMBRE_UNICO] == ["ciclo_id", "operacion", "proveedor"]


def test_modelo_y_migracion_declaran_la_misma_unica(url_tmp):
    from alembic import command

    command.upgrade(_alembic(url_tmp), "head")
    insp = sa.inspect(sa.create_engine(url_tmp))
    en_bd = {u["name"]: sorted(u["column_names"])
             for u in insp.get_unique_constraints("ciclo_http_audit")}
    en_modelo = {c.name: sorted(col.name for col in c.columns)
                 for c in models.CicloHttpAudit.__table__.constraints
                 if isinstance(c, sa.UniqueConstraint)}
    assert en_modelo == en_bd, (
        f"modelo y migracion han divergido: modelo={en_modelo} bd={en_bd}")


def test_la_base_rechaza_dos_filas_con_la_misma_clave(bd):
    """La regla no depende de la agregacion en memoria."""
    import sqlalchemy.exc as saexc

    def fila():
        return models.CicloHttpAudit(
            ciclo_id="ciclo-dup", proveedor="binance",
            operacion="get_multiple_prices", n_requests=1, n_ok=1, n_error=0)

    with bd() as db:
        db.add(fila())
        db.commit()

    with bd() as db:
        db.add(fila())
        with pytest.raises(saexc.IntegrityError):
            db.commit()

    with bd() as db:
        assert db.query(models.CicloHttpAudit).count() == 1, "no hay duplicado"


def test_dos_medidores_del_mismo_ciclo_no_duplican_metricas(bd, capsys):
    """
    Escenario que la memoria no puede evitar: dos medidores distintos con el
    mismo ciclo_id. La BD lo corta y la telemetria sigue siendo fail-open.
    """
    for _ in range(2):
        m = MedidorCicloHttp("ciclo-compartido")
        with m.operacion("binance", "exchange_info").peticion() as p:
            p.anotar_status(200)
        m.volcar(session_factory=bd)          # el segundo debe ser rechazado

    with bd() as db:
        assert db.query(models.CicloHttpAudit).count() == 1
    assert "no cambia" in capsys.readouterr().out, \
        "el rechazo se informa pero no propaga"


def test_un_doble_volcar_accidental_no_duplica_ni_lanza(bd):
    m = MedidorCicloHttp("ciclo-doble")
    op = m.operacion("binance", "get_multiple_prices")
    for _ in range(3):
        with op.peticion() as p:
            p.anotar_status(200)

    assert m.volcar(session_factory=bd) == 1
    assert m.volcar(session_factory=bd) == 0, "el segundo volcado es un no-op"
    assert m.volcar(session_factory=bd) == 0

    with bd() as db:
        filas = db.query(models.CicloHttpAudit).all()
    assert len(filas) == 1
    assert filas[0].n_requests == 3, "las metricas no se han duplicado"


def test_un_volcado_fallido_si_puede_reintentarse(bd):
    """La idempotencia no puede impedir recuperarse de un fallo transitorio."""
    def caida():
        raise RuntimeError("base de datos caida")

    m = MedidorCicloHttp("ciclo-reintento")
    with m.operacion("binance", "x").peticion():
        pass

    assert m.volcar(session_factory=caida) == 0
    assert m.volcar(session_factory=bd) == 1, "debe poder reintentarse"


def test_el_doble_volcar_no_altera_el_resultado_del_bucle(bucle, bd):
    """Un volcado repetido no puede tocar ninguna decision de trading."""
    ejecutar, registro = bucle
    ejecutar(n=4)
    ciclos = [x["ciclo"] for x in registro["llm"]]

    with bd() as db:
        antes = db.query(models.CicloHttpAudit).count()
    assert ciclos == [1, 3]
    assert antes > 0
    # El bucle ya volco cada iteracion; nada mas puede escribirse.
    with bd() as db:
        assert db.query(models.CicloHttpAudit).count() == antes


# ═══════════════════════════════════════════════════════════════════════════
# LATENCIAS Y DURACION
# ═══════════════════════════════════════════════════════════════════════════
def test_latencia_total_y_maxima_y_media_derivable():
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    for espera in (0.01, 0.03, 0.01):
        with op.peticion():
            time.sleep(espera)

    met = op.metricas
    assert met.latencia_total_ms >= 45
    assert met.latencia_max_ms >= 28
    assert met.latencia_max_ms <= met.latencia_total_ms
    # La media NO se persiste: se deriva.
    assert met.latencia_media_ms == pytest.approx(
        met.latencia_total_ms / met.n_requests)


def test_la_media_de_cero_peticiones_es_desconocida_no_cero():
    from backend.telemetria_http import MetricasOperacionHttp
    assert MetricasOperacionHttp("binance", "x").latencia_media_ms is None


def test_latencia_media_no_se_persiste():
    columnas = {c.name for c in models.CicloHttpAudit.__table__.columns}
    assert "latencia_media_ms" not in columnas, (
        "es derivable de latencia_total_ms y n_requests; duplicar estado "
        "invita a inconsistencias")
    assert {"latencia_total_ms", "latencia_max_ms"} <= columnas


def test_duracion_de_pared_puede_diferir_de_la_suma_de_latencias():
    """La suma de latencias ignora el trabajo local ENTRE peticiones."""
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    for _ in range(2):
        with op.peticion():
            time.sleep(0.01)
        time.sleep(0.04)          # trabajo local, fuera de la peticion

    met = op.metricas
    assert met.duracion_ms > met.latencia_total_ms, (
        "el tiempo de pared incluye lo que la suma de latencias no ve")
    assert met.inicio is not None and met.fin is not None


def test_fase_pre_llm_mide_pared_sin_peticiones_propias(bd):
    """Es la fila que explica los ~8 min previos al LLM del baseline."""
    m = MedidorCicloHttp("ciclo-pre-llm")
    time.sleep(0.05)
    m.marcar_fase_pre_llm(490)

    op = m.operacion("interno", "fase_pre_llm")
    assert op.metricas.n_requests == 0, "no hace peticiones propias"
    assert op.metricas.duracion_ms >= 45
    assert op.metricas.n_elementos == 490

    m.volcar(session_factory=bd)
    with bd() as db:
        fila = db.query(models.CicloHttpAudit).filter_by(
            operacion="fase_pre_llm").one()
        assert fila.n_requests == 0 and fila.duracion_ms >= 45
        assert fila.n_elementos == 490


# ═══════════════════════════════════════════════════════════════════════════
# n_elementos POR OPERACION
# ═══════════════════════════════════════════════════════════════════════════
def test_n_elementos_de_exchange_info_y_account_balance(monkeypatch):
    """exchange_info -> simbolos devueltos; account_balance -> activos con saldo."""
    from backend.utils import asset_collector as ac

    simbolos = [
        {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
         "status": "TRADING", "isSpotTradingAllowed": True},
        {"symbol": "ETHBTC", "baseAsset": "ETH", "quoteAsset": "BTC",
         "status": "TRADING", "isSpotTradingAllowed": True},
    ]
    saldos = [{"asset": "USDT", "free": "20.0", "locked": "0.0"}]

    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    # 04A-1 dejo de delegar en `get_account_balance()` y llama directamente a
    # `client.get_account()`, para reutilizar EL MISMO payload y sacar de el la
    # fee taker sin anadir una peticion. El doble se ajusta a esa ruta; el
    # trafico y lo que se mide siguen siendo los mismos.
    monkeypatch.setattr(ac.binance, "client",
                        SimpleNamespace(get_exchange_info=lambda: {"symbols": simbolos},
                                        get_account=lambda: {"balances": saldos}),
                        raising=False)

    m = MedidorCicloHttp()
    activos, balances, info = ac.get_available_assets(medidor=m)

    assert m.operacion("binance", "exchange_info").metricas.n_elementos == 2
    assert m.operacion("binance", "account_balance").metricas.n_elementos == 1
    assert m.operacion("binance", "exchange_info").metricas.n_requests == 1
    assert m.operacion("binance", "account_balance").metricas.n_requests == 1
    # El resultado funcional no cambia por medir.
    assert [a["symbol"] for a in activos] == ["BTCUSDT"]
    assert balances == saldos and info == simbolos


def test_n_elementos_de_get_multiple_prices_cuenta_precios_devueltos(monkeypatch):
    """02B: se resuelve del snapshot, con CERO peticiones propias."""
    from backend.connectors.crypto import binance_connector as bc

    conector = bc.BinanceConnector()
    monkeypatch.setattr(conector, "init_client", lambda: None)
    snapshot = {"BTCUSDT": 100000.0, "ETHUSDT": 3000.0}

    m = MedidorCicloHttp()
    op = m.operacion("binance", "get_multiple_prices")
    salida = conector.get_multiple_prices(
        ["BTCUSDT", "ETHUSDT", "AUSENTEUSDT"], snapshot=snapshot, medicion=op)

    assert salida == snapshot, "solo los simbolos con precio conocido"
    assert "AUSENTEUSDT" not in salida, "un simbolo ausente no inventa 0.0"
    assert op.metricas.n_requests == 0, "resolver del snapshot no es HTTP"
    assert op.metricas.n_elementos == 2


def test_n_elementos_de_get_market_pairs_cuenta_pares_con_precio(monkeypatch):
    """02B: se construye en memoria, con CERO peticiones propias."""
    from backend.utils import asset_collector as ac

    simbolos = [
        {"symbol": "BTCUSDT", "status": "TRADING", "isSpotTradingAllowed": True},
        {"symbol": "ETHBTC", "status": "TRADING", "isSpotTradingAllowed": True},
        {"symbol": "VIEJOX", "status": "BREAK", "isSpotTradingAllowed": True},
    ]
    monkeypatch.setattr(ac.binance, "init_client", lambda: None)

    m = MedidorCicloHttp()
    pares = ac.get_market_pairs(simbolos, snapshot={"BTCUSDT": 1.5, "ETHBTC": 0.05},
                                medidor=m)

    op = m.operacion("binance", "get_market_pairs")
    assert len(pares) == 2, "el par que no cotiza se descarta"
    assert op.metricas.n_requests == 0, "ya no hay un ticker por par"
    assert op.metricas.n_elementos == 2


def test_n_elementos_de_noticias_por_proveedor(monkeypatch):
    """CryptoPanic y NewsAPI fallan por separado: se miden por separado."""
    from backend.connectors.apis import news_connector as nc

    conector = nc.NewsConnector()
    monkeypatch.setattr(conector, "obtener_noticias_recientes",
                        lambda numero_noticias=5, medicion=None: ["c1", "c2"])
    monkeypatch.setattr(conector, "obtener_noticias_stocks",
                        lambda numero_noticias=3, medicion=None: ["s1"])
    monkeypatch.setattr(conector, "obtener_noticias_forex",
                        lambda numero_noticias=3, medicion=None: ["f1", "f2", "f3"])

    m = MedidorCicloHttp()
    assert len(conector.obtener_noticias_combinadas(6, medidor=m)) == 6
    assert m.operacion("cryptopanic", "noticias").metricas.n_elementos == 2
    assert m.operacion("newsapi", "noticias").metricas.n_elementos == 4


def test_noticias_cuenta_una_peticion_por_proveedor(monkeypatch):
    from backend.connectors.apis import news_connector as nc

    conector = nc.NewsConnector()
    conector.api_key = AUTH_TOKEN_FALSO
    conector.newsapi_key = API_KEY_FALSA

    def get_falso(url, params=None):
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None,
                               json=lambda: {"results": [{"title": "t"}],
                                             "articles": [{"title": "a"}]})

    monkeypatch.setattr(nc.requests, "get", get_falso)
    m = MedidorCicloHttp()
    conector.obtener_noticias_combinadas(6, medidor=m)

    assert m.operacion("cryptopanic", "noticias").metricas.n_requests == 1
    assert m.operacion("newsapi", "noticias").metricas.n_requests == 2, \
        "stocks y forex son el MISMO proveedor: una sola fila, dos peticiones"


def test_un_403_de_cryptopanic_se_cuenta_como_error(monkeypatch):
    import requests as requests_real
    from backend.connectors.apis import news_connector as nc

    conector = nc.NewsConnector()
    conector.api_key = AUTH_TOKEN_FALSO

    def get_403(url, params=None):
        def revienta():
            raise requests_real.HTTPError(
                f"403 Client Error for url: {url}?auth_token={AUTH_TOKEN_FALSO}")
        return SimpleNamespace(status_code=403, raise_for_status=revienta)

    monkeypatch.setattr(nc.requests, "get", get_403)
    m = MedidorCicloHttp()
    op = m.operacion("cryptopanic", "noticias")

    assert conector.obtener_noticias_recientes(2, medicion=op) == []
    assert op.metricas.n_error == 1 and op.metricas.n_ok == 0
    assert op.metricas.status_counts == {"403": 1}


# ═══════════════════════════════════════════════════════════════════════════
# REDACCION DE SECRETOS
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("texto", [
    f"403 Client Error for url: https://cryptopanic.com/api/v1/posts/?auth_token={AUTH_TOKEN_FALSO}&public=true",
    f"HTTPError: https://newsapi.org/v2/everything?apiKey={API_KEY_FALSA}",
    f"{{'api_key': '{API_KEY_FALSA}'}}",
    f"Authorization: Bearer {API_KEY_FALSA}",
    f"headers={{'Authorization': 'Bearer {API_KEY_FALSA}'}}",
    f"signature={AUTH_TOKEN_FALSO}&timestamp=1",
    f"token={AUTH_TOKEN_FALSO}",
])
def test_redactar_elimina_el_valor_sensible(texto):
    salida = redactar(texto)
    assert AUTH_TOKEN_FALSO not in salida
    assert API_KEY_FALSA not in salida
    assert "REDACTADO" in salida


@pytest.mark.parametrize("clave", [
    "auth_token", "AUTH_TOKEN", "Auth_Token", "aUtH_tOkEn",
    "api_key", "API_KEY", "Api_Key", "apiKey", "APIKEY",
    "token", "TOKEN", "key", "KEY", "signature", "SIGNATURE",
])
def test_redactar_es_insensible_a_mayusculas(clave):
    """La clave puede llegar en cualquier caja segun el proveedor."""
    salida = redactar(f"https://ejemplo/api?{clave}={AUTH_TOKEN_FALSO}&x=1")
    assert AUTH_TOKEN_FALSO not in salida
    assert "REDACTADO" in salida


@pytest.mark.parametrize("forma", [
    # query string
    "https://ejemplo/api?auth_token={s}&public=true",
    "https://ejemplo/api?x=1&apiKey={s}",
    # representacion tipo diccionario
    "{{'auth_token': '{s}', 'filter': ''}}",
    '{{"api_key": "{s}"}}',
    "params={{'signature': '{s}'}}",
    # cabecera de autorizacion
    "Authorization: Bearer {s}",
    "Authorization=Basic {s}",
    "headers={{'Authorization': 'Bearer {s}'}}",
])
def test_redactar_cubre_las_cuatro_formas_de_exposicion(forma):
    salida = redactar(forma.format(s=AUTH_TOKEN_FALSO))
    assert AUTH_TOKEN_FALSO not in salida, f"no redactado en: {forma}"
    assert "REDACTADO" in salida


def test_redactar_conserva_lo_que_no_es_secreto():
    salida = redactar(
        f"403 Client Error for url: https://cryptopanic.com/api/v1/posts/"
        f"?auth_token={AUTH_TOKEN_FALSO}&currencies=BTC,ETH")
    assert "403 Client Error" in salida, "el diagnostico debe sobrevivir"
    assert "cryptopanic.com" in salida
    assert "currencies=BTC,ETH" in salida, "un parametro inocuo no se toca"


def test_redactar_nunca_lanza():
    class Hostil:
        def __str__(self):
            raise RuntimeError("no me conviertas")

    assert "no publicable" in redactar(Hostil())


def test_describir_error_conserva_la_clase_y_sanea_el_mensaje():
    e = ValueError(f"fallo con auth_token={AUTH_TOKEN_FALSO}")
    salida = describir_error(e)
    assert salida.startswith("ValueError:")
    assert AUTH_TOKEN_FALSO not in salida


def test_el_auth_token_no_llega_a_consola_en_un_fallo(monkeypatch, capsys):
    """El fallo real del baseline: un 403 publicaba el auth_token en los logs."""
    import requests as requests_real
    from backend.connectors.apis import news_connector as nc

    conector = nc.NewsConnector()
    conector.api_key = AUTH_TOKEN_FALSO

    def get_403(url, params=None):
        def revienta():
            raise requests_real.HTTPError(
                f"403 Client Error for url: {url}?auth_token={AUTH_TOKEN_FALSO}"
                f"&public=true")
        return SimpleNamespace(status_code=403, raise_for_status=revienta)

    monkeypatch.setattr(nc.requests, "get", get_403)
    assert conector.obtener_noticias_recientes(3) == []

    salida = capsys.readouterr()
    assert AUTH_TOKEN_FALSO not in salida.out + salida.err
    assert "CryptoPanic" in salida.out, "el diagnostico sigue siendo util"


def test_la_apikey_de_newsapi_no_llega_a_consola(monkeypatch, capsys):
    import requests as requests_real
    from backend.connectors.apis import news_connector as nc

    conector = nc.NewsConnector()
    conector.newsapi_key = API_KEY_FALSA

    def get_401(url, params=None):
        def revienta():
            raise requests_real.HTTPError(
                f"401 Client Error for url: {url}?apiKey={API_KEY_FALSA}")
        return SimpleNamespace(status_code=401, raise_for_status=revienta)

    monkeypatch.setattr(nc.requests, "get", get_401)
    assert conector.obtener_noticias_stocks(3) == []
    assert conector.obtener_noticias_forex(3) == []

    salida = capsys.readouterr()
    assert API_KEY_FALSA not in salida.out + salida.err


def test_news_connector_no_imprime_excepciones_en_crudo():
    """AST: ningun print del conector puede formatear la excepcion sin sanear."""
    ruta = RAIZ / "backend/connectors/apis/news_connector.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Call) and getattr(nodo.func, "id", None) == "print"):
            continue
        for arg in nodo.args:
            if not isinstance(arg, ast.JoinedStr):
                continue
            for parte in arg.values:
                if not isinstance(parte, ast.FormattedValue):
                    continue
                assert not (isinstance(parte.value, ast.Name) and parte.value.id == "e"), (
                    f"linea {nodo.lineno}: la excepcion se imprime sin sanear; "
                    f"requests incluye la URL con credenciales en el mensaje")


# ═══════════════════════════════════════════════════════════════════════════
# PRIVACIDAD DE LA TABLA
# ═══════════════════════════════════════════════════════════════════════════
def test_ciclo_http_audit_no_tiene_columnas_de_contenido():
    columnas = {c.name for c in models.CicloHttpAudit.__table__.columns}
    for prohibida in ("url", "headers", "cabeceras", "token", "api_key", "auth",
                      "params", "body", "cuerpo", "respuesta", "mensaje",
                      "secret", "key"):
        assert prohibida not in columnas, f"la tabla no debe guardar {prohibida}"


def test_ninguna_credencial_acaba_en_ciclo_http_audit(bd):
    """Aunque el simbolo/operacion viniesen contaminados, no hay donde guardar."""
    m = MedidorCicloHttp("ciclo-privacidad")
    with m.operacion("binance", "get_multiple_prices").peticion() as p:
        p.anotar_status(200)
    m.volcar(session_factory=bd)

    with bd() as db:
        fila = db.query(models.CicloHttpAudit).one()
        texto = " ".join(str(getattr(fila, c.name))
                         for c in fila.__table__.columns)
    assert AUTH_TOKEN_FALSO not in texto
    assert API_KEY_FALSA not in texto
    assert "sk-" not in texto and "Bearer" not in texto


def test_status_counts_es_texto_portable():
    """Text con JSON: mismo esquema en SQLite y en PostgreSQL, sin extensiones."""
    tipo = models.CicloHttpAudit.__table__.c.status_counts.type
    assert isinstance(tipo, sa.Text), f"tipo no portable: {type(tipo).__name__}"


# ═══════════════════════════════════════════════════════════════════════════
# FAIL-OPEN
# ═══════════════════════════════════════════════════════════════════════════
def test_volcar_con_la_base_caida_no_lanza_y_devuelve_cero(capsys):
    def fabrica_rota():
        raise RuntimeError("base de datos caida")

    m = MedidorCicloHttp("ciclo-sin-bd")
    with m.operacion("binance", "x").peticion():
        pass

    assert m.volcar(session_factory=fabrica_rota) == 0
    assert "no cambia" in capsys.readouterr().out


def test_volcar_sin_operaciones_no_escribe_nada(bd):
    assert MedidorCicloHttp("ciclo-vacio").volcar(session_factory=bd) == 0
    with bd() as db:
        assert db.query(models.CicloHttpAudit).count() == 0


def test_el_mensaje_de_fallo_de_telemetria_tambien_va_saneado(capsys):
    def fabrica_rota():
        raise RuntimeError(f"no pude conectar con auth_token={AUTH_TOKEN_FALSO}")

    m = MedidorCicloHttp()
    with m.operacion("binance", "x").peticion():
        pass
    m.volcar(session_factory=fabrica_rota)
    assert AUTH_TOKEN_FALSO not in capsys.readouterr().out


def test_elementos_con_un_valor_absurdo_no_lanza():
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    op.elementos("no soy un numero")
    op.elementos(None)
    assert op.metricas.n_elementos is None


def test_los_objetos_nulos_no_hacen_nada_y_no_lanzan():
    """`medidor=None` no debe abrir una rama distinta de ejecucion."""
    with OPERACION_NULA.peticion() as p:
        p.anotar_status(200)
        p.marcar_error(500)
    OPERACION_NULA.elementos(5)

    assert MEDIDOR_NULO.operaciones() == []
    assert MEDIDOR_NULO.volcar() == 0
    MEDIDOR_NULO.marcar_fase_pre_llm(3)
    with MEDIDOR_NULO.operacion("binance", "x").peticion():
        pass


def test_el_objeto_nulo_tambien_relanza_las_excepciones():
    with pytest.raises(ValueError):
        with OPERACION_NULA.peticion():
            raise ValueError("intacta")


# ═══════════════════════════════════════════════════════════════════════════
# ciclo_id
# ═══════════════════════════════════════════════════════════════════════════
def test_ciclo_id_es_unico_por_construccion():
    assert len({nuevo_ciclo_id() for _ in range(500)}) == 500
    assert nuevo_ciclo_id().startswith("ciclo-")


def test_ciclo_id_es_estable_dentro_del_medidor():
    m = MedidorCicloHttp()
    visto = m.ciclo_id
    for _ in range(10):
        with m.operacion("binance", "x").peticion():
            pass
        assert m.ciclo_id == visto


def _trading_loop_ast():
    arbol = ast.parse(MAIN.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(arbol)
                if isinstance(n, ast.FunctionDef) and n.name == "trading_loop")


def test_ciclo_id_no_participa_en_ninguna_condicion_ni_aritmetica():
    """
    Guarda estructural: `ciclo_id` es EXCLUSIVAMENTE telemetrico.

    Si algun dia alguien lo usa para decidir, comparar o contar, esto falla.
    """
    fn = _trading_loop_ast()
    for nodo in ast.walk(fn):
        if isinstance(nodo, (ast.Compare, ast.BinOp, ast.BoolOp)):
            volcado = ast.dump(nodo)
            assert "ciclo_id" not in volcado, (
                f"linea {getattr(nodo, 'lineno', '?')}: ciclo_id no puede "
                f"participar en una condicion ni en una operacion")


def test_el_contador_ciclo_no_se_alimenta_de_la_telemetria():
    fn = _trading_loop_ast()
    for nodo in ast.walk(fn):
        objetivos = []
        if isinstance(nodo, ast.AugAssign):
            objetivos = [nodo.target]
        elif isinstance(nodo, ast.Assign):
            objetivos = nodo.targets
        if not any(isinstance(t, ast.Name) and t.id == "ciclo" for t in objetivos):
            continue
        volcado = ast.dump(nodo.value)
        for prohibido in ("medidor", "ciclo_id", "MedidorCicloHttp"):
            assert prohibido not in volcado, (
                f"linea {nodo.lineno}: `ciclo` no puede derivar de la telemetria")


def test_el_numero_de_incrementos_de_ciclo_no_ha_cambiado():
    """
    `ciclo` se incrementa en 5 ramas. Es deuda conocida y 02A NO la toca:
    anadir o quitar un incremento cambiaria la cadencia real del bot.
    """
    fn = _trading_loop_ast()
    incrementos = [n for n in ast.walk(fn)
                   if isinstance(n, ast.AugAssign)
                   and isinstance(n.target, ast.Name) and n.target.id == "ciclo"]
    assert len(incrementos) == 5, (
        f"02A no puede alterar la cadencia: se esperaban 5 incrementos de "
        f"`ciclo`, hay {len(incrementos)}")


def test_el_scheduling_no_lo_toca_la_telemetria():
    """Todo sleep del bucle sigue esperando exactamente settings.WAIT_TIME."""
    fn = _trading_loop_ast()
    sleeps = [n for n in ast.walk(fn)
              if isinstance(n, ast.Call)
              and getattr(n.func, "attr", None) == "sleep"]
    assert sleeps, "el bucle debe seguir esperando entre ciclos"
    for nodo in sleeps:
        assert len(nodo.args) == 1
        assert ast.dump(nodo.args[0]) == ast.dump(
            ast.parse("settings.WAIT_TIME", mode="eval").body), (
            f"linea {nodo.lineno}: el tiempo de espera ha cambiado")


def test_la_cadencia_configurada_sigue_congelada():
    fn = _trading_loop_ast()
    valores = [n.value.value for n in ast.walk(fn)
               if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "EVALUAR_CADA_N_CICLOS"
                       for t in n.targets)
               and isinstance(n.value, ast.Constant)]
    assert valores == [2], f"EVALUAR_CADA_N_CICLOS no puede cambiar en 02A: {valores}"


# ═══════════════════════════════════════════════════════════════════════════
# EL BUCLE COMPLETO (con dobles): comportamiento y telemetria
# ═══════════════════════════════════════════════════════════════════════════
class _Parar(BaseException):
    """
    Corta el `while True` sin que lo capture su `except Exception`.

    Hereda de BaseException a proposito: asi el bucle sale por su `finally`
    -que es justo lo que hay que ejercitar- sin pasar por el manejador de
    errores del ciclo.
    """


# Filtros completos: el Eligibility Gate (03A) exige LOT_SIZE + NOTIONAL y es
# fail-closed sin ellos. minNotional bajo para que la compra sea posible con el
# capital del doble de cartera.
SIMBOLOS = [
    {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
     "status": "TRADING", "isSpotTradingAllowed": True,
     "filters": [{"filterType": "NOTIONAL", "minNotional": "0.10"},
                 {"filterType": "LOT_SIZE", "minQty": "0.00001",
                  "maxQty": "9000.00000000", "stepSize": "0.00001"}]},
]


@pytest.fixture
def bucle(monkeypatch, bd):
    """
    Monta trading_loop sobre dobles y lo deja listo para N iteraciones.

    Devuelve (ejecutar, registro). Ninguna llamada sale a la red.
    """
    import backend.main as main
    from backend.config import settings

    registro = {"llm": [], "iteraciones": 0}
    limite = {"n": 4}

    monkeypatch.setattr(settings, "MODO_REAL", False)
    monkeypatch.setattr(main.time, "sleep", lambda _s: None)
    # volcar() resuelve SessionLocal en el momento de llamar: basta parchear
    # el atributo del modulo para que la telemetria caiga en la BD de prueba.
    monkeypatch.setattr("backend.app.database.SessionLocal", bd)

    def contexto_falso():
        registro["iteraciones"] += 1
        if registro["iteraciones"] > limite["n"]:
            raise _Parar()
        return SimpleNamespace(usuario_id=1, estado={},
                               ultimos_movimientos={}, ultimos_precios_venta={})

    monkeypatch.setattr(main, "cargar_contexto_usuario", contexto_falso)
    monkeypatch.setattr(main.binance, "init_client", lambda: None)
    monkeypatch.setattr(main.binance, "client",
                        SimpleNamespace(get_exchange_info=lambda: {"symbols": SIMBOLOS}),
                        raising=False)
    monkeypatch.setattr(main.binance, "ultima_respuesta",
                        lambda: SimpleNamespace(status_code=200))
    # 02B: el ciclo pide UN snapshot y lo reutiliza; get_multiple_prices ya no
    # hace peticiones propias.
    def snapshot_falso(medicion=None):
        if medicion is not None:
            with medicion.peticion() as p:
                p.anotar_status(200)
            medicion.elementos(len(SIMBOLOS))
        return {s["symbol"]: 100.0 for s in SIMBOLOS}

    monkeypatch.setattr(main.binance, "get_price_snapshot", snapshot_falso)
    monkeypatch.setattr(main.binance, "get_market_metrics",
                        lambda medicion=None: _metricas_sanas(
                            {s["symbol"]: 100.0 for s in SIMBOLOS}))
    monkeypatch.setattr(main.binance, "get_multiple_prices",
                        lambda symbols, snapshot=None, medicion=None: (
                            medicion.elementos(len(symbols)) if medicion else None,
                            {s: (snapshot or {}).get(s, 100.0) for s in symbols})[1])
    monkeypatch.setattr(main.news_connector, "obtener_noticias_combinadas",
                        lambda total=6, medidor=None: ["n1", "n2"])
    def assets_falsos(medidor=None):
        # Reproduce la medicion del original: get_available_assets pide
        # exchange_info y account_balance en CADA ciclo, tambien en los que
        # luego no evaluan. Ese coste debe quedar registrado igualmente.
        if medidor is not None:
            op_info = medidor.operacion("binance", "exchange_info")
            with op_info.peticion() as p:
                p.anotar_status(200)
            op_info.elementos(len(SIMBOLOS))
            op_saldos = medidor.operacion("binance", "account_balance")
            with op_saldos.peticion() as p:
                p.anotar_status(200)
            op_saldos.elementos(1)
        return ([{"symbol": "BTCUSDT", "type": "crypto",
                  "has_balance": False, "has_position": False}],
                [{"asset": "USDT", "free": "20.0", "locked": "0.0"}],
                SIMBOLOS)

    monkeypatch.setattr(main, "get_available_assets", assets_falsos)
    monkeypatch.setattr(main, "get_market_pairs",
                        lambda symbols_info=None, snapshot=None, medidor=None: [])
    monkeypatch.setattr(main, "mercado_ny_abierto", lambda: False)
    monkeypatch.setattr(main, "precio_medio_de", lambda estado, symbol: None)
    from backend.risk import reloj
    from backend.risk.estado import EstadoRiesgo
    monkeypatch.setattr(main, "construir_cartera",
                        lambda **k: SimpleNamespace(
                            modo="PAPER", capital_disponible=lambda: 20.0,
                            cantidad_disponible=lambda s: 0.0,
                            estado_riesgo=lambda: EstadoRiesgo(
                                dia=reloj.dia_de_riesgo())))

    def llm_falso(*a, **k):
        registro["llm"].append({"ciclo": k.get("ciclo"),
                                "ciclo_id": k.get("ciclo_id")})
        return [], "sin json"

    monkeypatch.setattr(main.openai, "analyze_multiple_assets", llm_falso)

    def ejecutar(n=4):
        limite["n"] = n
        with pytest.raises(_Parar):
            main.trading_loop()
        return registro

    return ejecutar, registro


def test_el_bucle_conserva_exactamente_la_cadencia_legacy(bucle):
    """
    `ciclo_id` no puede alterar cuando se evalua.

    Con EVALUAR_CADA_N_CICLOS=2 el bucle evalua una iteracion si y otra no, y
    el `ciclo += 1` previo a la llamada hace que el LLM reciba impares.
    """
    ejecutar, registro = bucle
    ejecutar(n=4)
    assert [x["ciclo"] for x in registro["llm"]] == [1, 3], (
        "la cadencia efectiva ha cambiado respecto al baseline")


def test_ciclo_id_es_distinto_en_cada_iteracion(bucle, bd):
    ejecutar, registro = bucle
    ejecutar(n=4)

    vistos = [x["ciclo_id"] for x in registro["llm"]]
    assert len(vistos) == 2 and len(set(vistos)) == 2, "uno por iteracion"
    assert all(v and v.startswith("ciclo-") for v in vistos)

    with bd() as db:
        ids = {f.ciclo_id for f in db.query(models.CicloHttpAudit).all()}
    assert len(ids) == 4, "se mide TAMBIEN la iteracion que no evalua"


def test_ciclo_id_correlaciona_el_gasto_del_llm_con_el_trafico_http(bucle, bd):
    ejecutar, registro = bucle
    ejecutar(n=2)

    ciclo_id_llm = registro["llm"][0]["ciclo_id"]
    with bd() as db:
        filas = db.query(models.CicloHttpAudit).filter_by(
            ciclo_id=ciclo_id_llm).all()
    assert filas, "el ciclo_id del LLM debe existir en la telemetria HTTP"
    assert {f.operacion for f in filas} >= {"exchange_info", "account_balance",
                                            "get_multiple_prices",
                                            "fase_pre_llm"}


def test_la_iteracion_que_aborta_pronto_tambien_se_mide(bucle, bd):
    """El `finally` existe justo para el ciclo que sale por un `continue`."""
    ejecutar, _ = bucle
    ejecutar(n=2)
    with bd() as db:
        por_ciclo = {}
        for f in db.query(models.CicloHttpAudit).all():
            por_ciclo.setdefault(f.ciclo_id, set()).add(f.operacion)
    assert len(por_ciclo) == 2
    # La segunda iteracion no llega al LLM y aun asi deja constancia.
    sin_llm = [ops for ops in por_ciclo.values() if "fase_pre_llm" not in ops]
    assert sin_llm, "la iteracion fuera de turno debe quedar registrada"


def test_ciclo_num_se_guarda_como_dato_legacy(bucle, bd):
    ejecutar, _ = bucle
    ejecutar(n=2)
    with bd() as db:
        nums = {f.ciclo_num for f in db.query(models.CicloHttpAudit).all()}
    assert nums == {0, 1}, (
        "ciclo_num acompana a cada fila como diagnostico, no como identidad")


def test_una_telemetria_rota_no_cambia_el_comportamiento_del_bucle(
        bucle, monkeypatch, capsys):
    """
    Fail-open de verdad: con la persistencia caida, el ciclo produce
    EXACTAMENTE la misma secuencia de decisiones.
    """
    ejecutar, registro = bucle

    def sesion_rota():
        raise RuntimeError("base de datos caida")

    monkeypatch.setattr("backend.app.database.SessionLocal", sesion_rota)
    ejecutar(n=4)

    assert [x["ciclo"] for x in registro["llm"]] == [1, 3], (
        "un fallo de telemetria no puede alterar la cadencia")
    assert "no cambia" in capsys.readouterr().out


def test_un_medidor_que_explota_no_tumba_el_bucle(bucle, monkeypatch):
    """Ni siquiera un fallo interno del medidor puede propagar."""
    from backend import telemetria_http

    def volcar_roto(self, *, session_factory=None):
        try:
            raise RuntimeError("medidor corrupto")
        except Exception:
            return 0

    monkeypatch.setattr(telemetria_http.MedidorCicloHttp, "volcar", volcar_roto)
    ejecutar, registro = bucle
    ejecutar(n=4)
    assert [x["ciclo"] for x in registro["llm"]] == [1, 3]


# ═══════════════════════════════════════════════════════════════════════════
# AMPLIACION DE llm_call_audit
# ═══════════════════════════════════════════════════════════════════════════
class RespuestaLLM:
    def __init__(self, payload, status=200, headers=None):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture
def conector_llm(monkeypatch):
    from backend.config import settings
    from backend.connectors.apis import openai_connector as mod

    monkeypatch.setattr(settings, "OPENAI_API_KEY", API_KEY_FALSA)
    capturadas = []
    c = mod.OpenAIConnector(registrar_telemetria=capturadas.append)
    c.api_key = API_KEY_FALSA
    return c, capturadas, mod


CABECERAS_429 = {
    "x-request-id": "req_1234567890abcdef",
    "x-ratelimit-limit-requests": "500",
    "x-ratelimit-limit-tokens": "30000",
    "x-ratelimit-remaining-requests": "0",
    "x-ratelimit-remaining-tokens": "12345",
    "x-ratelimit-reset-requests": "6m0s",
    "x-ratelimit-reset-tokens": "1.5s",
    # Ruido que NO debe copiarse.
    "authorization": f"Bearer {API_KEY_FALSA}",
    "set-cookie": "sesion=secreta",
}

CUERPO_429 = {"error": {"message": f"limite alcanzado para la clave {API_KEY_FALSA}",
                        "type": "requests", "code": "rate_limit_exceeded"}}


def _llamar_llm(conector_llm, monkeypatch, respuesta, **kw):
    c, capturadas, mod = conector_llm
    monkeypatch.setattr(mod.requests, "post", lambda *a, **k: respuesta)
    c.analyze_multiple_assets([{"symbol": "BTCUSDT", "price": 1.0,
                                "position_quantity": 0.0, "average_price": None}],
                              1000.0, "NEUTRO", "t1\nt2", market_pairs=[], **kw)
    return capturadas[0]


def test_cabeceras_de_rate_limit_capturadas_en_un_429(conector_llm, monkeypatch):
    m = _llamar_llm(conector_llm, monkeypatch,
                    RespuestaLLM(CUERPO_429, status=429, headers=CABECERAS_429))
    assert m.http_status == 429
    assert m.rl_limit_requests == 500
    assert m.rl_limit_tokens == 30000
    assert m.rl_remaining_requests == 0
    assert m.rl_remaining_tokens == 12345
    assert m.rl_reset_requests == "6m0s"
    assert m.rl_reset_tokens == "1.5s"


def test_x_request_id_capturado(conector_llm, monkeypatch):
    m = _llamar_llm(conector_llm, monkeypatch,
                    RespuestaLLM(CUERPO_429, status=429, headers=CABECERAS_429))
    assert m.x_request_id == "req_1234567890abcdef"


def test_error_type_y_code_capturados(conector_llm, monkeypatch):
    """Un 429 por cuota y otro por ritmo comparten codigo HTTP."""
    m = _llamar_llm(conector_llm, monkeypatch,
                    RespuestaLLM(CUERPO_429, status=429, headers=CABECERAS_429))
    assert m.error_type == "requests"
    assert m.error_code == "rate_limit_exceeded"


def test_el_error_message_no_se_captura_nunca(conector_llm, monkeypatch, bd):
    m = _llamar_llm(conector_llm, monkeypatch,
                    RespuestaLLM(CUERPO_429, status=429, headers=CABECERAS_429))

    serializado = repr(vars(m))
    assert API_KEY_FALSA not in serializado
    assert "limite alcanzado" not in serializado, "error.message puede citar el prompt"

    from backend.telemetria_llm import registrar_llamada
    assert registrar_llamada(m, session_factory=bd,
                             config=SimpleNamespace()) is True
    with bd() as db:
        fila = db.query(models.LlmCallAudit).one()
        texto = " ".join(str(getattr(fila, c.name)) for c in fila.__table__.columns)
    assert API_KEY_FALSA not in texto
    assert "Bearer" not in texto and "sesion=secreta" not in texto
    assert "limite alcanzado" not in texto


def test_la_tabla_llm_no_tiene_columna_de_mensaje_de_error():
    columnas = {c.name for c in models.LlmCallAudit.__table__.columns}
    assert "error_message" not in columnas
    assert "error_mensaje" not in columnas
    assert {"error_type", "error_code"} <= columnas


def test_ciclo_id_se_propaga_a_la_telemetria_del_llm(conector_llm, monkeypatch):
    m = _llamar_llm(conector_llm, monkeypatch,
                    RespuestaLLM({"model": "gpt-4o",
                                  "choices": [{"message": {"content": "[]"}}]}),
                    ciclo=3, ciclo_id="ciclo-abc")
    assert m.ciclo == 3
    assert m.ciclo_id == "ciclo-abc"


def test_una_respuesta_sin_cabeceras_deja_los_campos_desconocidos(conector_llm,
                                                                 monkeypatch):
    m = _llamar_llm(conector_llm, monkeypatch,
                    RespuestaLLM({"model": "gpt-4o",
                                  "choices": [{"message": {"content": "[]"}}]}))
    for campo in ("x_request_id", "rl_limit_requests", "rl_reset_tokens",
                  "error_type", "error_code"):
        assert getattr(m, campo) is None, f"{campo}: desconocido, no cero"


def test_una_cabecera_no_numerica_queda_desconocida_no_cero(conector_llm,
                                                            monkeypatch):
    m = _llamar_llm(conector_llm, monkeypatch,
                    RespuestaLLM(CUERPO_429, status=429,
                                 headers={"x-ratelimit-limit-requests": "ilimitado"}))
    assert m.rl_limit_requests is None, "no interpretable no es 0"


def test_capturar_cabeceras_nunca_lanza():
    from backend.telemetria_llm import MetricasLlamadaLLM

    m = MetricasLlamadaLLM(operacion="x")
    m.aplicar_cabeceras(None)
    m.aplicar_cabeceras(SimpleNamespace(headers="no soy un dict"))
    m.aplicar_error(None)
    m.aplicar_error({"error": "texto plano"})
    assert m.x_request_id is None and m.error_type is None


# ═══════════════════════════════════════════════════════════════════════════
# MIGRACION 0005
# ═══════════════════════════════════════════════════════════════════════════
MIGRACION = RAIZ / "migrations" / "versions" / "0005_telemetria_http.py"


def _alembic(url):
    import importlib
    import os

    from alembic.config import Config

    os.environ["DATABASE_URL"] = url        # env.py lee de settings
    from backend.config import settings
    importlib.reload(settings)

    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def url_tmp(tmp_path):
    import importlib
    import os

    previo = os.environ.get("DATABASE_URL")
    yield f"sqlite:///{tmp_path / 'prueba.db'}"
    if previo is not None:
        os.environ["DATABASE_URL"] = previo
    from backend.config import settings
    importlib.reload(settings)


def test_0005_es_la_cabeza_y_encadena_con_0004():
    from backend.esquema import revision_esperada

    assert revision_esperada() == "0005_telemetria_http"
    fuente = MIGRACION.read_text(encoding="utf-8")
    assert 'down_revision = "0004_telemetria"' in fuente


def test_0005_sobre_bd_vacia_crea_la_tabla_y_las_columnas(url_tmp):
    from alembic import command

    command.upgrade(_alembic(url_tmp), "head")
    insp = sa.inspect(sa.create_engine(url_tmp))

    assert "ciclo_http_audit" in insp.get_table_names()
    columnas = {c["name"] for c in insp.get_columns("ciclo_http_audit")}
    assert {"ciclo_id", "ciclo_num", "proveedor", "operacion", "n_requests",
            "n_ok", "n_error", "latencia_total_ms", "latencia_max_ms",
            "duracion_ms", "n_elementos", "status_counts", "inicio",
            "fin"} <= columnas
    assert "latencia_media_ms" not in columnas

    llm = {c["name"] for c in insp.get_columns("llm_call_audit")}
    assert {"ciclo_id", "x_request_id", "error_type", "error_code",
            "rl_limit_requests", "rl_limit_tokens", "rl_remaining_requests",
            "rl_remaining_tokens", "rl_reset_requests",
            "rl_reset_tokens"} <= llm


def test_0005_sobre_bd_con_datos_previos_solo_agrega(url_tmp):
    """Una base con historico de 02-01 sobrevive intacta."""
    from alembic import command

    command.upgrade(_alembic(url_tmp), "0004_telemetria")
    engine = sa.create_engine(url_tmp)
    with engine.begin() as c:
        c.execute(sa.text(
            "INSERT INTO llm_call_audit (call_id, proveedor, operacion, exito, "
            "costo_status) VALUES ('llm-previa', 'openai', 'analyze', 0, "
            "'NO_DISPONIBLE')"))
        c.execute(sa.text("INSERT INTO usuarios (id,nombre,email,password_hash) "
                          "VALUES (1,'Prev','p@e.com','h')"))

    command.upgrade(_alembic(url_tmp), "head")

    with engine.connect() as c:
        assert c.execute(sa.text(
            "SELECT COUNT(*) FROM llm_call_audit")).scalar() == 1
        assert c.execute(sa.text(
            "SELECT nombre FROM usuarios WHERE id=1")).scalar() == "Prev"
        # Las columnas nuevas son nullable: la fila previa las deja a NULL.
        assert c.execute(sa.text(
            "SELECT ciclo_id FROM llm_call_audit "
            "WHERE call_id='llm-previa'")).scalar() is None
        assert c.execute(sa.text(
            "SELECT version_num FROM alembic_version")).scalar() == \
            "0005_telemetria_http"


def test_0005_solo_agrega_no_altera_ni_borra():
    fuente = MIGRACION.read_text(encoding="utf-8")
    upgrade = fuente.split("def upgrade")[1].split("def downgrade")[0]
    for prohibido in ("drop_table", "drop_column", "DELETE", "UPDATE ",
                      "alter_column"):
        assert prohibido not in upgrade, f"la migracion no debe usar {prohibido}"


def test_0005_usa_tipos_portables():
    """Nada especifico de PostgreSQL: el mismo esquema vale en SQLite."""
    arbol = ast.parse(MIGRACION.read_text(encoding="utf-8"))
    # Se inspecciona el CODIGO, no los comentarios: el docstring explica
    # precisamente por que no se usa JSONB, y nombrarlo no es usarlo.
    codigo = [n for n in arbol.body
              if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    volcado = "\n".join(ast.dump(n) for n in codigo)
    for especifico in ("JSONB", "postgresql", "ARRAY", "UUID", "dialects"):
        assert especifico not in volcado, f"tipo no portable: {especifico}"


def test_status_counts_sobrevive_el_viaje_de_ida_y_vuelta_en_sqlite(url_tmp):
    from alembic import command

    command.upgrade(_alembic(url_tmp), "head")
    engine = sa.create_engine(url_tmp)
    Sesion = sessionmaker(bind=engine)

    m = MedidorCicloHttp("ciclo-json")
    op = m.operacion("binance", "get_multiple_prices")
    for _ in range(3):
        with op.peticion() as p:
            p.anotar_status(200)
    with op.peticion() as p:
        p.marcar_error(429)
    assert m.volcar(session_factory=Sesion) == 1

    with Sesion() as db:
        fila = db.query(models.CicloHttpAudit).one()
    assert json.loads(fila.status_counts) == {"200": 3, "429": 1}
    assert fila.n_requests == 4 and fila.n_ok == 3 and fila.n_error == 1


def test_el_modelo_y_la_migracion_declaran_las_mismas_columnas(url_tmp):
    """Alembic sigue siendo la unica autoridad: no puede haber desfase."""
    from alembic import command

    command.upgrade(_alembic(url_tmp), "head")
    insp = sa.inspect(sa.create_engine(url_tmp))
    for tabla in ("ciclo_http_audit", "llm_call_audit"):
        en_bd = {c["name"] for c in insp.get_columns(tabla)}
        en_modelo = {c.name for c in models.Base.metadata.tables[tabla].columns}
        assert en_modelo == en_bd, (
            f"{tabla}: el modelo y la migracion han divergido "
            f"(solo modelo: {en_modelo - en_bd}, solo BD: {en_bd - en_modelo})")


# ═══════════════════════════════════════════════════════════════════════════
# EL ENTORNO NO CAMBIA
# ═══════════════════════════════════════════════════════════════════════════
def test_importar_main_sigue_siendo_inocuo(monkeypatch):
    """0 conexiones · 0 DDL · 0 trading loops."""
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

    assert conexiones == [], "importar no debe abrir conexiones"
    assert ddl == [], "importar no debe ejecutar DDL"
    assert not [t for t in threading.enumerate() if t.name != "MainThread"], \
        "importar no debe arrancar trading loops"


def test_importar_la_telemetria_http_no_toca_la_base():
    """El modulo solo usa stdlib al importarse; la BD se resuelve al volcar."""
    arbol = ast.parse((RAIZ / "backend/telemetria_http.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:                    # SOLO nivel de modulo
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            volcado = ast.dump(nodo)
            assert "backend" not in volcado, (
                "importar telemetria_http no puede arrastrar el backend entero")


def test_la_telemetria_http_no_se_acopla_al_flujo_de_ordenes():
    arbol = ast.parse((RAIZ / "backend/telemetria_http.py").read_text(encoding="utf-8"))
    prohibidos = ("real_trading_connector", "ordenes_repo", "motor",
                  "reconciliacion", "carteras")
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            volcado = ast.dump(nodo)
            for p in prohibidos:
                assert p not in volcado, f"la telemetria no debe acoplarse a {p}"


def test_paper_sigue_activo():
    from backend.config import settings
    assert settings.TRADING_MODE == "PAPER"
    assert settings.MODO_REAL is False


def test_ninguna_prueba_de_este_modulo_sale_a_la_red():
    """Guarda: aqui no puede aparecer una URL real invocada de verdad."""
    fuente = pathlib.Path(__file__).read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            if nodo.func.attr in ("get", "post") and \
                    getattr(nodo.func.value, "id", None) in ("requests", "urllib"):
                pytest.fail(f"linea {nodo.lineno}: peticion real en una prueba")
    assert not re.search(r"api\.openai\.com|api\.binance\.com", fuente)
