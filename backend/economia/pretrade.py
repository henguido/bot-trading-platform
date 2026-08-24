"""Orquestacion pre-trade minima para BOT 2.0-05A.

Garantiza el orden economico para COMPRAS NUEVAS:
    rentabilidad -> MotorRiesgo

Una compra NO puede llegar al MotorRiesgo si la rentabilidad es NO_APTA o
NO_EVALUABLE. Las VENTAS no se bloquean por rentabilidad: salir de una posicion
es una decision de riesgo/gestion y debe poder ocurrir aun con edge desconocido.

No ejecuta ordenes, no toca cartera, red ni BD.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.app.services.ordenes import Lado
from backend.economia.rentabilidad import EvaluacionRentabilidad
from backend.risk.motor import PropuestaOperacion


@dataclass(frozen=True)
class ResultadoPretrade:
    propuesta: PropuestaOperacion
    bloqueada_por_rentabilidad: bool
    motivo: Optional[str]
    rentabilidad: Optional[EvaluacionRentabilidad]
    veredicto_riesgo: Optional[Any]

    @property
    def llego_a_riesgo(self) -> bool:
        return self.veredicto_riesgo is not None


def evaluar_pretrade(*, propuesta: PropuestaOperacion,
                      rentabilidad: Optional[EvaluacionRentabilidad],
                      motor_riesgo, capital_disponible, estado) -> ResultadoPretrade:
    """Aplica rentabilidad a compras y luego delega SIEMPRE la autoridad a riesgo.

    Para COMPRA la evaluacion de rentabilidad es obligatoria y debe ser APTA.
    Para VENTA se ignora como gate porque el bot nunca debe quedar atrapado en
    una posicion por no poder demostrar edge de salida.
    """
    if not isinstance(propuesta, PropuestaOperacion):
        raise TypeError("propuesta debe ser PropuestaOperacion")

    if propuesta.side == Lado.COMPRA:
        if rentabilidad is None:
            return ResultadoPretrade(
                propuesta=propuesta,
                bloqueada_por_rentabilidad=True,
                motivo="RENTABILIDAD_AUSENTE",
                rentabilidad=None,
                veredicto_riesgo=None,
            )
        if not rentabilidad.apta:
            return ResultadoPretrade(
                propuesta=propuesta,
                bloqueada_por_rentabilidad=True,
                motivo=f"RENTABILIDAD_{rentabilidad.estado}",
                rentabilidad=rentabilidad,
                veredicto_riesgo=None,
            )

    veredicto = motor_riesgo.evaluar(
        propuesta,
        capital_disponible=capital_disponible,
        estado=estado,
    )
    return ResultadoPretrade(
        propuesta=propuesta,
        bloqueada_por_rentabilidad=False,
        motivo=None,
        rentabilidad=rentabilidad,
        veredicto_riesgo=veredicto,
    )
