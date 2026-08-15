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
  - el apagado libera el candado.

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
    """

    def __init__(self, objetivo, candado=None, nombre="trading-loop",
                 precondiciones=()):
        self._objetivo = objetivo
        self._candado = candado
        self._nombre = nombre
        # Cada precondicion es un callable que devuelve (ok: bool, motivo: str).
        # Se evaluan ANTES de pedir el candado: un proceso que no puede operar
        # no debe retener el liderazgo y bloquear a otro que si podria.
        self._precondiciones = tuple(precondiciones)
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
                return True                     # ya somos lider: no duplicar

            # Fallo cerrado: si una precondicion no se cumple, no se opera.
            # Se comprueba antes del candado para no retener el liderazgo.
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

            self.es_lider = True
            self.motivo_inactivo = ""
            self._hilo = threading.Thread(target=self._objetivo, name=self._nombre,
                                          daemon=True)
            self._hilo.start()
            print(f"[COORDINADOR] Liderazgo obtenido. Bucle '{self._nombre}' iniciado.")
            return True

    def detener(self) -> None:
        with self._mutex:
            self._hilo = None
            self.es_lider = False
            self.motivo_inactivo = "detenido"
            if self._candado is not None:
                self._candado.liberar()
            print("[COORDINADOR] Liderazgo liberado.")
