"""Auditoría de cobertura y calidad para métricas USD-M BOT 2.0-04B-v20."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Mapping, Sequence, Tuple

from backend.economia.historico_posicionamiento_v20 import (
    ListadoMetricasV20,
    ResumenArchivoMetricasV20,
)
from backend.economia.protocolo_posicionamiento_v20 import (
    CAMPOS_CORE_OI_V20,
    CAMPOS_RATIOS_V20,
    DESDE_V20,
    DIAS_ESPERADOS_V20,
    FRACCION_CADENCIA_5M_MIN_V20,
    FRACCION_COBERTURA_SIMBOLO_MIN_V20,
    FRACCION_CORE_POSITIVO_MIN_V20,
    FRACCION_CORE_VALIDO_MIN_V20,
    FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V20,
    FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V20,
    FRACCION_MUESTRAS_PARSEADAS_MIN_V20,
    FRACCION_RATIO_USABLE_MIN_V20,
    HASTA_EXCLUSIVO_V20,
    MESES_ESPERADOS_V20,
    MIN_SIMBOLOS_COBERTURA_APTA_V20,
    MIN_SIMBOLOS_POR_DIA_V20,
    UNIVERSO_POSICIONAMIENTO_V20,
)


@dataclass(frozen=True)
class CoberturaSimboloV20:
    symbol: str
    listado_completo: bool
    n_archivos: int
    n_dias_unicos: int
    dias_esperados: int
    fraccion_cobertura: Decimal
    fechas_duplicadas: int
    archivos_tamano_cero: int
    meses_con_archivo: int
    apto: bool


@dataclass(frozen=True)
class CoberturaAnioV20:
    year: int
    dias: int
    dias_cross_section_completa: int
    fraccion_cross_section_completa: Decimal
    apto: bool


@dataclass(frozen=True)
class CalidadCampoV20:
    nombre: str
    total: int
    validos: int
    positivos: int
    fraccion_valida: Decimal
    fraccion_positiva: Decimal
    usable: bool


@dataclass(frozen=True)
class AuditoriaPosicionamientoV20:
    simbolos: Tuple[CoberturaSimboloV20, ...]
    anios: Tuple[CoberturaAnioV20, ...]
    n_simbolos_aptos: int
    dias_cross_section_completa: int
    fraccion_cross_section_completa: Decimal
    min_simbolos_en_dia: int
    max_simbolos_en_dia: int
    n_muestras_objetivo: int
    n_muestras_parseadas: int
    fraccion_muestras_parseadas: Decimal
    n_filas_muestra: int
    duplicados_muestra: int
    no_ascendentes_muestra: int
    n_deltas_muestra: int
    n_deltas_5m_muestra: int
    fraccion_cadencia_5m: Decimal
    campos: Tuple[CalidadCampoV20, ...]
    campos_ratios_usables: Tuple[str, ...]
    core_oi_apto: bool
    dataset_apto: bool
    motivos_rechazo: Tuple[str, ...]


def _frac(num: int, den: int) -> Decimal:
    return Decimal(num) / Decimal(den) if den else Decimal("0")


def _dias_periodo():
    d = DESDE_V20
    while d < HASTA_EXCLUSIVO_V20:
        yield d.date(), d.year
        d += timedelta(days=1)


def auditar_posicionamiento_v20(
    listados: Mapping[str, ListadoMetricasV20],
    muestras: Sequence[ResumenArchivoMetricasV20],
    *,
    rechazar_no_ascendentes: bool = True,
) -> AuditoriaPosicionamientoV20:
    """Audita cobertura/calidad; v20 estricto rechaza orden físico no ascendente.

    ``rechazar_no_ascendentes=False`` existe para v20.1, donde el orden físico
    no es semántico y la serie se considera canónica por ``create_time``. Esto
    no relaja duplicados, fechas fuera del ZIP, cobertura, cadencia ni calidad.
    """
    if not isinstance(rechazar_no_ascendentes, bool):
        raise ValueError("rechazar_no_ascendentes debe ser bool")

    coberturas = []
    fechas_por_symbol = {}
    for symbol in UNIVERSO_POSICIONAMIENTO_V20:
        listado = listados.get(symbol)
        archivos = tuple(listado.archivos) if listado is not None and listado.completa else ()
        contador_fechas = Counter(a.fecha for a in archivos)
        fechas = set(contador_fechas)
        fechas_por_symbol[symbol] = fechas
        duplicadas = sum(max(0, n - 1) for n in contador_fechas.values())
        meses = {(f.year, f.month) for f in fechas}
        frac = _frac(len(fechas), DIAS_ESPERADOS_V20)
        ceros = sum(a.size == 0 for a in archivos)
        listado_ok = bool(listado is not None and listado.completa)
        apto = (
            listado_ok
            and frac >= FRACCION_COBERTURA_SIMBOLO_MIN_V20
            and duplicadas == 0
            and ceros == 0
        )
        coberturas.append(CoberturaSimboloV20(
            symbol=symbol,
            listado_completo=listado_ok,
            n_archivos=len(archivos),
            n_dias_unicos=len(fechas),
            dias_esperados=DIAS_ESPERADOS_V20,
            fraccion_cobertura=frac,
            fechas_duplicadas=duplicadas,
            archivos_tamano_cero=ceros,
            meses_con_archivo=len(meses),
            apto=apto,
        ))

    counts = []
    anio_total = Counter()
    anio_completo = Counter()
    total_completo = 0
    for fecha, year in _dias_periodo():
        n = sum(fecha in fechas_por_symbol[s] for s in UNIVERSO_POSICIONAMIENTO_V20)
        counts.append(n)
        anio_total[year] += 1
        if n >= MIN_SIMBOLOS_POR_DIA_V20:
            total_completo += 1
            anio_completo[year] += 1

    anios = tuple(
        CoberturaAnioV20(
            year=year,
            dias=anio_total[year],
            dias_cross_section_completa=anio_completo[year],
            fraccion_cross_section_completa=_frac(anio_completo[year], anio_total[year]),
            apto=(
                _frac(anio_completo[year], anio_total[year])
                >= FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V20
            ),
        )
        for year in sorted(anio_total)
    )
    frac_cross = _frac(total_completo, DIAS_ESPERADOS_V20)

    completas = tuple(m for m in muestras if m.completa)
    objetivo = len(UNIVERSO_POSICIONAMIENTO_V20) * MESES_ESPERADOS_V20
    frac_muestras = _frac(len(completas), objetivo)
    n_filas = sum(m.n_filas for m in completas)
    duplicados = sum(m.duplicados for m in completas)
    no_asc = sum(m.no_ascendentes for m in completas)
    n_deltas = sum(m.n_deltas for m in completas)
    n_5m = sum(m.n_deltas_5m for m in completas)
    frac_5m = _frac(n_5m, n_deltas)

    acumulado = {
        nombre: {"total": 0, "validos": 0, "positivos": 0}
        for nombre in CAMPOS_CORE_OI_V20 + CAMPOS_RATIOS_V20
    }
    for m in completas:
        for c in m.campos:
            if c.nombre not in acumulado:
                continue
            acumulado[c.nombre]["total"] += c.total
            acumulado[c.nombre]["validos"] += c.validos
            acumulado[c.nombre]["positivos"] += c.positivos

    campos = []
    for nombre in CAMPOS_CORE_OI_V20 + CAMPOS_RATIOS_V20:
        d = acumulado[nombre]
        fv = _frac(d["validos"], d["total"])
        fp = _frac(d["positivos"], d["total"])
        if nombre in CAMPOS_CORE_OI_V20:
            usable = fv >= FRACCION_CORE_VALIDO_MIN_V20 and fp >= FRACCION_CORE_POSITIVO_MIN_V20
        else:
            usable = fv >= FRACCION_RATIO_USABLE_MIN_V20
        campos.append(CalidadCampoV20(
            nombre=nombre,
            total=d["total"],
            validos=d["validos"],
            positivos=d["positivos"],
            fraccion_valida=fv,
            fraccion_positiva=fp,
            usable=usable,
        ))
    campos = tuple(campos)
    core_apto = all(c.usable for c in campos if c.nombre in CAMPOS_CORE_OI_V20)
    ratios_usables = tuple(c.nombre for c in campos if c.nombre in CAMPOS_RATIOS_V20 and c.usable)

    motivos = []
    n_simbolos_aptos = sum(c.apto for c in coberturas)
    if n_simbolos_aptos < MIN_SIMBOLOS_COBERTURA_APTA_V20:
        motivos.append("SIMBOLOS_ARCHIVO_APTOS_INSUFICIENTES")
    if frac_cross < FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V20:
        motivos.append("COBERTURA_CROSS_SECTION_GLOBAL_INSUFICIENTE")
    if any(not a.apto for a in anios):
        motivos.append("COBERTURA_CROSS_SECTION_ANUAL_INSUFICIENTE")
    if frac_muestras < FRACCION_MUESTRAS_PARSEADAS_MIN_V20:
        motivos.append("MUESTRAS_PARSEADAS_INSUFICIENTES")
    if duplicados:
        motivos.append("TIMESTAMPS_DUPLICADOS_EN_MUESTRA")
    if no_asc and rechazar_no_ascendentes:
        motivos.append("TIMESTAMPS_NO_ASCENDENTES_EN_MUESTRA")
    if frac_5m < FRACCION_CADENCIA_5M_MIN_V20:
        motivos.append("CADENCIA_5M_INSUFICIENTE")
    if not core_apto:
        motivos.append("CORE_OPEN_INTEREST_NO_APTO")

    return AuditoriaPosicionamientoV20(
        simbolos=tuple(coberturas),
        anios=anios,
        n_simbolos_aptos=n_simbolos_aptos,
        dias_cross_section_completa=total_completo,
        fraccion_cross_section_completa=frac_cross,
        min_simbolos_en_dia=min(counts, default=0),
        max_simbolos_en_dia=max(counts, default=0),
        n_muestras_objetivo=objetivo,
        n_muestras_parseadas=len(completas),
        fraccion_muestras_parseadas=frac_muestras,
        n_filas_muestra=n_filas,
        duplicados_muestra=duplicados,
        no_ascendentes_muestra=no_asc,
        n_deltas_muestra=n_deltas,
        n_deltas_5m_muestra=n_5m,
        fraccion_cadencia_5m=frac_5m,
        campos=campos,
        campos_ratios_usables=ratios_usables,
        core_oi_apto=core_apto,
        dataset_apto=not motivos,
        motivos_rechazo=tuple(motivos),
    )
