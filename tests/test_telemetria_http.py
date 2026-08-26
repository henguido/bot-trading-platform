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
    cliente = _ClienteConResponse()
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    with op.peticion(observador=cliente.observador()):
        cliente.responde(429)
    assert op.metricas.status_counts == {"429": 1}
    assert (op.metricas.n_ok, op.metricas.n_error) == (0, 1)


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
    cliente = _ClienteConResponse()
    observador = cliente.observador()
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    with op.peticion(observador=observador):
        cliente.responde(200)
    with op.peticion(observador=observador, exige_evidencia=True) as p:
        p.marcar_error()
    assert op.metricas.status_counts == {"200": 1, SIN_STATUS: 1}
    assert op.metricas.status_counts.get("200") == 1
    assert (op.metricas.n_ok, op.metricas.n_error) == (1, 1)


def test_atribucion_4b_si_hay_respuesta_nueva_si_se_atribuye():
    cliente = _ClienteConResponse()
    observador = cliente.observador()
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    with op.peticion(observador=observador):
        cliente.responde(200)
    with op.peticion(observador=observador, exige_evidencia=True) as p:
        cliente.responde(429)
        p.marcar_error()
    assert op.metricas.status_counts == {"200": 1, "429": 1}


def test_atribucion_5_metodo_legacy_que_traga_la_excepcion(monkeypatch):
    from backend.connectors.crypto import binance_connector as bc
    conector = bc.BinanceConnector()
    cliente = _ClienteConResponse()
    monkeypatch.setattr(conector, "init_client", lambda: None)
    monkeypatch.setattr(conector, "client", cliente, raising=False)
    m = MedidorCicloHttp()
    cliente.get_all_tickers = lambda: (cliente.responde(200),
                                       [{"symbol": "BTCUSDT", "price": "100000.0"}])[1]
    op = m.operacion("binance", "market_price_snapshot")
    assert conector.get_price_snapshot(medicion=op) == {"BTCUSDT": 100000.0}
    def revienta():
        raise ConnectionError("la conexion murio antes de responder")
    cliente.get_all_tickers = revienta
    assert conector.get_price_snapshot(medicion=op) == {}
    assert (op.metricas.n_ok, op.metricas.n_error) == (1, 1)
    assert op.metricas.status_counts == {"200": 1, SIN_STATUS: 1}


def test_atribucion_5b_get_account_balance_vacio_sin_respuesta_no_es_exito(monkeypatch):
    from backend.utils import asset_collector as ac
    cliente = _ClienteConResponse()
    monkeypatch.setattr(ac.binance, "init_client", lambda: None)
    monkeypatch.setattr(ac.binance, "client", cliente, raising=False)
    monkeypatch.setattr(cliente, "get_exchange_info",
                        lambda: (cliente.responde(200), {"symbols": []})[1], raising=False)
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
    with op.peticion(observador=observador):
        cliente.responde(200)
    with op.peticion(observador=observador):
        cliente.responde(429)
    with pytest.raises(ConnectionError):
        with op.peticion(observador=observador):
            raise ConnectionError("sin red")
    with op.peticion(observador=observador, exige_evidencia=True) as p:
        p.marcar_error()
    with op.peticion():
        pass
    met = op.metricas
    assert met.n_requests == 5
    assert met.n_ok + met.n_error == met.n_requests
    assert (met.n_ok, met.n_error) == (2, 3)
    assert sum(met.status_counts.values()) == met.n_requests


def test_una_excepcion_anula_cualquier_marca_previa_de_exito():
    m = MedidorCicloHttp()
    op = m.operacion("binance", "x")
    with pytest.raises(RuntimeError):
        with op.peticion() as p:
            p.marcar_ok(200)
            raise RuntimeError("revento despues")
    assert (op.metricas.n_ok, op.metricas.n_error) == (0, 1)
    assert op.metricas.status_counts == {"200": 1}


def test_el_observador_no_confunde_objetos_reciclados():
    from backend.telemetria_http import ObservadorRespuesta
    caja = {"r": None}
    obs = ObservadorRespuesta(lambda: caja["r"])
    caja["r"] = SimpleNamespace(status_code=200)
    obs.antes()
    assert obs.status() is None
    caja["r"] = SimpleNamespace(status_code=503)
    assert obs.status() == 503


def test_ningun_punto_de_medicion_usa_ultima_respuesta_directamente():
    for ruta in ("backend/main.py", "backend/utils/asset_collector.py",
                 "backend/connectors/crypto/binance_connector.py"):
        arbol = ast.parse((RAIZ / ruta).read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not (isinstance(nodo, ast.Call)
                    and getattr(nodo.func, "attr", None) == "peticion"):
                continue
            volcado = ast.dump(nodo)
            assert "ultima_respuesta" not in volcado
            assert "status_de" not in volcado


# ═══════════════════════════════════════════════════════════════════════════
# CARDINALIDAD PROTEGIDA POR LA BASE DE DATOS
# ═══════════════════════════════════════════════════════════════════════════
NOMBRE_UNICO = "uq_ciclo_http_audit_ciclo_proveedor_operacion"


def test_el_modelo_declara_la_unica():
    unicas = {c.name: sorted(col.name for col in c.columns)
              for c in models.CicloHttpAudit.__table__.constraints
              if isinstance(c, sa.UniqueConstraint)}
    assert NOMBRE_UNICO in unicas
    assert unicas[NOMBRE_UNICO] == ["ciclo_id", "operacion", "proveedor"]


def test_la_base_rechaza_dos_filas_con_la_misma_clave(bd):
    import sqlalchemy.exc as saexc
    def fila():
        return models.CicloHttpAudit(ciclo_id="ciclo-dup", proveedor="binance",
                                     operacion="get_multiple_prices", n_requests=1,
                                     n_ok=1, n_error=0)
    with bd() as db:
        db.add(fila()); db.commit()
    with bd() as db:
        db.add(fila())
        with pytest.raises(saexc.IntegrityError):
            db.commit()
    with bd() as db:
        assert db.query(models.CicloHttpAudit).count() == 1


def test_un_doble_volcar_accidental_no_duplica_ni_lanza(bd):
    m = MedidorCicloHttp("ciclo-doble")
    op = m.operacion("binance", "get_multiple_prices")
    for _ in range(3):
        with op.peticion() as p:
            p.anotar_status(200)
    assert m.volcar(session_factory=bd) == 1
    assert m.volcar(session_factory=bd) == 0
    with bd() as db:
        filas = db.query(models.CicloHttpAudit).all()
    assert len(filas) == 1 and filas[0].n_requests == 3


def test_un_volcado_fallido_si_puede_reintentarse(bd):
    def caida():
        raise RuntimeError("base de datos caida")
    m = MedidorCicloHttp("ciclo-reintento")
    with m.operacion("binance", "x").peticion():
        pass
    assert m.volcar(session_factory=caida) == 0
    assert m.volcar(session_factory=bd) == 1


# ═══════════════════════════════════════════════════════════════════════════
# LATENCIAS, PRIVACIDAD, FAIL-OPEN Y ciclo_id
# ═══════════════════════════════════════════════════════════════════════════
def test_latencia_total_y_maxima_y_media_derivable():
    m = MedidorCicloHttp(); op = m.operacion("binance", "x")
    for espera in (0.01, 0.03, 0.01):
        with op.peticion(): time.sleep(espera)
    met = op.metricas
    assert met.latencia_total_ms >= 45
    assert met.latencia_max_ms >= 28
    assert met.latencia_media_ms == pytest.approx(met.latencia_total_ms / met.n_requests)


def test_la_media_de_cero_peticiones_es_desconocida_no_cero():
    from backend.telemetria_http import MetricasOperacionHttp
    assert MetricasOperacionHttp("binance", "x").latencia_media_ms is None


def test_latencia_media_no_se_persiste():
    columnas = {c.name for c in models.CicloHttpAudit.__table__.columns}
    assert "latencia_media_ms" not in columnas
    assert {"latencia_total_ms", "latencia_max_ms"} <= columnas


def test_ciclo_http_audit_no_tiene_columnas_de_contenido():
    columnas = {c.name for c in models.CicloHttpAudit.__table__.columns}
    for prohibida in ("url", "headers", "cabeceras", "token", "api_key", "auth",
                      "params", "body", "cuerpo", "respuesta", "mensaje", "secret", "key"):
        assert prohibida not in columnas


def test_status_counts_es_texto_portable():
    assert isinstance(models.CicloHttpAudit.__table__.c.status_counts.type, sa.Text)


def test_volcar_con_la_base_caida_no_lanza_y_devuelve_cero(capsys):
    def fabrica_rota(): raise RuntimeError("base de datos caida")
    m = MedidorCicloHttp("ciclo-sin-bd")
    with m.operacion("binance", "x").peticion(): pass
    assert m.volcar(session_factory=fabrica_rota) == 0
    assert "no cambia" in capsys.readouterr().out


def test_los_objetos_nulos_no_hacen_nada_y_no_lanzan():
    with OPERACION_NULA.peticion() as p:
        p.anotar_status(200); p.marcar_error(500)
    OPERACION_NULA.elementos(5)
    assert MEDIDOR_NULO.operaciones() == []
    assert MEDIDOR_NULO.volcar() == 0


def test_ciclo_id_es_unico_por_construccion():
    assert len({nuevo_ciclo_id() for _ in range(500)}) == 500
    assert nuevo_ciclo_id().startswith("ciclo-")


def test_ciclo_id_es_estable_dentro_del_medidor():
    m = MedidorCicloHttp(); visto = m.ciclo_id
    for _ in range(10):
        with m.operacion("binance", "x").peticion(): pass
        assert m.ciclo_id == visto


# ═══════════════════════════════════════════════════════════════════════════
# REDACCION DE SECRETOS
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("texto", [
    f"403 Client Error for url: https://cryptopanic.com/api/v1/posts/?auth_token={AUTH_TOKEN_FALSO}&public=true",
    f"HTTPError: https://newsapi.org/v2/everything?apiKey={API_KEY_FALSA}",
    f"{{'api_key': '{API_KEY_FALSA}'}}",
    f"Authorization: Bearer {API_KEY_FALSA}",
    f"signature={AUTH_TOKEN_FALSO}&timestamp=1",
])
def test_redactar_elimina_el_valor_sensible(texto):
    salida = redactar(texto)
    assert AUTH_TOKEN_FALSO not in salida
    assert API_KEY_FALSA not in salida
    assert "REDACTADO" in salida


def test_describir_error_conserva_la_clase_y_sanea_el_mensaje():
    e = ValueError(f"fallo con auth_token={AUTH_TOKEN_FALSO}")
    salida = describir_error(e)
    assert salida.startswith("ValueError:")
    assert AUTH_TOKEN_FALSO not in salida


# ═══════════════════════════════════════════════════════════════════════════
# MIGRACION 0005
# ═══════════════════════════════════════════════════════════════════════════
MIGRACION = RAIZ / "migrations" / "versions" / "0005_telemetria_http.py"


def _alembic(url):
    import importlib
    import os
    from alembic.config import Config
    os.environ["DATABASE_URL"] = url
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


def test_0005_declara_su_revision_y_encadena_con_0004():
    """Prueba 0005 como migracion historica, sin exigir que siga siendo head."""
    fuente = MIGRACION.read_text(encoding="utf-8")
    assert 'revision = "0005_telemetria_http"' in fuente
    assert 'down_revision = "0004_telemetria"' in fuente


def test_0005_sobre_bd_vacia_crea_la_tabla_y_las_columnas(url_tmp):
    from alembic import command
    command.upgrade(_alembic(url_tmp), "0005_telemetria_http")
    insp = sa.inspect(sa.create_engine(url_tmp))
    assert "ciclo_http_audit" in insp.get_table_names()
    columnas = {c["name"] for c in insp.get_columns("ciclo_http_audit")}
    assert {"ciclo_id", "ciclo_num", "proveedor", "operacion", "n_requests",
            "n_ok", "n_error", "latencia_total_ms", "latencia_max_ms",
            "duracion_ms", "n_elementos", "status_counts", "inicio", "fin"} <= columnas
    assert "latencia_media_ms" not in columnas
    llm = {c["name"] for c in insp.get_columns("llm_call_audit")}
    assert {"ciclo_id", "x_request_id", "error_type", "error_code",
            "rl_limit_requests", "rl_limit_tokens", "rl_remaining_requests",
            "rl_remaining_tokens", "rl_reset_requests", "rl_reset_tokens"} <= llm


def test_0005_sobre_bd_con_datos_previos_solo_agrega(url_tmp):
    """Una base con historico de 02-01 sobrevive intacta al aplicar SOLO 0005."""
    from alembic import command
    command.upgrade(_alembic(url_tmp), "0004_telemetria")
    engine = sa.create_engine(url_tmp)
    with engine.begin() as c:
        c.execute(sa.text("INSERT INTO llm_call_audit (call_id, proveedor, operacion, exito, costo_status) VALUES ('llm-previa', 'openai', 'analyze', 0, 'NO_DISPONIBLE')"))
        c.execute(sa.text("INSERT INTO usuarios (id,nombre,email,password_hash) VALUES (1,'Prev','p@e.com','h')"))
    command.upgrade(_alembic(url_tmp), "0005_telemetria_http")
    with engine.connect() as c:
        assert c.execute(sa.text("SELECT COUNT(*) FROM llm_call_audit")).scalar() == 1
        assert c.execute(sa.text("SELECT nombre FROM usuarios WHERE id=1")).scalar() == "Prev"
        assert c.execute(sa.text("SELECT ciclo_id FROM llm_call_audit WHERE call_id='llm-previa'")).scalar() is None
        assert c.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == "0005_telemetria_http"


def test_0005_solo_agrega_no_altera_ni_borra():
    fuente = MIGRACION.read_text(encoding="utf-8")
    upgrade = fuente.split("def upgrade")[1].split("def downgrade")[0]
    for prohibido in ("drop_table", "drop_column", "DELETE", "UPDATE ", "alter_column"):
        assert prohibido not in upgrade


def test_0005_usa_tipos_portables():
    arbol = ast.parse(MIGRACION.read_text(encoding="utf-8"))
    codigo = [n for n in arbol.body
              if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    volcado = "\n".join(ast.dump(n) for n in codigo)
    for especifico in ("JSONB", "postgresql", "ARRAY", "UUID", "dialects"):
        assert especifico not in volcado


def test_head_actual_incluye_0006_sin_invalidar_0005(url_tmp):
    """La evolucion posterior puede avanzar head conservando la migracion 0005."""
    from alembic import command
    from backend.esquema import revision_esperada
    command.upgrade(_alembic(url_tmp), "head")
    with sa.create_engine(url_tmp).connect() as c:
        assert c.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == revision_esperada()
    assert revision_esperada() == "0006_paper_ledger"


# ═══════════════════════════════════════════════════════════════════════════
# EL ENTORNO NO CAMBIA
# ═══════════════════════════════════════════════════════════════════════════
def test_importar_main_sigue_siendo_inocuo(monkeypatch):
    conexiones, ddl = [], []
    original = sa.engine.Engine.connect
    monkeypatch.setattr(sa.engine.Engine, "connect",
                        lambda self, *a, **k: (conexiones.append(1), original(self, *a, **k))[1])
    monkeypatch.setattr(sa.MetaData, "create_all", lambda self, *a, **k: ddl.append(1))
    monkeypatch.setattr(sa.MetaData, "drop_all", lambda self, *a, **k: ddl.append(1))
    import importlib
    import backend.main
    importlib.reload(backend.main)
    assert conexiones == [] and ddl == []
    assert not [t for t in threading.enumerate() if t.name != "MainThread"]


def test_paper_sigue_activo():
    from backend.config import settings
    assert settings.TRADING_MODE == "PAPER"
    assert settings.MODO_REAL is False
