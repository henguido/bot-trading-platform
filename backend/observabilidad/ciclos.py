"""Embudo de decision explicable por ciclo.

La telemetria de este modulo es audit-only: nunca decide, dimensiona, filtra ni
hace red. Acumula contadores y codigos estables que ya produjo cada etapa del
bot y persiste UNA fila al terminar el ciclo.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Optional

from backend.observabilidad.models import DecisionCycleAudit


@dataclass
class ResumenCicloDecision:
    ciclo_id: str
    usuario_id: int
    modo: str
    decision_engine: str
    contadores: Counter = field(default_factory=Counter)
    motivos: Counter = field(default_factory=Counter)

    def motivo(self, codigo: str, n: int = 1) -> None:
        try:
            if codigo and int(n) > 0:
                self.motivos[str(codigo)] += int(n)
        except Exception:
            pass

    def anotar_elegibilidad(self, resumen) -> None:
        try:
            self.contadores["universo"] = int(getattr(resumen, "universo", 0) or 0)
            self.contadores["elegibles_compra"] = int(
                getattr(resumen, "elegibles_compra", 0) or 0)
            self.contadores["preservados_venta"] = int(
                getattr(resumen, "preservados_venta", 0) or 0)
            self.contadores["descartados_elegibilidad"] = int(
                getattr(resumen, "descartados", 0) or 0)
            for codigo, cantidad in dict(getattr(resumen, "por_motivo", {}) or {}).items():
                if codigo != "ELEGIBLE":
                    self.motivo(f"ELEGIBILIDAD:{codigo}", cantidad)
        except Exception:
            self.motivo("OBSERVABILIDAD:ELEGIBILIDAD_INCOMPLETA")

    def anotar_scanner(self, resumen) -> None:
        try:
            self.contadores["scanner_entrada"] = int(getattr(resumen, "entrada", 0) or 0)
            self.contadores["scanner_puntuados"] = int(getattr(resumen, "puntuados", 0) or 0)
            self.contadores["scanner_seleccionados"] = int(
                getattr(resumen, "seleccionados", 0) or 0)
            self.contadores["scanner_preservados"] = int(
                getattr(resumen, "preservados", 0) or 0)
            self.contadores["scanner_descartados"] = int(
                getattr(resumen, "descartados", 0) or 0)
            for codigo, cantidad in dict(getattr(resumen, "por_motivo", {}) or {}).items():
                if codigo not in ("CANDIDATO", "POSICION_ABIERTA"):
                    self.motivo(f"SCANNER:{codigo}", cantidad)
        except Exception:
            self.motivo("OBSERVABILIDAD:SCANNER_INCOMPLETO")

    def anotar_rentabilidad_pre(self, *, antes: int, despues: int,
                                aplicado: bool, motivo: Optional[str] = None) -> None:
        self.contadores["rentabilidad_pre_entrada"] = max(0, int(antes or 0))
        self.contadores["rentabilidad_pre_salida"] = max(0, int(despues or 0))
        bloqueados = max(0, int(antes or 0) - int(despues or 0)) if aplicado else 0
        self.contadores["rentabilidad_pre_bloqueados"] = bloqueados
        self.contadores["rentabilidad_gate_aplicado"] = 1 if aplicado else 0
        if bloqueados:
            self.motivo("RENTABILIDAD:PRE_LLM_BLOQUEO", bloqueados)
        if not aplicado and motivo:
            self.motivo(f"RENTABILIDAD:{motivo}")

    def anotar_decision(self, decision: str) -> None:
        d = str(decision or "DESCONOCIDA").upper()
        self.contadores["motor_resultados"] += 1
        if d == "COMPRAR":
            self.contadores["motor_comprar"] += 1
        elif d == "VENDER":
            self.contadores["motor_vender"] += 1
        elif d == "ESPERAR":
            self.contadores["motor_esperar"] += 1
        else:
            self.contadores["motor_otras"] += 1
            self.motivo(f"MOTOR:DECISION_{d}")

    def anotar_rentabilidad_post_bloqueada(self, motivo: str) -> None:
        self.contadores["rentabilidad_post_bloqueados"] += 1
        self.motivo(f"RENTABILIDAD:{motivo or 'POST_LLM_BLOQUEO'}")

    def anotar_riesgo(self, veredicto) -> None:
        if bool(getattr(veredicto, "aprobado", False)):
            self.contadores["riesgo_aprobadas"] += 1
            return
        self.contadores["riesgo_rechazadas"] += 1
        codigo = getattr(veredicto, "limite_violado", None) or getattr(
            veredicto, "motivo", None) or "RECHAZO"
        self.motivo(f"RIESGO:{codigo}")

    def anotar_ejecucion(self, *, success: bool, motivo: Optional[str] = None) -> None:
        if success:
            self.contadores["ejecuciones_ok"] += 1
        else:
            self.contadores["ejecuciones_fallidas"] += 1
            self.motivo(f"EJECUCION:{motivo or 'FALLO'}")

    def anotar_omision(self, codigo: str) -> None:
        self.contadores["omisiones"] += 1
        self.motivo(f"OMISION:{codigo}")

    def _motivo_principal(self) -> str:
        c = self.contadores
        if c["ejecuciones_ok"] > 0:
            return "OPERACION_EJECUTADA"
        if c["ejecuciones_fallidas"] > 0:
            return "EJECUCION_FALLIDA"
        if c["riesgo_rechazadas"] > 0:
            return "RIESGO_BLOQUEO"
        if c["rentabilidad_post_bloqueados"] > 0 or c["rentabilidad_pre_bloqueados"] > 0:
            return "RENTABILIDAD_BLOQUEO"
        if c["motor_comprar"] + c["motor_vender"] > 0:
            return "PROPUESTA_SIN_EJECUCION"
        if c["motor_esperar"] > 0:
            return "MOTOR_ESPERAR"
        if c["motor_resultados"] == 0 and (
            c["scanner_seleccionados"] + c["scanner_preservados"] > 0
        ):
            return "MOTOR_SIN_RESULTADOS"
        if c["scanner_seleccionados"] + c["scanner_preservados"] == 0:
            return "SIN_CANDIDATOS_DESPUES_SCANNER"
        return "SIN_EJECUCION"

    def como_dict(self) -> dict:
        return {
            "ciclo_id": self.ciclo_id,
            "usuario_id": self.usuario_id,
            "modo": self.modo,
            "decision_engine": self.decision_engine,
            "motivo_principal": self._motivo_principal(),
            "hubo_ejecucion": self.contadores["ejecuciones_ok"] > 0,
            "contadores": dict(sorted(self.contadores.items())),
            "motivos": dict(sorted(self.motivos.items(), key=lambda kv: (-kv[1], kv[0]))),
        }


def persistir_resumen_ciclo(db, resumen: ResumenCicloDecision) -> DecisionCycleAudit:
    payload = resumen.como_dict()
    existente = (
        db.query(DecisionCycleAudit)
        .filter(DecisionCycleAudit.ciclo_id == resumen.ciclo_id)
        .first()
    )
    if existente is not None:
        return existente

    fila = DecisionCycleAudit(
        usuario_id=resumen.usuario_id,
        ciclo_id=resumen.ciclo_id,
        timestamp=datetime.utcnow(),
        modo=resumen.modo,
        decision_engine=resumen.decision_engine,
        resumen_json=json.dumps(payload, sort_keys=True, ensure_ascii=False),
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


def ultimos_resumenes(db, *, usuario_id: int, limite: int = 12) -> list[dict]:
    limite = max(1, min(int(limite), 100))
    filas = (
        db.query(DecisionCycleAudit)
        .filter(DecisionCycleAudit.usuario_id == usuario_id)
        .order_by(DecisionCycleAudit.timestamp.desc(), DecisionCycleAudit.id.desc())
        .limit(limite)
        .all()
    )
    salida = []
    for fila in filas:
        try:
            payload = json.loads(fila.resumen_json)
        except (TypeError, ValueError):
            payload = {"motivo_principal": "RESUMEN_ILEGIBLE", "contadores": {}, "motivos": {}}
        payload["timestamp"] = fila.timestamp.isoformat() if fila.timestamp else None
        salida.append(payload)
    return salida
