"""Selector probabilistico empirico para BOT 2.0-04B-v8.

Reutiliza el estimador cuantílico de 04B para OOD, discretizacion, vecindad y
soporte. Sobre EXACTAMENTE las mismas muestras que sustentan el retorno medio,
calcula P(retorno bruto 24h > hurdle). No decide trading real.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence, Tuple

from backend.economia.edge_celdas import (
    DISPONIBLE,
    ModeloEdgeCeldas,
    _claves_en_radio,
    ajustar_modelo_celdas,
    estimar_edge_celdas,
)
from backend.economia.edge_selector_v8 import (
    EstadoSelectorV8,
    ObservacionSelectorV8,
    vector_selector_v8,
)
from backend.economia.protocolo_edge_v8 import (
    HORIZONTE_HORAS_V8,
    HURDLE_ECONOMICO_BPS_V8,
    MIN_SYMBOLS_CELDA_V8,
    MIN_TIMESTAMPS_CELDA_V8,
    NOMBRES_FEATURES_V8,
    PROBABILIDAD_SUPERAR_HURDLE_MIN_V8,
)

_BPS = Decimal("10000")


@dataclass(frozen=True)
class EstimacionSelectorV8:
    estado: str
    motivo: Optional[str]
    n_muestras: int
    n_symbols_unicos: int
    n_timestamps_unicos: int
    radio_usado: Optional[int]
    retorno_bruto_esperado_bps: Optional[Decimal]
    prob_superar_hurdle: Optional[Decimal]
    candidata: bool

    @property
    def disponible(self) -> bool:
        return self.estado == DISPONIBLE


def ajustar_selector_v8(
    observaciones: Sequence[ObservacionSelectorV8],
    *,
    rank_bins: int,
    regimen_bins: int,
    dispersion_bins: int,
    min_muestras: int,
    max_radio: int,
) -> ModeloEdgeCeldas:
    bins = (rank_bins, rank_bins, rank_bins, regimen_bins, dispersion_bins)
    return ajustar_modelo_celdas(
        observaciones,
        horizonte_horas=HORIZONTE_HORAS_V8,
        n_bins=rank_bins,
        min_muestras=min_muestras,
        min_symbols=MIN_SYMBOLS_CELDA_V8,
        min_timestamps=MIN_TIMESTAMPS_CELDA_V8,
        max_radio=max_radio,
        nombres_features=NOMBRES_FEATURES_V8,
        bins_por_feature=bins,
        vectorizador=vector_selector_v8,
    )


def _muestras_del_radio(
    modelo: ModeloEdgeCeldas,
    clave: Tuple[int, ...],
    radio: int,
) -> Tuple[ObservacionSelectorV8, ...]:
    muestras = []
    for vecina in _claves_en_radio(clave, radio, modelo.discretizaciones):
        obs = modelo.celdas.get(vecina)
        if obs:
            muestras.extend(obs)
    return tuple(sorted(
        muestras,
        key=lambda o: (o.estado.timestamp_ms, o.estado.symbol),
    ))


def estimar_selector_v8(
    modelo: ModeloEdgeCeldas,
    estado_actual: EstadoSelectorV8,
    *,
    hurdle_bps=HURDLE_ECONOMICO_BPS_V8,
    prob_min=PROBABILIDAD_SUPERAR_HURDLE_MIN_V8,
) -> EstimacionSelectorV8:
    hurdle = Decimal(str(hurdle_bps))
    prob_umbral = Decimal(str(prob_min))
    if hurdle < 0:
        raise ValueError("hurdle no puede ser negativo")
    if prob_umbral < 0 or prob_umbral > 1:
        raise ValueError("prob_min debe estar en [0,1]")

    base = estimar_edge_celdas(modelo, estado_actual)
    if not base.disponible:
        return EstimacionSelectorV8(
            estado=base.estado,
            motivo=base.motivo,
            n_muestras=base.n_muestras,
            n_symbols_unicos=base.n_symbols_unicos,
            n_timestamps_unicos=base.n_timestamps_unicos,
            radio_usado=base.radio_usado,
            retorno_bruto_esperado_bps=None,
            prob_superar_hurdle=None,
            candidata=False,
        )
    if base.clave is None or base.radio_usado is None or base.retorno_esperado is None:
        raise RuntimeError("estimacion base disponible incompleta")

    muestras = _muestras_del_radio(modelo, base.clave, base.radio_usado)
    if len(muestras) != base.n_muestras:
        raise RuntimeError("soporte probabilistico difiere del soporte de edge")

    retornos_bps = tuple(
        o.etiqueta(HORIZONTE_HORAS_V8).retorno_cierre * _BPS
        for o in muestras
    )
    prob = (
        Decimal(sum(r > hurdle for r in retornos_bps)) / Decimal(len(retornos_bps))
        if retornos_bps else Decimal("0")
    )
    retorno_bps = base.retorno_esperado * _BPS
    candidata = retorno_bps > hurdle and prob >= prob_umbral
    return EstimacionSelectorV8(
        estado=base.estado,
        motivo=None,
        n_muestras=base.n_muestras,
        n_symbols_unicos=base.n_symbols_unicos,
        n_timestamps_unicos=base.n_timestamps_unicos,
        radio_usado=base.radio_usado,
        retorno_bruto_esperado_bps=retorno_bps,
        prob_superar_hurdle=prob,
        candidata=candidata,
    )
