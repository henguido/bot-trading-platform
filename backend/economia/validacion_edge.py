"""Particion temporal para evaluar Expected Edge sin fuga entre periodos.

Nunca hace random split. Los cortes son timestamps globales compartidos por todos
los simbolos. Ademas aplica un embargo igual al horizonte maximo de etiqueta:
una observacion de train cuyo futuro de 24h pisaria validacion se EXCLUYE, no se
mueve artificialmente de conjunto.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

from backend.economia.edge_historico import ObservacionEdge

HORA_MS = 60 * 60 * 1000


@dataclass(frozen=True)
class ParticionesTemporales:
    train: Tuple[ObservacionEdge, ...]
    validacion: Tuple[ObservacionEdge, ...]
    test: Tuple[ObservacionEdge, ...]
    descartadas_embargo: Tuple[ObservacionEdge, ...]


def particionar_temporal(
    observaciones: Iterable[ObservacionEdge],
    *,
    corte_validacion_ms: int,
    corte_test_ms: int,
    embargo_horas: int = 24,
) -> ParticionesTemporales:
    """Divide por tiempo con embargo antes de cada corte.

    Semantica:
      train      : t < corte_validacion y t+embargo < corte_validacion
      validacion : t >= corte_validacion, t < corte_test y t+embargo < corte_test
      test       : t >= corte_test

    Las observaciones dentro de las zonas de embargo se conservan aparte para
    poder auditar cuantas se descartaron. Todos los simbolos con el mismo t van
    al mismo lado del corte: no existe particion aleatoria por fila.
    """
    if isinstance(corte_validacion_ms, bool) or not isinstance(corte_validacion_ms, int):
        raise ValueError("corte_validacion_ms debe ser entero")
    if isinstance(corte_test_ms, bool) or not isinstance(corte_test_ms, int):
        raise ValueError("corte_test_ms debe ser entero")
    if corte_validacion_ms < 0 or corte_test_ms <= corte_validacion_ms:
        raise ValueError("cortes temporales invalidos")
    if isinstance(embargo_horas, bool) or not isinstance(embargo_horas, int) or embargo_horas < 0:
        raise ValueError("embargo_horas debe ser entero no negativo")

    embargo_ms = embargo_horas * HORA_MS
    ordenadas = sorted(
        tuple(observaciones),
        key=lambda o: (o.estado.timestamp_ms, o.estado.symbol),
    )

    train = []
    valid = []
    test = []
    embargo = []

    for o in ordenadas:
        t = o.estado.timestamp_ms
        if t < corte_validacion_ms:
            if t + embargo_ms < corte_validacion_ms:
                train.append(o)
            else:
                embargo.append(o)
        elif t < corte_test_ms:
            if t + embargo_ms < corte_test_ms:
                valid.append(o)
            else:
                embargo.append(o)
        else:
            test.append(o)

    return ParticionesTemporales(
        train=tuple(train),
        validacion=tuple(valid),
        test=tuple(test),
        descartadas_embargo=tuple(embargo),
    )
