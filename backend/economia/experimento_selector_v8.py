"""Walk-forward de desarrollo para BOT 2.0-04B-v8.

Evalua exclusivamente 2025 como DESARROLLO ya observado, con train expansivo
anterior, rejilla no solapada 24h y embargo de 24h. No abre 2026.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence, Tuple

from backend.economia.edge_selector_v8 import ObservacionSelectorV8
from backend.economia.muestreo_edge import submuestrear_no_solapado
from backend.economia.protocolo_edge_v8 import (
    DISPERSION_BINS_CANDIDATOS_V8,
    FASE_REJILLA_HORAS_V8,
    FOLDS_CON_SENAL_MIN_V8,
    FOLDS_NETOS_POSITIVOS_MIN_V8,
    FRACCION_SENALES_NETO_POSITIVO_MIN_V8,
    HORIZONTE_HORAS_V8,
    HURDLE_ECONOMICO_BPS_V8,
    MAX_RADIOS_CANDIDATOS_V8,
    MESES_CON_SENAL_MIN_V8,
    MESES_NETOS_POSITIVOS_MIN_V8,
    MIN_DIMENSIONES_VECINAS_ROBUSTAS_V8,
    MIN_MUESTRAS_CANDIDATAS_V8,
    MIN_SENALES_DESARROLLO_2025_V8,
    MIN_SYMBOLS_POR_TIMESTAMP_V8,
    RANK_BINS_CANDIDATOS_V8,
    REGIMEN_BINS_CANDIDATOS_V8,
)
from backend.economia.selector_probabilistico_v8 import (
    ajustar_selector_v8,
    estimar_selector_v8,
)

_BPS = Decimal("10000")
_HORA_MS = 60 * 60 * 1000


def _utc_ms(fecha: str) -> int:
    return int(datetime.fromisoformat(fecha).replace(tzinfo=timezone.utc).timestamp() * 1000)


INICIO_2025_MS = _utc_ms("2025-01-01T00:00:00")
FIN_2025_MS = _utc_ms("2026-01-01T00:00:00")
FOLDS_DESARROLLO_2025_V8 = (
    (INICIO_2025_MS, _utc_ms("2025-04-01T00:00:00")),
    (_utc_ms("2025-04-01T00:00:00"), _utc_ms("2025-07-01T00:00:00")),
    (_utc_ms("2025-07-01T00:00:00"), _utc_ms("2025-10-01T00:00:00")),
    (_utc_ms("2025-10-01T00:00:00"), FIN_2025_MS),
)


@dataclass(frozen=True)
class ConfiguracionSelectorV8:
    rank_bins: int
    regimen_bins: int
    dispersion_bins: int
    min_muestras: int
    max_radio: int


@dataclass(frozen=True)
class SenalSelectorV8:
    symbol: str
    timestamp_ms: int
    fold_idx: int
    retorno_predicho_bps: Decimal
    prob_superar_hurdle: Decimal
    retorno_bruto_real_bps: Decimal
    retorno_neto_real_bps: Decimal


@dataclass(frozen=True)
class ResultadoConfiguracionSelectorV8:
    configuracion: ConfiguracionSelectorV8
    n_timestamps_evaluables: int
    n_senales: int
    retorno_neto_medio_bps: Optional[Decimal]
    fraccion_senales_neto_positivo: Optional[Decimal]
    n_meses_con_senal: int
    meses_netos_positivos: int
    n_folds_con_senal: int
    folds_netos_positivos: int
    supera_criterios: bool
    motivos_rechazo: Tuple[str, ...]
    robusta_grid: bool = False
    dimensiones_vecinas_robustas: Tuple[str, ...] = ()
    senales: Tuple[SenalSelectorV8, ...] = ()


@dataclass(frozen=True)
class ResultadoExperimentoSelectorV8:
    n_observaciones_desarrollo: int
    n_configuraciones: int
    resultados: Tuple[ResultadoConfiguracionSelectorV8, ...]

    @property
    def n_superan_criterios(self) -> int:
        return sum(r.supera_criterios for r in self.resultados)

    @property
    def n_robustas(self) -> int:
        return sum(r.robusta_grid for r in self.resultados)

    @property
    def configuracion_preferida_no_performance(self) -> Optional[ConfiguracionSelectorV8]:
        return seleccionar_configuracion_no_performance_v8(self.resultados)


def configuraciones_v8_predeclaradas() -> Tuple[ConfiguracionSelectorV8, ...]:
    return tuple(
        ConfiguracionSelectorV8(rb, gb, db, mm, mr)
        for rb in RANK_BINS_CANDIDATOS_V8
        for gb in REGIMEN_BINS_CANDIDATOS_V8
        for db in DISPERSION_BINS_CANDIDATOS_V8
        for mm in MIN_MUESTRAS_CANDIDATAS_V8
        for mr in MAX_RADIOS_CANDIDATOS_V8
    )


def _media(valores) -> Optional[Decimal]:
    v = tuple(valores)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _mes(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")


def _evaluar_config(
    observaciones: Sequence[ObservacionSelectorV8],
    c: ConfiguracionSelectorV8,
) -> ResultadoConfiguracionSelectorV8:
    datos = submuestrear_no_solapado(
        observaciones,
        horizonte_horas=HORIZONTE_HORAS_V8,
        fase_horas=FASE_REJILLA_HORAS_V8,
    )
    senales = []
    timestamps_evaluables = 0

    for fold_idx, (desde, hasta) in enumerate(FOLDS_DESARROLLO_2025_V8):
        embargo_ms = HORIZONTE_HORAS_V8 * _HORA_MS
        train = tuple(o for o in datos if o.estado.timestamp_ms < desde - embargo_ms)
        valid = tuple(o for o in datos if desde <= o.estado.timestamp_ms < hasta)
        if not train or not valid:
            continue
        modelo = ajustar_selector_v8(
            train,
            rank_bins=c.rank_bins,
            regimen_bins=c.regimen_bins,
            dispersion_bins=c.dispersion_bins,
            min_muestras=c.min_muestras,
            max_radio=c.max_radio,
        )

        por_ts = defaultdict(list)
        for o in valid:
            e = estimar_selector_v8(modelo, o.estado)
            if e.disponible:
                por_ts[o.estado.timestamp_ms].append((o, e))

        for ts, grupo in sorted(por_ts.items()):
            if len(grupo) < MIN_SYMBOLS_POR_TIMESTAMP_V8:
                continue
            timestamps_evaluables += 1
            candidatas = tuple(
                (o, e) for o, e in grupo
                if e.candidata
                and e.retorno_bruto_esperado_bps is not None
                and e.prob_superar_hurdle is not None
            )
            if not candidatas:
                continue
            o, e = min(
                candidatas,
                key=lambda par: (
                    -par[1].retorno_bruto_esperado_bps,
                    -par[1].prob_superar_hurdle,
                    par[0].estado.symbol,
                ),
            )
            real = o.etiqueta(HORIZONTE_HORAS_V8).retorno_cierre * _BPS
            senales.append(SenalSelectorV8(
                symbol=o.estado.symbol,
                timestamp_ms=ts,
                fold_idx=fold_idx,
                retorno_predicho_bps=e.retorno_bruto_esperado_bps,
                prob_superar_hurdle=e.prob_superar_hurdle,
                retorno_bruto_real_bps=real,
                retorno_neto_real_bps=real - HURDLE_ECONOMICO_BPS_V8,
            ))

    rs = tuple(sorted(senales, key=lambda s: (s.timestamp_ms, s.symbol)))
    media_neta = _media(s.retorno_neto_real_bps for s in rs)
    fraccion_pos = (
        Decimal(sum(s.retorno_neto_real_bps > 0 for s in rs)) / Decimal(len(rs))
        if rs else None
    )
    mensual = defaultdict(list)
    folds = defaultdict(list)
    for s in rs:
        mensual[_mes(s.timestamp_ms)].append(s.retorno_neto_real_bps)
        folds[s.fold_idx].append(s.retorno_neto_real_bps)
    medias_mes = tuple(_media(v) for _, v in sorted(mensual.items()))
    medias_mes = tuple(v for v in medias_mes if v is not None)
    medias_fold = tuple(_media(v) for _, v in sorted(folds.items()))
    medias_fold = tuple(v for v in medias_fold if v is not None)

    motivos = []
    if len(rs) < MIN_SENALES_DESARROLLO_2025_V8:
        motivos.append("SENALES_INSUFICIENTES")
    if media_neta is None or media_neta <= 0:
        motivos.append("RETORNO_NETO_NO_POSITIVO")
    if fraccion_pos is None or fraccion_pos < FRACCION_SENALES_NETO_POSITIVO_MIN_V8:
        motivos.append("HIT_RATE_INSUFICIENTE")
    if len(medias_mes) < MESES_CON_SENAL_MIN_V8:
        motivos.append("COBERTURA_MENSUAL_INSUFICIENTE")
    if sum(v > 0 for v in medias_mes) < MESES_NETOS_POSITIVOS_MIN_V8:
        motivos.append("ESTABILIDAD_MENSUAL_INSUFICIENTE")
    if len(medias_fold) < FOLDS_CON_SENAL_MIN_V8:
        motivos.append("COBERTURA_FOLDS_INSUFICIENTE")
    if sum(v > 0 for v in medias_fold) < FOLDS_NETOS_POSITIVOS_MIN_V8:
        motivos.append("ESTABILIDAD_FOLDS_INSUFICIENTE")

    return ResultadoConfiguracionSelectorV8(
        configuracion=c,
        n_timestamps_evaluables=timestamps_evaluables,
        n_senales=len(rs),
        retorno_neto_medio_bps=media_neta,
        fraccion_senales_neto_positivo=fraccion_pos,
        n_meses_con_senal=len(medias_mes),
        meses_netos_positivos=sum(v > 0 for v in medias_mes),
        n_folds_con_senal=len(medias_fold),
        folds_netos_positivos=sum(v > 0 for v in medias_fold),
        supera_criterios=not motivos,
        motivos_rechazo=tuple(motivos),
        senales=rs,
    )


def _adyacente(valores, a, b) -> bool:
    try:
        ia, ib = tuple(valores).index(a), tuple(valores).index(b)
    except ValueError:
        return False
    return abs(ia - ib) == 1


def _dimension_vecina(a: ConfiguracionSelectorV8, b: ConfiguracionSelectorV8) -> Optional[str]:
    cambios = []
    campos = (
        ("rank_bins", RANK_BINS_CANDIDATOS_V8),
        ("regimen_bins", REGIMEN_BINS_CANDIDATOS_V8),
        ("dispersion_bins", DISPERSION_BINS_CANDIDATOS_V8),
        ("min_muestras", MIN_MUESTRAS_CANDIDATAS_V8),
        ("max_radio", MAX_RADIOS_CANDIDATOS_V8),
    )
    for nombre, valores in campos:
        va, vb = getattr(a, nombre), getattr(b, nombre)
        if va != vb:
            if not _adyacente(valores, va, vb):
                return None
            cambios.append(nombre)
    return cambios[0] if len(cambios) == 1 else None


def _marcar_robustez(resultados):
    rs = tuple(resultados)
    aprobadas = tuple(r for r in rs if r.supera_criterios)
    salida = []
    for r in rs:
        dimensiones = set()
        if r.supera_criterios:
            for otra in aprobadas:
                if otra is r:
                    continue
                d = _dimension_vecina(r.configuracion, otra.configuracion)
                if d:
                    dimensiones.add(d)
        salida.append(replace(
            r,
            robusta_grid=len(dimensiones) >= MIN_DIMENSIONES_VECINAS_ROBUSTAS_V8,
            dimensiones_vecinas_robustas=tuple(sorted(dimensiones)),
        ))
    return tuple(salida)


def _indice(c: ConfiguracionSelectorV8):
    return (
        RANK_BINS_CANDIDATOS_V8.index(c.rank_bins),
        REGIMEN_BINS_CANDIDATOS_V8.index(c.regimen_bins),
        DISPERSION_BINS_CANDIDATOS_V8.index(c.dispersion_bins),
        MIN_MUESTRAS_CANDIDATAS_V8.index(c.min_muestras),
        MAX_RADIOS_CANDIDATOS_V8.index(c.max_radio),
    )


def seleccionar_configuracion_no_performance_v8(resultados) -> Optional[ConfiguracionSelectorV8]:
    robustas = tuple(r for r in resultados if r.robusta_grid)
    if not robustas:
        return None

    def score(r):
        idx = _indice(r.configuracion)
        distancia = sum(
            sum(abs(a - b) for a, b in zip(idx, _indice(o.configuracion)))
            for o in robustas
        )
        # Desempates conservadores sin usar retorno realizado.
        return (
            distancia,
            -r.configuracion.min_muestras,
            r.configuracion.max_radio,
            r.configuracion.rank_bins + r.configuracion.regimen_bins + r.configuracion.dispersion_bins,
            idx,
        )

    return min(robustas, key=score).configuracion


def evaluar_selector_v8_desarrollo(
    observaciones: Sequence[ObservacionSelectorV8],
    *,
    configuraciones: Sequence[ConfiguracionSelectorV8] | None = None,
) -> ResultadoExperimentoSelectorV8:
    datos = tuple(sorted(
        (o for o in observaciones if o.estado.timestamp_ms < FIN_2025_MS),
        key=lambda o: (o.estado.timestamp_ms, o.estado.symbol),
    ))
    configs = tuple(configuraciones_v8_predeclaradas() if configuraciones is None else configuraciones)
    resultados = tuple(_evaluar_config(datos, c) for c in configs)
    marcados = _marcar_robustez(resultados)
    return ResultadoExperimentoSelectorV8(
        n_observaciones_desarrollo=len(datos),
        n_configuraciones=len(marcados),
        resultados=marcados,
    )
