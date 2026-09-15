"""
Ciclo de vida del bucle de trading  (P0-13).

Antes, `threading.Thread(target=trading_loop).start()` estaba a nivel de modulo:
IMPORTAR backend.main arrancaba a operar. Con `uvicorn --reload` el proceso se
respawnea, y con `--workers N` hay N procesos: cada uno con su propio bucle
enviando ordenes. Nada lo impedia ni lo detectaba.

Ahora:
  - importar el modulo NO arranca nada;
  - el arranque es explicito, desde el lifespan de FastAPI;
  - antes de arrancar hay que GANAR un candado de liderazgo;
  - arrancar dos veces en el mismo proceso no crea un segundo hilo;
  - el apagado cooperativo espera al bucle antes de liberar el candado.

CANDADOS
  CandadoPostgres  usa pg_try_advisory_lock sobre una conexion dedicada. Es el
                   candado valido para produccion: funciona entre procesos y
                   entre maquinas, y se libera solo si la conexion muere.
  CandadoLocal     fichero con bloqueo exclusivo del sistema operativo. Sirve
                   para desarrollo y SQLite: cubre varios procesos en la misma
                   maquina, que es el escenario de `--reload` y `--workers`.

Se elige automaticamente segun DATABASE_URL. Si no se puede obtener el candado,
el bucle NO arranca y se registra el motivo: preferimos no operar a operar dos
veces.
"""
from __future__ import annotations

import os
import threading

# Identificador del candado advisory. Entero fijo, compartido por todos los
# procesos del bot. Cualquier valor sirve mientras sea el mismo en todos.
CLAVE_LIDERAZGO = 0x8077A01D


class CandadoNoDisponible(Exception):
    """El liderazgo ya lo tiene otro proceso."""


class CandadoLocal:
    """Bloqueo exclusivo por fichero. Cubre varios procesos en una maquina."""

    def __init__(self, ruta=None):
        self.ruta = ruta or os.path.join(
            os.environ.get("TEMP") or "/tmp", "bot_trading_lider.lock")
        self._handle = None

    def adquirir(self) -> bool:
        if self._handle is not None:
            return True
        try:
            handle = open(self.ruta, "a+")
            try:
                import msvcrt  # Windows
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except ImportError:
                import fcntl  # POSIX
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            try:
                handle.close()
            except Exception:
                pass
            return False
        self._handle = handle
        return True

    def liberar(self) -> None:
        if self._handle is None:
            return
        try:
            try:
                import msvcrt
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            except ImportError:
                import fcntl
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        finally:
            try:
                self._handle.close()
            finally:
                self._handle = None


class CandadoPostgres:
    """
    pg_try_advisory_lock sobre una conexion dedicada y mantenida abierta.

    El candado vive mientras viva la conexion: si el proceso muere, PostgreSQL
    lo libera solo. No hace falta TTL ni heartbeat.
    """

    def __init__(self, engine, clave=CLAVE_LIDERAZGO):
        self._engine = engine
        self._clave = clave
        self._conexion = None

    def adquirir(self) -> bool:
        if self._conexion is not None:
            return True
        from sqlalchemy import text
        conexion = self._engine.connect()
        try:
            obtenido = conexion.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": self._clave}
            ).scalar()
        except Exception:
            conexion.close()
            raise
        if not obtenido:
            conexion.close()
            return False
        self._conexion = conexion
        return True

    def liberar(self) -> None:
        if self._conexion is None:
            return
        from sqlalchemy import text
        try:
            self._conexion.execute(text("SELECT pg_advisory_unlock(:k)"),
                                   {"k": self._clave})
        except Exception:
            pass
        finally:
            self._conexion.close()
            self._conexion = None


def candado_por_defecto(database_url: str):
    """PostgreSQL en produccion, fichero en desarrollo/SQLite."""
    if database_url and database_url.startswith(("postgresql", "postgres")):
        from backend.app.database import engine
        return CandadoPostgres(engine)
    return CandadoLocal()


class CoordinadorTrading:
    """
    Unico responsable de arrancar y detener el bucle. Idempotente: llamarlo
    varias veces no crea hilos adicionales.

    Si se proporciona `stop_event`, el objetivo debe cooperar consultandolo o
    esperando sobre el. El candado de liderazgo NO se libera mientras el hilo
    siga vivo: es preferible fallar cerrado a permitir dos loops simultaneos.
    """

    def __init__(self, objetivo, candado=None, nombre="trading-loop",
                 precondiciones=(), stop_event=None, stop_timeout=10.0):
        self._objetivo = objetivo
        self._candado = candado
        self._nombre = nombre
        self._precondiciones = tuple(precondiciones)
        self._stop_event = stop_event
        self._stop_timeout = float(stop_timeout)
        self._hilo = None
        self._mutex = threading.Lock()
        self.es_lider = False
        self.motivo_inactivo = "no iniciado"

    @property
    def activo(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    def iniciar(self) -> bool:
        """Devuelve True si este proceso quedo como lider y el bucle corre."""
        with self._mutex:
            if self.activo:
                return True

            for verificar in self._precondiciones:
                ok, motivo = verificar()
                if not ok:
                    self.es_lider = False
                    self.motivo_inactivo = motivo
                    print(f"[COORDINADOR] Precondicion no cumplida: {motivo} "
                          f"Este proceso NO operara.")
                    return False

            if self._candado is not None and not self._candado.adquirir():
                self.es_lider = False
                self.motivo_inactivo = (
                    "otro proceso ya tiene el liderazgo del bucle de trading")
                print(f"[COORDINADOR] {self.motivo_inactivo}. Este proceso NO operara.")
                return False

            if self._stop_event is not None:
                self._stop_event.clear()

            self.es_lider = True
            self.motivo_inactivo = ""
            self._hilo = threading.Thread(target=self._objetivo, name=self._nombre,
                                          daemon=True)
            self._hilo.start()
            print(f"[COORDINADOR] Liderazgo obtenido. Bucle '{self._nombre}' iniciado.")
            return True

    def detener(self) -> bool:
        """Solicita parada y solo libera liderazgo cuando el hilo termino."""
        with self._mutex:
            hilo = self._hilo
            if self._stop_event is not None:
                self._stop_event.set()

        if (hilo is not None and hilo.is_alive()
                and hilo is not threading.current_thread()):
            hilo.join(timeout=self._stop_timeout)

        with self._mutex:
            if hilo is not None and hilo.is_alive():
                self.es_lider = True
                self.motivo_inactivo = "detencion pendiente: hilo aun activo"
                print("[COORDINADOR] Hilo aun activo; liderazgo retenido por seguridad.")
                return False

            self._hilo = None
            self.es_lider = False
            self.motivo_inactivo = "detenido"
            if self._candado is not None:
                self._candado.liberar()
            print("[COORDINADOR] Liderazgo liberado.")
            return True
