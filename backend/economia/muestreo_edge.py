"""Muestreo temporal para evaluar Expected Edge sin pseudo-replicacion.

Las etiquetas a horizonte h se solapan si se evalua cada vela horaria. Para
medir capacidad predictiva sin inflar artificialmente el numero de eventos,
seleccionamos una rejilla UTC fija: una observacion cada h horas por timestamp,
conservando TODOS los simbolos presentes en ese timestamp.

Ejemplo h=4: cierres 04:00, 08:00, 12:00... (representados por close_time+1).
La etiqueta [04,08] no se solapa con la siguiente [08,12].
"""
from __future__ import annotations

from typing import Iterable, Tuple

from backend.economia.edge_historico import ObservacionEdge
from backend.economia.validacion_edge import HORA_MS


def submuestrear_no_solapado(
    observaciones: Iterable[ObservacionEdge],
    *,
    horizonte_horas: int,
    fase_horas: int = 0,
) -> Tuple[ObservacionEdge, ...]:
    """Devuelve observaciones sobre una rejilla UTC fija no solapada.

    `timestamp_ms` en EstadoHistorico es el close_time de la vela Binance
    (HH:59:59.999). Sumamos 1 ms para recuperar el limite horario exacto antes
    de aplicar modulo. `fase_horas` permite declarar la fase, pero no se elige
    automaticamente: cambiarla tras mirar resultados seria data snooping.
    """
    if isinstance(horizonte_horas, bool) or not isinstance(horizonte_horas, int) \
            or horizonte_horas <= 0:
        raise ValueError("horizonte_horas debe ser entero positivo")
    if isinstance(fase_horas, bool) or not isinstance(fase_horas, int) \
            or not 0 <= fase_horas < horizonte_horas:
        raise ValueError("fase_horas debe cumplir 0 <= fase < horizonte")

    salida = []
    for o in observaciones:
        t = o.estado.timestamp_ms
        if isinstance(t, bool) or not isinstance(t, int) or t < 0:
            raise ValueError("timestamp_ms invalido")
        limite_hora = t + 1
        # Los datos Binance reales cierran en el milisegundo anterior al limite.
        # Si una fuente distinta no esta alineada, se rechaza: no redondeamos.
        if limite_hora % HORA_MS:
            raise ValueError(f"timestamp no alineado a vela horaria: {t}")
        indice_hora = limite_hora // HORA_MS
        if indice_hora % horizonte_horas == fase_horas:
            salida.append(o)

    return tuple(sorted(
        salida, key=lambda o: (o.estado.timestamp_ms, o.estado.symbol)))
