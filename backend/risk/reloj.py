"""
Fuente UNICA de tiempo para el motor de riesgo.

Ningun otro modulo debe usar date.today() ni datetime.now() para decidir a que
"dia de riesgo" pertenece una operacion. Todo pasa por aqui.

DEFINICION DEL DIA DE RIESGO
    Cripto opera 24/7, asi que no hay cierre de mercado natural. El corte es
    convencional: el dia de riesgo va de las 00:00:00 a las 23:59:59.999999
    en la zona settings.RISK_TIMEZONE (por defecto America/Costa_Rica, la
    misma que ya usaba el proyecto para presentar timestamps).

    inicio  ->  00:00:00.000000 hora local de RISK_TIMEZONE
    fin     ->  00:00:00.000000 del dia siguiente (limite superior EXCLUSIVO)

CAMBIO DE DIA
    No hay ningun estado en memoria que "se reinicie". El dia de riesgo se
    deriva del reloj y el P&L se recalcula desde las transacciones de esa
    ventana. Cruzar la medianoche cambia la ventana y, por tanto, el resultado.

ALMACENAMIENTO
    Transaction.fecha_operacion se guarda con datetime.utcnow(), es decir UTC
    SIN tzinfo. Por eso las ventanas se devuelven tambien en UTC naive: es la
    unica forma de compararlas con la columna sin conversiones implicitas.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytz

from backend.config import settings


def zona_riesgo():
    return pytz.timezone(settings.RISK_TIMEZONE)


def ahora_utc() -> datetime:
    """Instante actual en UTC, con tzinfo."""
    return datetime.now(timezone.utc)


def dia_de_riesgo(momento: datetime | None = None) -> date:
    """
    Dia de riesgo al que pertenece `momento`.

    Acepta datetimes con tzinfo o naive. Los naive se interpretan como UTC,
    que es como los guarda la base de datos.
    """
    if momento is None:
        momento = ahora_utc()
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(zona_riesgo()).date()


def ventana_utc(dia: date) -> tuple[datetime, datetime]:
    """
    Limites [inicio, fin) del dia de riesgo, en UTC naive.

    `fin` es exclusivo: pertenece ya al dia siguiente.
    """
    zona = zona_riesgo()
    inicio_local = zona.localize(datetime.combine(dia, time.min))
    fin_local = zona.localize(datetime.combine(dia + timedelta(days=1), time.min))
    return (
        inicio_local.astimezone(timezone.utc).replace(tzinfo=None),
        fin_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def ventana_actual() -> tuple[datetime, datetime]:
    return ventana_utc(dia_de_riesgo())
