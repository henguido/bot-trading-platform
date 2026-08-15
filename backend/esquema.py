"""
Comprobacion fail-safe del estado del esquema  (P0-16).

La aplicacion NO migra nunca. Solo puede MIRAR si la base esta en la revision
que el codigo espera y, si no lo esta, decirlo de forma explicita.

Invariante:
    codigo de aplicacion  ->  no modifica esquema
    alembic               ->  unica autoridad de migraciones

Nada de este modulo se ejecuta al importar: `estado_esquema()` abre conexion
solo cuando alguien la llama (por ejemplo GET /health).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

ALINEADO = "OK"
MIGRACION_REQUERIDA = "SCHEMA_MIGRATION_REQUIRED"
SIN_ALEMBIC = "SCHEMA_UNMANAGED"          # base sin tabla alembic_version
DESCONOCIDO = "SCHEMA_UNKNOWN"            # no se pudo determinar (BD inaccesible)


@dataclass(frozen=True)
class EstadoEsquema:
    estado: str
    revision_actual: Optional[str] = None
    revision_esperada: Optional[str] = None
    detalle: Optional[str] = None

    @property
    def alineado(self) -> bool:
        return self.estado == ALINEADO


def revision_esperada() -> Optional[str]:
    """Head de las migraciones del repositorio. No toca la base de datos."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    raiz = Path(__file__).resolve().parents[1]
    cfg = Config(str(raiz / "alembic.ini"))
    cfg.set_main_option("script_location", str(raiz / "migrations"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    return heads[0] if len(heads) == 1 else None


def estado_esquema(engine=None) -> EstadoEsquema:
    """
    Compara la revision de la base con el head del repositorio.

    SOLO LEE. No crea tablas, no aplica migraciones y no escribe nada. Si la
    base es inaccesible devuelve SCHEMA_UNKNOWN en lugar de propagar el error:
    la app debe poder arrancar y REPORTAR el problema, no morir en el import.
    """
    esperada = revision_esperada()

    if engine is None:
        from backend.app.database import engine as engine_por_defecto
        engine = engine_por_defecto

    try:
        from alembic.migration import MigrationContext
        with engine.connect() as conexion:
            actual = MigrationContext.configure(conexion).get_current_revision()
    except Exception as e:
        return EstadoEsquema(DESCONOCIDO, None, esperada,
                             f"{type(e).__name__}: no se pudo leer la revision")

    if actual is None:
        return EstadoEsquema(
            SIN_ALEMBIC, None, esperada,
            "la base no esta bajo control de Alembic. Si su esquema coincide con "
            "la baseline: `alembic stamp 0001_baseline` y despues "
            "`alembic upgrade head`. Nunca `stamp head`.")

    if actual != esperada:
        return EstadoEsquema(
            MIGRACION_REQUERIDA, actual, esperada,
            "la base esta en una revision anterior a la que el codigo espera. "
            "Ejecutar `alembic upgrade head` como paso explicito de despliegue.")

    return EstadoEsquema(ALINEADO, actual, esperada)
