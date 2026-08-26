"""Estado operativo derivado para la consola PAPER.

No hace red, no escribe DB y no participa en decisiones. Convierte el estado
contable ya reconstruido y la configuracion canonica en un contrato pequeno y
explicito para la UI: motor activo, gate de rentabilidad, capital desplegado,
calidad de la valoracion y disponibilidad de evidencia por estrategia.
"""
from __future__ import annotations

from backend.config import settings
from backend.economia.integracion_05e import PROFITABILITY_GATE_05E_ENABLED


def _porcentaje(numerador, denominador):
    if denominador is None or float(denominador) <= 0:
        return None
    return float(numerador) / float(denominador) * 100.0


def construir_estado_operativo(*, estado, valoracion_completa: bool,
                               estrategias_paper: dict) -> dict:
    """Construye telemetria de lectura; nunca habilita ni bloquea operaciones."""
    inicial = float(estado.initial_capital_usd)
    capital = float(estado.capital_usd)
    desplegado = float(estado.exposicion_coste_usd)
    realizado = float(estado.realized_pnl_usd)

    estrategias = (
        estrategias_paper.get("estrategias", {})
        if isinstance(estrategias_paper, dict) else {}
    )
    cierres = sum(
        int(fila.get("cierres", 0) or 0)
        for fila in estrategias.values()
        if isinstance(fila, dict)
    )

    motor = str(settings.DECISION_ENGINE)
    if motor == "SAFE_NO_TRADE":
        estado_motor = "OBSERVACION_SIN_COMPRAS"
        descripcion_motor = "Motor seguro sin IA: solo observa y no abre compras nuevas."
    else:
        estado_motor = "DECISION_ASISTIDA"
        descripcion_motor = (
            "GPT propone decisiones; MotorRiesgo conserva la autoridad de sizing y aprobacion."
        )

    gate_activo = bool(PROFITABILITY_GATE_05E_ENABLED)
    mensajes = []
    if not gate_activo:
        mensajes.append(
            "Gate 05E desactivado: la evidencia OOS aun no ha promovido el filtro de rentabilidad."
        )
    if not valoracion_completa:
        mensajes.append(
            "Valoracion parcial: al menos una posicion abierta carece de precio publico."
        )
    if cierres == 0:
        mensajes.append(
            "Aun no hay cierres PAPER atribuidos por estrategia; no existe P&L realizado comparable."
        )

    return {
        "modo": "PAPER",
        "live_orders_enabled": False,
        "decision_engine": motor,
        "decision_engine_status": estado_motor,
        "decision_engine_description": descripcion_motor,
        "profitability_gate_05e_enabled": gate_activo,
        "profitability_gate_05e_status": (
            "ACTIVO_PAPER" if gate_activo else "PENDIENTE_EVIDENCIA_OOS"
        ),
        "paper_execution_model": "ORDER_BOOK_VWAP_TAKER_FEE",
        "paper_ledger_source": "PAPER_OPERACIONES",
        "valoracion_completa": bool(valoracion_completa),
        "capital_inicial_usd": inicial,
        "capital_disponible_usd": capital,
        "capital_desplegado_usd": desplegado,
        "capital_desplegado_pct": _porcentaje(desplegado, inicial),
        "retorno_realizado_pct": _porcentaje(realizado, inicial),
        "estrategias_con_cierres": sum(
            1 for fila in estrategias.values()
            if isinstance(fila, dict) and int(fila.get("cierres", 0) or 0) > 0
        ),
        "cierres_atribuidos": cierres,
        "evidencia_estrategias_status": (
            "DISPONIBLE" if cierres > 0 else "SIN_CIERRES_REALIZADOS"
        ),
        "mensajes": mensajes,
    }
