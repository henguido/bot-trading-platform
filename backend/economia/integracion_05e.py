"""Contrato de integración del Profitability Gate para BOT 2.0-05E.

Este módulo prepara el punto de unión scanner -> rentabilidad -> LLM -> riesgo,
pero NO activa el gate todavía. La evidencia OOS de 05C/05D sigue acumulándose.

Invariantes de esta fase:
- desactivado por defecto;
- desactivado => cero red adicional y cero cambios sobre los candidatos;
- LIVE no puede usar 05E mientras esta fase siga experimental;
- si se activa en PAPER, una compra debe pasar 05A antes del LLM;
- después del LLM, una compra vuelve a comprobar que su evaluación pre-LLM era
  APTA antes de poder llegar al MotorRiesgo;
- las posiciones abiertas/ventas no quedan atrapadas por el gate de compra.

No interpreta variables de entorno: settings.py sigue siendo la única fuente
canónica de configuración. La activación permanece deliberadamente congelada
en código hasta que exista evidencia suficiente para promover la fase.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from backend.config import settings
from backend.economia.filtro_rentabilidad_05a import (
    ResumenFiltroRentabilidad,
    filtrar_compras_rentables,
)

# Congelado en False durante 05E. No se cambia por .env ni por prompt/LLM.
PROFITABILITY_GATE_05E_ENABLED = False


@dataclass(frozen=True)
class ResultadoPreLLM05E:
    activos: tuple
    evaluaciones: Dict[str, dict]
    aplicado: bool
    motivo: str
    resumen: Optional[ResumenFiltroRentabilidad] = None


def aplicar_pre_llm_05e(
    activos: Sequence[dict],
    metricas_por_symbol,
    *,
    fee_taker_bps_por_lado,
    notional_por_symbol,
    binance,
    medidor=None,
    ahora_ms=None,
    enabled: bool = PROFITABILITY_GATE_05E_ENABLED,
    modo_real: Optional[bool] = None,
) -> ResultadoPreLLM05E:
    """Aplica 05A antes del LLM solo cuando 05E esté explícitamente habilitado.

    Mientras `enabled=False` devuelve los mismos objetos, en el mismo orden, y
    no toca `binance`. Esto permite cablear el adaptador sin alterar todavía el
    comportamiento del trading_loop.
    """
    activos = tuple(activos or ())
    real = settings.MODO_REAL if modo_real is None else bool(modo_real)

    if not enabled:
        return ResultadoPreLLM05E(
            activos=activos,
            evaluaciones={},
            aplicado=False,
            motivo="DESACTIVADO_PENDIENTE_EVIDENCIA_OOS",
            resumen=None,
        )

    if real:
        raise RuntimeError("05E experimental no puede activarse en LIVE")

    resumen = ResumenFiltroRentabilidad()
    filtrados, evaluaciones = filtrar_compras_rentables(
        activos,
        metricas_por_symbol,
        fee_taker_bps_por_lado=fee_taker_bps_por_lado,
        notional_por_symbol=notional_por_symbol,
        binance=binance,
        medidor=medidor,
        ahora_ms=ahora_ms,
        resumen=resumen,
    )
    return ResultadoPreLLM05E(
        activos=tuple(filtrados),
        evaluaciones=dict(evaluaciones),
        aplicado=True,
        motivo="APLICADO_PAPER",
        resumen=resumen,
    )


def compra_post_llm_permitida_05e(
    symbol: str,
    evaluaciones: Dict[str, dict],
    *,
    enabled: bool = PROFITABILITY_GATE_05E_ENABLED,
) -> tuple[bool, str]:
    """Segunda cerradura antes del MotorRiesgo para decisiones COMPRAR.

    Desactivado conserva el comportamiento actual. Activado exige que el mismo
    símbolo haya quedado APTA en la evaluación pre-LLM; ausencia/desconocido no
    se interpreta como aprobado.
    """
    if not enabled:
        return True, "DESACTIVADO_PENDIENTE_EVIDENCIA_OOS"

    info = (evaluaciones or {}).get(symbol)
    if not isinstance(info, dict):
        return False, "SIN_EVALUACION_RENTABILIDAD"

    rent = info.get("rentabilidad")
    if rent is None or not bool(getattr(rent, "apta", False)):
        return False, "RENTABILIDAD_NO_APTA"
    return True, "RENTABILIDAD_APTA"
