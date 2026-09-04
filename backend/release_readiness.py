"""Evaluacion pura de readiness para PAPER v1.

No hace red, no migra la BD, no ejecuta ordenes y no modifica estado. Recibe
configuracion y estado de esquema ya resueltos para poder reutilizarse desde
CLI y /health sin duplicar reglas.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from backend.economia.fee_verificada import diagnosticar_fee_taker_manual


PAPER_V1_INITIAL_CAPITAL_USD = 500.0


@dataclass(frozen=True)
class Check:
    codigo: str
    nivel: str  # OK | WARN | BLOCKER
    detalle: str


def evaluar(
    config,
    esquema,
    *,
    profitability_gate_enabled: bool,
    environ=None,
    now=None,
):
    env = os.environ if environ is None else environ
    checks: list[Check] = []

    def add(codigo, nivel, detalle):
        checks.append(Check(codigo, nivel, detalle))

    if getattr(config, "MODO_REAL", False):
        add("MODO_PAPER", "BLOCKER", "MODO_REAL=True; PAPER v1 no puede declararse lista")
    elif getattr(config, "TRADING_MODE", "") != "PAPER":
        add("MODO_PAPER", "BLOCKER", "TRADING_MODE efectivo no es PAPER")
    else:
        add("MODO_PAPER", "OK", "PAPER activo; no se enviaran ordenes reales")

    if getattr(esquema, "alineado", False):
        add("ALEMBIC", "OK", f"esquema alineado en {esquema.revision_actual}")
    else:
        add(
            "ALEMBIC",
            "BLOCKER",
            f"esquema={esquema.estado} actual={esquema.revision_actual} esperada={esquema.revision_esperada}",
        )

    capital = float(getattr(config, "INITIAL_CAPITAL_USD", 0.0))
    if capital == PAPER_V1_INITIAL_CAPITAL_USD:
        add(
            "CAPITAL_PAPER",
            "OK",
            f"capital inicial={capital:.2f} USDT",
        )
    else:
        add(
            "CAPITAL_PAPER",
            "BLOCKER",
            f"capital inicial={capital:.2f} USDT; PAPER v1 exige baseline={PAPER_V1_INITIAL_CAPITAL_USD:.2f} USDT",
        )

    asignacion = float(getattr(config, "LIMITE_ASIGNACION_POR_OPERACION", 0.0))
    if 0 < asignacion <= 0.02:
        add("ASIGNACION", "OK", f"asignacion maxima={asignacion:.2%}")
    else:
        add(
            "ASIGNACION",
            "BLOCKER",
            f"asignacion={asignacion:.2%}; PAPER v1 exige un maximo de 2% por operacion",
        )

    perdida = float(getattr(config, "MAX_DAILY_LOSS_USDT", 0.0))
    add(
        "KILL_SWITCH",
        "OK" if perdida > 0 else "BLOCKER",
        f"perdida realizada diaria maxima={perdida:.2f} USDT",
    )
    if str(env.get("MAX_DAILY_LOSS_USDT", "")).strip():
        add("KILL_SWITCH_EXPLICITO", "OK", "MAX_DAILY_LOSS_USDT esta definida explicitamente")
    else:
        add(
            "KILL_SWITCH_EXPLICITO",
            "WARN",
            "usa el default de MAX_DAILY_LOSS_USDT; definirlo en .env elimina ambiguedad operativa",
        )

    engine = str(getattr(config, "DECISION_ENGINE", "")).upper()
    if engine not in {"GPT", "SAFE_NO_TRADE"}:
        add("DECISION_ENGINE", "BLOCKER", f"motor no reconocido: {engine!r}")
    elif engine == "GPT" and not getattr(config, "OPENAI_API_KEY", None):
        add("DECISION_ENGINE", "BLOCKER", "DECISION_ENGINE=GPT pero OPENAI_API_KEY no esta disponible")
    else:
        add("DECISION_ENGINE", "OK", f"motor={engine}")

    fee_manual = diagnosticar_fee_taker_manual(now, environ=env)
    tiene_credenciales_binance = bool(
        getattr(config, "BINANCE_API_KEY", None)
        and getattr(config, "BINANCE_API_SECRET", None)
    )
    if fee_manual["status"] == "VERIFICADA":
        add(
            "BINANCE_FEE_SOURCE",
            "OK",
            "fee taker verificada manualmente y vigente",
        )
        fee_evidence = {
            "status": "VERIFICADA",
            "source": "MANUAL_VERIFIED",
            "bps_per_side": float(fee_manual["fee_taker_bps_por_lado"]),
            "verified_at": fee_manual["fee_verified_at"],
            "age_seconds": float(fee_manual["age_seconds"]),
            "max_age_seconds": int(fee_manual["max_age_seconds"]),
        }
    elif fee_manual["status"] == "VENCIDA":
        add(
            "BINANCE_FEE_SOURCE",
            "BLOCKER",
            "la fee taker manual esta vencida; PAPER falla cerrado hasta revalidarla",
        )
        fee_evidence = {
            "status": "VENCIDA",
            "source": "MANUAL_VERIFIED",
            "bps_per_side": float(fee_manual["fee_taker_bps_por_lado"]),
            "verified_at": fee_manual["fee_verified_at"],
            "age_seconds": float(fee_manual["age_seconds"]),
            "max_age_seconds": int(fee_manual["max_age_seconds"]),
        }
    elif tiene_credenciales_binance:
        add(
            "BINANCE_FEE_SOURCE",
            "WARN",
            "hay credenciales Binance para leer la fee, pero readiness no hace red y no la declara verificada",
        )
        fee_evidence = {
            "status": "CUENTA_DISPONIBLE_SIN_VERIFICAR",
            "source": "BINANCE_ACCOUNT",
            "bps_per_side": None,
            "verified_at": None,
            "age_seconds": None,
            "max_age_seconds": int(fee_manual["max_age_seconds"]),
        }
    else:
        detalle = (
            "fee taker manual invalida; PAPER falla cerrado"
            if fee_manual["status"] == "INVALIDA"
            else "no hay fee taker verificable; PAPER falla cerrado"
        )
        add("BINANCE_FEE_SOURCE", "BLOCKER", detalle)
        fee_evidence = {
            "status": fee_manual["status"],
            "source": None,
            "bps_per_side": None,
            "verified_at": None,
            "age_seconds": None,
            "max_age_seconds": int(fee_manual["max_age_seconds"]),
        }

    cors = tuple(getattr(config, "CORS_ORIGINS", ()) or ())
    if cors and "*" not in cors:
        add("CORS", "OK", f"origenes explicitos={len(cors)}")
    else:
        add("CORS", "BLOCKER", "CORS no tiene una lista explicita segura")

    if profitability_gate_enabled:
        add(
            "PROFITABILITY_GATE_05E",
            "BLOCKER",
            "05E esta habilitado aunque todavia no fue promovido por evidencia OOS",
        )
    else:
        add("PROFITABILITY_GATE_05E", "OK", "05E permanece apagado")

    blockers = [c for c in checks if c.nivel == "BLOCKER"]
    warnings = [c for c in checks if c.nivel == "WARN"]
    return {
        "release": "PAPER_V1",
        "ready": not blockers,
        "status": "READY" if not blockers else "NOT_READY",
        "blockers": len(blockers),
        "warnings": len(warnings),
        "fee_evidence": fee_evidence,
        "checks": [c.__dict__ for c in checks],
    }


def resumen_publico(resultado):
    """Vista segura para /health: no expone secretos ni valores de credenciales."""
    fee = resultado.get("fee_evidence") or {}
    return {
        "release": resultado["release"],
        "ready": bool(resultado["ready"]),
        "status": resultado["status"],
        "blockers": int(resultado["blockers"]),
        "warnings": int(resultado["warnings"]),
        "fee": {
            "status": fee.get("status", "NO_DISPONIBLE"),
            "source": fee.get("source"),
            "bps_per_side": fee.get("bps_per_side"),
            "verified_at": fee.get("verified_at"),
            "age_seconds": fee.get("age_seconds"),
            "max_age_seconds": fee.get("max_age_seconds"),
        },
    }
