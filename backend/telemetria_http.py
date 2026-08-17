"""
Telemetria HTTP del ciclo de mercado  (Fase BOT 2.0-02A).

MIDE, NO OPTIMIZA. Esta fase no cambia decisiones de trading, ni el prompt de
negocio, ni el modelo, ni WAIT_TIME, ni el riesgo, ni el scheduling. Su unico
proposito es responder con datos -no con estimaciones- a estas preguntas:

    ¿cuantas peticiones HTTP hace realmente un ciclo?
    ¿a que proveedor y en que operacion se van?
    ¿cuanto tiempo de pared se consume ANTES de llamar al LLM?

PRINCIPIO DE ROBUSTEZ (identico al de 02-01)
    Un fallo de telemetria NUNCA puede convertirse en una operacion de trading.
    Ni al medir ni al persistir. `volcar()` no propaga excepciones y ninguna
    decision depende de su retorno. Si la persistencia falla se informa por
    consola y el ciclo continua EXACTAMENTE igual. La telemetria no puede
    habilitar una operacion que de otro modo se habria rechazado.

    Los medidores tampoco alteran el flujo de control: `peticion()` re-lanza
    cualquier excepcion que envuelva, sin tocarla.

IDENTIDAD DEL CICLO
    `ciclo_id` es EXCLUSIVAMENTE TELEMETRICO. No sustituye ni modifica la
    semantica de `ciclo`, `EVALUAR_CADA_N_CICLOS`, las decisiones, el
    MotorRiesgo, las ordenes ni el scheduling. Existe porque `ciclo` se
    incrementa en cinco ramas distintas de trading_loop -varias dentro de un
    `continue`-, de modo que un mismo recorrido puede incrementarlo varias
    veces o ninguna: no sirve como identidad. `ciclo_num` se conserva junto a
    cada fila solo como dato diagnostico legacy.

GRANULARIDAD
    Una fila por (ciclo_id, proveedor, operacion). Por peticion serian ~1.895
    filas por ciclo (~4,1 M al ano); agregado son ~7 filas por ciclo (~15 k al
    ano). `latencia_media_ms` NO se persiste: es derivable
    (latencia_total_ms / n_requests) y duplicar estado invita a
    inconsistencias.

PRIVACIDAD
    No se guarda ninguna URL, cabecera, cuerpo ni credencial. Solo contadores,
    tiempos y codigos de estado. Ver `redactar` para el saneamiento de los
    mensajes que SI van a consola.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

# Clave usada en `status_counts` cuando la peticion termino pero el codigo HTTP
# no esta disponible. Desconocido no es 200: no se fabrica un exito.
SIN_STATUS = "SIN_STATUS"

PROVEEDOR_INTERNO = "interno"
OPERACION_FASE_PRE_LLM = "fase_pre_llm"


def nuevo_ciclo_id() -> str:
    """Identidad telemetrica de una iteracion del bucle. Solo para medir."""
    return f"ciclo-{uuid.uuid4().hex}"


# ─────────────────────────────────────────────────────────────────────────────
# SANEAMIENTO DE SECRETOS EN MENSAJES
#
# `requests` incluye la URL COMPLETA -con query params- en el mensaje de sus
# excepciones. Un `print(f"...: {e}")` sobre una peticion que lleva
# `auth_token=` en los parametros publica la credencial en los logs. Le paso a
# CryptoPanic en el baseline (news_connector.py).
#
# La redaccion es generica y por LISTA DE CLAVES, no por proveedor: cualquier
# conector que use estos nombres queda cubierto sin volver a tocar el helper.
# ─────────────────────────────────────────────────────────────────────────────
CLAVES_SENSIBLES = (
    "auth_token", "access_token", "refresh_token", "api_key", "apikey",
    "api_secret", "apisecret", "secret", "signature", "token", "key",
    "password", "passwd", "pwd",
)

_PATRON_CLAVE_VALOR = re.compile(
    r"(?i)(?<![\w-])(" + "|".join(CLAVES_SENSIBLES) + r")"
    # Separador. La comilla de cierre opcional cubre los dicts en un repr:
    # {'api_key': 'xxx'}, donde la clave llega entrecomillada.
    r"(['\"]?\s*[=:]\s*)"
    r"(['\"]?)"                          # comilla opcional de apertura
    r"([^&\s'\"<>,;)\}\]]+)"             # el valor, hasta el siguiente limite
)

# `Authorization: Bearer xxx`, `Authorization=Basic yyy` y los esquemas sueltos.
_PATRON_AUTORIZACION = re.compile(
    r"(?i)(?<![\w-])(authorization)(['\"]?\s*[=:]\s*)(['\"]?)([^'\"\r\n,;)\}\]]+)"
)
_PATRON_ESQUEMA = re.compile(r"(?i)(?<![\w-])(bearer|basic)(\s+)([A-Za-z0-9._\-+/=]+)")

REDACTADO = "***REDACTADO***"


def redactar(texto) -> str:
    """
    Elimina de un texto los valores de claves sensibles.

    Pensado para mensajes que van a consola o a un log. Nunca lanza: si algo
    va mal devuelve una cadena sin contenido util, porque publicar el original
    sin sanear seria peor que perder el detalle.
    """
    try:
        salida = texto if isinstance(texto, str) else str(texto)
        salida = _PATRON_AUTORIZACION.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTADO}", salida)
        salida = _PATRON_ESQUEMA.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{REDACTADO}", salida)
        salida = _PATRON_CLAVE_VALOR.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTADO}", salida)
        return salida
    except Exception:
        return "<mensaje no publicable: fallo al sanear>"


def describir_error(e) -> str:
    """
    Representacion publicable de una excepcion: clase + mensaje SANEADO.

    Se conserva el mensaje porque sin el muchos fallos de red son
    indiagnosticables, pero jamas con credenciales dentro.
    """
    try:
        return f"{type(e).__name__}: {redactar(e)}"
    except Exception:
        return "<error no publicable>"


def _status_de(objeto) -> Optional[int]:
    """Extrae un codigo HTTP de una respuesta o de una excepcion, si lo hay."""
    try:
        directo = getattr(objeto, "status_code", None)
        if isinstance(directo, int):
            return directo
        respuesta = getattr(objeto, "response", None)
        anidado = getattr(respuesta, "status_code", None)
        if isinstance(anidado, int):
            return anidado
    except Exception:
        pass
    return None


class ObservadorRespuesta:
    """
    Atribuye un codigo HTTP a LA peticion en curso, nunca a una anterior.

    POR QUE EXISTE
        Algunos clientes -python-binance entre ellos- solo exponen la ultima
        respuesta en un atributo del cliente (`client.response`). Leerlo sin
        mas es inseguro: si la peticion B falla ANTES de producir respuesta, el
        atributo sigue conteniendo la de A, y B quedaria registrada con el
        codigo de A. Se comprobo que ocurria: A=200 seguido de B fallida
        producia status_counts {"200": 2}.

    COMO LO EVITA
        Guarda la respuesta ANTERIOR al entrar y compara por IDENTIDAD al
        salir. Si no hay una respuesta NUEVA, el codigo es desconocido -> None
        -> SIN_STATUS. Nunca se hereda el anterior.

        Se conserva la referencia al objeto previo, no su id(): mantenerlo vivo
        impide que el recolector libere la direccion y otro objeto la reutilice,
        que haria fallar la comparacion.

    Es reutilizable entre peticiones: `antes()` vuelve a tomar la instantanea.
    """

    __slots__ = ("_leer", "_previa")

    def __init__(self, leer_respuesta):
        self._leer = leer_respuesta
        self._previa = None

    def antes(self) -> None:
        self._previa = self._leer_seguro()

    def status(self) -> Optional[int]:
        actual = self._leer_seguro()
        if actual is None or actual is self._previa:
            return None          # no hay respuesta NUEVA: desconocido
        return _status_de(actual)

    def _leer_seguro(self):
        try:
            return self._leer()
        except Exception:
            return None


def _preparar_observador(observador) -> None:
    try:
        if observador is not None:
            observador.antes()
    except Exception:
        pass


def _status_observado(observador) -> Optional[int]:
    try:
        return observador.status() if observador is not None else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# MEDICION
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class MetricasOperacionHttp:
    """
    Agregado de UNA operacion (proveedor, operacion) dentro de UN ciclo.

    `duracion_ms` es tiempo de PARED de la operacion completa y puede diferir
    de `latencia_total_ms`: la suma de latencias ignora el trabajo local entre
    peticiones, y con concurrencia podria incluso superarla.
    """

    proveedor: str
    operacion: str

    n_requests: int = 0
    n_ok: int = 0
    n_error: int = 0

    latencia_total_ms: int = 0
    latencia_max_ms: int = 0
    duracion_ms: Optional[int] = None

    # Significado por operacion (acordado en el diseno):
    #   exchange_info        simbolos devueltos
    #   account_balance      activos con saldo
    #   get_multiple_prices  precios obtenidos
    #   get_market_pairs     pares con precio
    #   noticias             titulares obtenidos
    #   fase_pre_llm         activos preparados para el prompt
    n_elementos: Optional[int] = None

    status_counts: Dict[str, int] = field(default_factory=dict)
    inicio: Optional[datetime] = None
    fin: Optional[datetime] = None

    @property
    def latencia_media_ms(self) -> Optional[float]:
        """Derivada, NO persistida. Sin peticiones es desconocida, no cero."""
        if not self.n_requests:
            return None
        return self.latencia_total_ms / self.n_requests

    def status_counts_json(self) -> Optional[str]:
        """JSON serializado: portable entre SQLite y PostgreSQL."""
        if not self.status_counts:
            return None
        try:
            return json.dumps(self.status_counts, sort_keys=True)
        except Exception:
            return None


class _Peticion:
    """
    Anotador de UNA peticion. El llamador puede precisar lo que el medidor no
    puede saber por si mismo.
    """

    __slots__ = ("status", "_ok")

    def __init__(self):
        self.status: Optional[int] = None
        self._ok: Optional[bool] = None

    def anotar_status(self, status) -> None:
        """
        Registra el codigo HTTP SIN pronunciarse sobre el exito.

        Que la peticion haya ido bien o mal lo decide el propio bloque: si
        despues lanza -por ejemplo un raise_for_status()- se contara como
        error, y este codigo sera el que explique por que.
        """
        if isinstance(status, int):
            self.status = status

    def marcar_ok(self, status: Optional[int] = None) -> None:
        self._ok = True
        if status is not None:
            self.status = status

    def marcar_error(self, status: Optional[int] = None) -> None:
        """
        Para fallos que NO llegan como excepcion.

        Varios metodos del conector de Binance capturan la excepcion dentro y
        devuelven 0.0 o []: sin esto, un fallo se contaria como exito.
        """
        self._ok = False
        if status is not None:
            self.status = status


class OperacionHttp:
    """Acumulador de una operacion. Ningun metodo altera el flujo de control."""

    def __init__(self, proveedor: str, operacion: str):
        self.metricas = MetricasOperacionHttp(proveedor=proveedor,
                                              operacion=operacion)
        self._t0: Optional[float] = None

    # ── API de medicion ────────────────────────────────────────────────────
    @contextmanager
    def peticion(self, *, observador=None, exige_evidencia=False):
        """
        Envuelve UNA peticion HTTP.

        No captura nada: si el bloque lanza, la excepcion se re-lanza intacta
        despues de anotarla.

        `observador` (ver ObservadorRespuesta) sirve para los clientes que solo
        exponen la ultima respuesta en un atributo global; garantiza que el
        codigo HTTP pertenece a ESTA peticion y no a la anterior.

        `exige_evidencia=True` para los bloques que envuelven un metodo LEGACY
        que captura sus propias excepciones y devuelve 0.0 o []. Ahi la
        ausencia de excepcion NO prueba nada, asi que sin evidencia positiva
        -una marca explicita del llamador o un codigo 2xx/3xx observado- la
        peticion se cuenta como fallida. Es la direccion segura: preferimos
        sobreestimar errores a inventar exitos.
        """
        self._abrir()
        registro = _Peticion()
        _preparar_observador(observador)
        inicio = time.perf_counter()
        try:
            yield registro
        except BaseException as e:
            self._anotar(registro, hubo_excepcion=True,
                         status_excepcion=_status_de(e),
                         status_observado=_status_observado(observador),
                         exige_evidencia=exige_evidencia,
                         latencia_ms=self._transcurrido(inicio))
            raise
        else:
            self._anotar(registro, hubo_excepcion=False, status_excepcion=None,
                         status_observado=_status_observado(observador),
                         exige_evidencia=exige_evidencia,
                         latencia_ms=self._transcurrido(inicio))
        finally:
            self._cerrar()

    def elementos(self, n) -> None:
        """Cuantos elementos utiles produjo la operacion. Nunca lanza."""
        try:
            self.metricas.n_elementos = None if n is None else int(n)
        except Exception:
            pass

    # ── Interno ────────────────────────────────────────────────────────────
    @staticmethod
    def _transcurrido(inicio: float) -> int:
        return max(0, int((time.perf_counter() - inicio) * 1000))

    def _abrir(self) -> None:
        if self.metricas.inicio is None:
            self.metricas.inicio = datetime.utcnow()
            self._t0 = time.perf_counter()

    def _cerrar(self) -> None:
        try:
            self.metricas.fin = datetime.utcnow()
            if self._t0 is not None:
                self.metricas.duracion_ms = max(
                    0, int((time.perf_counter() - self._t0) * 1000))
        except Exception:
            pass

    def _anotar(self, registro: _Peticion, *, hubo_excepcion: bool,
                status_excepcion: Optional[int], status_observado: Optional[int],
                exige_evidencia: bool, latencia_ms: int) -> None:
        try:
            m = self.metricas

            # Orden de fiabilidad del codigo HTTP, de mas a menos:
            #   1. el que anoto el llamador sobre la respuesta de ESTA peticion
            #   2. el que trae la propia excepcion
            #   3. el que el observador demuestra que es NUEVO
            # Nunca se hereda el de una peticion anterior: si no hay ninguno,
            # el codigo es desconocido (SIN_STATUS), no 200.
            status = registro.status
            if status is None:
                status = status_excepcion
            if status is None:
                status = status_observado

            # El exito NO se infiere de que Python no propagara una excepcion
            # cuando el bloque envuelve codigo que las captura por dentro.
            if hubo_excepcion:
                exito = False                     # lanzo: fallo, sin discusion
            elif registro._ok is not None:
                exito = registro._ok              # el llamador lo sabe
            elif status is not None:
                exito = 200 <= status < 400       # evidencia HTTP
            elif exige_evidencia:
                exito = False                     # sin evidencia no se afirma
            else:
                exito = True                      # el bloque si propaga fallos

            m.n_requests += 1
            if exito:
                m.n_ok += 1
            else:
                m.n_error += 1
            m.latencia_total_ms += latencia_ms
            m.latencia_max_ms = max(m.latencia_max_ms, latencia_ms)

            clave = str(status) if status is not None else SIN_STATUS
            m.status_counts[clave] = m.status_counts.get(clave, 0) + 1
        except Exception:
            # Medir jamas puede tumbar el ciclo.
            pass


class MedidorCicloHttp:
    """
    Medidor de UNA iteracion del bucle de trading.

    Se crea al inicio de la iteracion y se vuelca al final, pase lo que pase.
    """

    def __init__(self, ciclo_id: Optional[str] = None,
                 ciclo_num: Optional[int] = None):
        self.ciclo_id = ciclo_id or nuevo_ciclo_id()
        self.ciclo_num = ciclo_num
        self._inicio_dt = datetime.utcnow()
        self._inicio_perf = time.perf_counter()
        self._operaciones: Dict[tuple, OperacionHttp] = {}
        # Se marca SOLO tras un commit correcto: un volcado fallido debe poder
        # reintentarse, pero uno correcto no puede repetirse.
        self._volcado = False

    def operacion(self, proveedor: str, operacion: str) -> OperacionHttp:
        """Devuelve SIEMPRE el mismo acumulador para una clave dada."""
        clave = (proveedor, operacion)
        if clave not in self._operaciones:
            self._operaciones[clave] = OperacionHttp(proveedor, operacion)
        return self._operaciones[clave]

    def marcar_fase_pre_llm(self, n_activos=None) -> None:
        """
        Sella el tiempo de PARED desde el inicio del ciclo hasta el POST al LLM.

        Es la metrica que explica por que en el baseline pasaron ~8 m 10 s
        antes de gastar un solo token: no hay peticiones propias, solo
        duracion.
        """
        try:
            op = self.operacion(PROVEEDOR_INTERNO, OPERACION_FASE_PRE_LLM)
            op.metricas.inicio = self._inicio_dt
            op.metricas.fin = datetime.utcnow()
            op.metricas.duracion_ms = max(
                0, int((time.perf_counter() - self._inicio_perf) * 1000))
            op.elementos(n_activos)
        except Exception:
            pass

    def operaciones(self):
        return list(self._operaciones.values())

    def volcar(self, *, session_factory=None) -> int:
        """
        Persiste una fila por operacion. Devuelve cuantas se guardaron.

        NUNCA lanza. El valor devuelto es informativo y ningun camino de
        decision debe depender de el: si la base esta caida, el ciclo continua
        con exactamente el mismo resultado que habria tenido sin telemetria.

        IDEMPOTENTE: una segunda llamada correcta no escribe nada. Es la
        primera barrera contra la duplicacion; la segunda -y la autoritativa-
        es la restriccion UNIQUE sobre (ciclo_id, proveedor, operacion), que no
        depende de que este objeto siga vivo ni de que la agregacion en memoria
        se haya hecho bien.
        """
        try:
            if self._volcado or not self._operaciones:
                return 0
            if session_factory is None:
                from backend.app.database import SessionLocal as session_factory

            from backend.app import models

            filas = [
                models.CicloHttpAudit(
                    ciclo_id=self.ciclo_id,
                    ciclo_num=self.ciclo_num,
                    proveedor=op.metricas.proveedor,
                    operacion=op.metricas.operacion,
                    n_requests=op.metricas.n_requests,
                    n_ok=op.metricas.n_ok,
                    n_error=op.metricas.n_error,
                    latencia_total_ms=op.metricas.latencia_total_ms,
                    latencia_max_ms=op.metricas.latencia_max_ms,
                    duracion_ms=op.metricas.duracion_ms,
                    n_elementos=op.metricas.n_elementos,
                    status_counts=op.metricas.status_counts_json(),
                    inicio=op.metricas.inicio,
                    fin=op.metricas.fin,
                )
                for op in self._operaciones.values()
            ]
            with session_factory() as db:
                db.add_all(filas)
                db.commit()
            self._volcado = True
            return len(filas)
        except Exception as e:
            # Deliberadamente amplio: la telemetria jamas debe tumbar el bot ni
            # cambiar una decision. Se informa -saneado- y se sigue.
            print(f"[TELEMETRIA] No se pudo registrar la telemetria HTTP del "
                  f"ciclo ({describir_error(e)}). El comportamiento de trading "
                  f"no cambia.")
            return 0


# ─────────────────────────────────────────────────────────────────────────────
# OBJETOS NULOS
#
# Permiten que conectores y colectores acepten `medidor=None` sin sembrar el
# codigo de `if medidor is not None`. Un medidor ausente mide en el vacio; no
# cambia ninguna ruta de ejecucion.
# ─────────────────────────────────────────────────────────────────────────────
class _OperacionNula:
    @contextmanager
    def peticion(self, *, observador=None, exige_evidencia=False):
        yield _Peticion()

    def elementos(self, n) -> None:
        pass


class _MedidorNulo:
    ciclo_id = None
    ciclo_num = None

    def operacion(self, proveedor, operacion):
        return OPERACION_NULA

    def marcar_fase_pre_llm(self, n_activos=None) -> None:
        pass

    def operaciones(self):
        return []

    def volcar(self, *, session_factory=None) -> int:
        return 0


OPERACION_NULA = _OperacionNula()
MEDIDOR_NULO = _MedidorNulo()
