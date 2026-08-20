"""Diagnostico offline de rebote intrahorizonte para BOT 2.0-04B-v6.

No genera nuevas senales: recibe las senales cost-aware ya producidas por v5 y
cambia UNICAMENTE la regla de salida para responder si el MFE/MAE observado en
las siguientes 8h podria convertir una senal defensiva en un payoff long spot
viable.

La politica es conservadora: si el stop y el target fueron tocados dentro de la
ventana, se asigna STOP porque velas 4h no demuestran el orden intrabar.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence, Tuple

from backend.economia.diagnostico_edge_desarrollo import (
    FOLDS_DIAGNOSTICO_DESARROLLO_2025,
    ResultadoDiagnosticoDesarrollo,
)
from backend.economia.edge_relativo_v2 import ObservacionRelativaV2
from backend.economia.evaluacion_cost_aware import SenalCostAware
from backend.economia.protocolo_edge_v6 import (
    CONFIGS_MINIMAS_APTAS_V6,
    FOLDS_CON_SENAL_MIN_V6,
    FOLDS_NETOS_POSITIVOS_MIN_V6,
    FRACCION_RESULTADOS_POSITIVOS_MIN_V6,
    HORIZONTE_HORAS_V6,
    HURDLE_ECONOMICO_BPS_V6,
    MESES_CON_SENAL_MIN_V6,
    MESES_NETOS_POSITIVOS_MIN_V6,
    MIN_SENALES_V6,
    STOP_BRUTO_BPS_V6,
    TARGET_BRUTO_BPS_V6,
)
from backend.economia.walk_forward_edge import FoldTemporal

_BPS = Decimal("10000")
STOP = "STOP"
TARGET = "TARGET"
TIME = "TIME"


@dataclass(frozen=True)
class ResultadoSenalReboteV6:
    symbol: str
    timestamp_ms: int
    salida: str
    stop_y_target_tocados: bool
    mfe_bps: Decimal
    mae_bps: Decimal
    bruto_salida_bps: Decimal
    neto_despues_hurdle_bps: Decimal


@dataclass(frozen=True)
class ResumenReboteV6:
    n_senales: int
    n_stop: int
    n_target: int
    n_time: int
    n_ambiguas_stop_prioritario: int
    retorno_neto_despues_hurdle_medio_bps: Optional[Decimal]
    fraccion_resultados_positivos: Optional[Decimal]
    n_meses_con_senal: int
    meses_netos_positivos: int
    n_folds_con_senal: int
    folds_netos_positivos: int
    apto_diagnostico: bool
    motivos_rechazo: Tuple[str, ...]
    resultados: Tuple[ResultadoSenalReboteV6, ...]


@dataclass(frozen=True)
class ResultadoConfiguracionReboteV6:
    min_muestras: int
    max_radio: int
    resumen: ResumenReboteV6


@dataclass(frozen=True)
class ResultadoDiagnosticoReboteV6:
    resultados: Tuple[ResultadoConfiguracionReboteV6, ...]

    @property
    def n_configuraciones_aptas(self) -> int:
        return sum(r.resumen.apto_diagnostico for r in self.resultados)

    @property
    def familia_apta(self) -> bool:
        return self.n_configuraciones_aptas >= CONFIGS_MINIMAS_APTAS_V6


def _media(valores) -> Optional[Decimal]:
    v = tuple(valores)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _mes(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")


def _fold_idx(ts: int, folds: Sequence[FoldTemporal]) -> Optional[int]:
    for idx, f in enumerate(folds):
        if f.valid_desde_ms <= ts < f.valid_hasta_ms:
            return idx
    return None


def evaluar_rebote_v6(
    senales: Sequence[SenalCostAware],
    observaciones: Sequence[ObservacionRelativaV2],
    *,
    folds: Sequence[FoldTemporal] = FOLDS_DIAGNOSTICO_DESARROLLO_2025,
    horizonte_horas: int = HORIZONTE_HORAS_V6,
    stop_bruto_bps=STOP_BRUTO_BPS_V6,
    target_bruto_bps=TARGET_BRUTO_BPS_V6,
    hurdle_bps=HURDLE_ECONOMICO_BPS_V6,
) -> ResumenReboteV6:
    """Aplica bracket conservador a senales existentes; no selecciona nuevas."""
    stop = Decimal(str(stop_bruto_bps))
    target = Decimal(str(target_bruto_bps))
    hurdle = Decimal(str(hurdle_bps))
    if stop <= 0 or target <= 0 or hurdle < 0:
        raise ValueError("stop/target deben ser positivos y hurdle no negativo")

    indice = {(o.estado.timestamp_ms, o.estado.symbol): o for o in observaciones}
    resultados = []
    vistos_ts = set()
    for s in sorted(senales, key=lambda x: (x.timestamp_ms, x.symbol)):
        if s.timestamp_ms in vistos_ts:
            raise ValueError("v6 espera maximo una senal por timestamp")
        vistos_ts.add(s.timestamp_ms)
        o = indice.get((s.timestamp_ms, s.symbol))
        if o is None:
            raise ValueError(f"senal sin observacion: {s.symbol}@{s.timestamp_ms}")
        try:
            etiqueta = o.etiqueta(horizonte_horas)
        except KeyError:
            raise ValueError("senal sin etiqueta del horizonte v6") from None

        mfe = etiqueta.mfe * _BPS
        mae = etiqueta.mae * _BPS
        toca_stop = mae <= -stop
        toca_target = mfe >= target
        ambigua = toca_stop and toca_target
        if toca_stop:
            salida = STOP
            bruto = -stop
        elif toca_target:
            salida = TARGET
            bruto = target
        else:
            salida = TIME
            bruto = etiqueta.retorno_cierre * _BPS

        resultados.append(ResultadoSenalReboteV6(
            symbol=s.symbol,
            timestamp_ms=s.timestamp_ms,
            salida=salida,
            stop_y_target_tocados=ambigua,
            mfe_bps=mfe,
            mae_bps=mae,
            bruto_salida_bps=bruto,
            neto_despues_hurdle_bps=bruto - hurdle,
        ))

    rs = tuple(resultados)
    mensual = defaultdict(list)
    por_fold = defaultdict(list)
    for r in rs:
        mensual[_mes(r.timestamp_ms)].append(r.neto_despues_hurdle_bps)
        idx = _fold_idx(r.timestamp_ms, folds)
        if idx is not None:
            por_fold[idx].append(r.neto_despues_hurdle_bps)

    medias_mes = tuple(_media(v) for _, v in sorted(mensual.items()))
    medias_mes = tuple(v for v in medias_mes if v is not None)
    medias_fold = tuple(_media(v) for _, v in sorted(por_fold.items()))
    medias_fold = tuple(v for v in medias_fold if v is not None)
    media_total = _media(r.neto_despues_hurdle_bps for r in rs)
    fraccion_pos = (
        Decimal(sum(r.neto_despues_hurdle_bps > 0 for r in rs)) / Decimal(len(rs))
        if rs else None
    )

    motivos = []
    if len(rs) < MIN_SENALES_V6:
        motivos.append("SENALES_INSUFICIENTES")
    if media_total is None or media_total <= 0:
        motivos.append("RETORNO_NETO_NO_POSITIVO")
    if fraccion_pos is None or fraccion_pos < FRACCION_RESULTADOS_POSITIVOS_MIN_V6:
        motivos.append("RESULTADOS_POSITIVOS_INSUFICIENTES")
    if len(medias_mes) < MESES_CON_SENAL_MIN_V6:
        motivos.append("COBERTURA_MENSUAL_INSUFICIENTE")
    if sum(v > 0 for v in medias_mes) < MESES_NETOS_POSITIVOS_MIN_V6:
        motivos.append("ESTABILIDAD_MENSUAL_INSUFICIENTE")
    if len(medias_fold) < FOLDS_CON_SENAL_MIN_V6:
        motivos.append("COBERTURA_FOLDS_INSUFICIENTE")
    if sum(v > 0 for v in medias_fold) < FOLDS_NETOS_POSITIVOS_MIN_V6:
        motivos.append("ESTABILIDAD_FOLDS_INSUFICIENTE")

    return ResumenReboteV6(
        n_senales=len(rs),
        n_stop=sum(r.salida == STOP for r in rs),
        n_target=sum(r.salida == TARGET for r in rs),
        n_time=sum(r.salida == TIME for r in rs),
        n_ambiguas_stop_prioritario=sum(r.stop_y_target_tocados for r in rs),
        retorno_neto_despues_hurdle_medio_bps=media_total,
        fraccion_resultados_positivos=fraccion_pos,
        n_meses_con_senal=len(medias_mes),
        meses_netos_positivos=sum(v > 0 for v in medias_mes),
        n_folds_con_senal=len(medias_fold),
        folds_netos_positivos=sum(v > 0 for v in medias_fold),
        apto_diagnostico=not motivos,
        motivos_rechazo=tuple(motivos),
        resultados=rs,
    )


def diagnosticar_rebote_v6(
    diagnostico_v5: ResultadoDiagnosticoDesarrollo,
    observaciones: Sequence[ObservacionRelativaV2],
) -> ResultadoDiagnosticoReboteV6:
    """Evalua las cuatro configuraciones heredadas sin optimizar parametros."""
    salida = []
    for r in diagnostico_v5.resultados:
        c = r.configuracion
        resumen = evaluar_rebote_v6(
            r.resultado_cost_aware.senales,
            observaciones,
        )
        salida.append(ResultadoConfiguracionReboteV6(
            min_muestras=c.min_muestras,
            max_radio=c.max_radio,
            resumen=resumen,
        ))
    return ResultadoDiagnosticoReboteV6(resultados=tuple(salida))
