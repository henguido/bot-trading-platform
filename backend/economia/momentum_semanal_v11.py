"""Observaciones semanales MOM/RMOM para BOT 2.0-04B-v11.

MOMk = retorno acumulado de las k semanas terminadas en t.
RMOMk = media(retornos diarios) / desviación estándar muestral diaria durante
        esas k semanas, con rf=0. No se anualiza: v11 solo usa el orden
        cross-sectional y una constante positiva no alteraría ese ranking.

Cada observación se forma al cierre del domingo (límite lunes 00:00 UTC). Las
features usan únicamente datos <= t. La etiqueta usa exclusivamente la semana
futura t+1..t+7d. El módulo no hace red ni decide operaciones.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping, Sequence, Tuple

from backend.economia.edge_historico import EtiquetaHorizonte, Vela
from backend.economia.protocolo_edge_v11 import (
    BARRAS_POR_DIA_V11,
    DIA_REBALANCEO_UTC_V11,
    DIAS_POR_SEMANA_V11,
    HORA_REBALANCEO_UTC_V11,
    HORIZONTE_HORAS_V11,
    INTERVALO_HORAS_V11,
    MAX_SEMANAS_FORMACION_V11,
)

HORA_MS = 60 * 60 * 1000


@dataclass(frozen=True)
class EstadoMomentumV11:
    symbol: str
    timestamp_ms: int
    close: Decimal
    mom1: Decimal
    mom2: Decimal
    mom3: Decimal
    rmom1: Decimal
    rmom2: Decimal
    rmom3: Decimal


@dataclass(frozen=True)
class ObservacionMomentumV11:
    estado: EstadoMomentumV11
    etiquetas: Tuple[EtiquetaHorizonte, ...]

    def etiqueta(self, horizonte_horas: int) -> EtiquetaHorizonte:
        for e in self.etiquetas:
            if e.horizonte_horas == horizonte_horas:
                return e
        raise KeyError(horizonte_horas)


def _media(valores: Sequence[Decimal]) -> Decimal:
    if not valores:
        raise ValueError("media sin datos")
    return sum(valores, Decimal("0")) / Decimal(len(valores))


def _std_muestral(valores: Sequence[Decimal]) -> Decimal:
    if len(valores) < 2:
        raise ValueError("desviacion requiere al menos dos datos")
    m = _media(valores)
    var = sum(((x - m) * (x - m) for x in valores), Decimal("0")) / Decimal(len(valores) - 1)
    if var < 0:
        raise RuntimeError("varianza negativa")
    return var.sqrt()


def _ordenar_y_validar(velas: Sequence[Vela]) -> Tuple[Vela, ...]:
    salida = tuple(sorted(velas, key=lambda v: v.open_time_ms))
    for anterior, actual in zip(salida, salida[1:]):
        if actual.open_time_ms == anterior.open_time_ms:
            raise ValueError(f"kline duplicado en {actual.open_time_ms}")
    return salida


def _es_cierre_semanal(v: Vela) -> bool:
    limite = v.close_time_ms + 1
    if limite % HORA_MS:
        raise ValueError(f"close_time no alineado a hora: {v.close_time_ms}")
    dt = datetime.fromtimestamp(limite / 1000, tz=timezone.utc)
    return dt.weekday() == DIA_REBALANCEO_UTC_V11 and dt.hour == HORA_REBALANCEO_UTC_V11


def _retornos_diarios(velas: Sequence[Vela], i: int, semanas: int) -> Tuple[Decimal, ...]:
    dias = semanas * DIAS_POR_SEMANA_V11
    paso = BARRAS_POR_DIA_V11
    inicio = i - dias * paso
    return tuple(
        (velas[j].close / velas[j - paso].close) - Decimal("1")
        for j in range(inicio + paso, i + 1, paso)
    )


def construir_observaciones_momentum_v11(
    series_por_symbol: Mapping[str, Sequence[Vela]],
    *,
    intervalo_horas: int = INTERVALO_HORAS_V11,
) -> Tuple[ObservacionMomentumV11, ...]:
    """Construye estados semanales completos; desconocido no se imputa a cero."""
    if intervalo_horas != INTERVALO_HORAS_V11:
        raise ValueError(f"v11 requiere intervalo_horas={INTERVALO_HORAS_V11}")

    paso_ms = intervalo_horas * HORA_MS
    barras_semana = DIAS_POR_SEMANA_V11 * BARRAS_POR_DIA_V11
    max_hist = MAX_SEMANAS_FORMACION_V11 * barras_semana
    futuro = HORIZONTE_HORAS_V11 // intervalo_horas
    salida = []

    for symbol in sorted(series_por_symbol):
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol invalido")
        velas = _ordenar_y_validar(series_por_symbol[symbol])
        n = len(velas)
        if n <= max_hist + futuro:
            continue

        rupturas = [0] * n
        for j in range(1, n):
            gap = 0 if velas[j].open_time_ms - velas[j - 1].open_time_ms == paso_ms else 1
            rupturas[j] = rupturas[j - 1] + gap

        def contiguo(a: int, b: int) -> bool:
            return 0 <= a <= b < n and rupturas[b] == rupturas[a]

        for i in range(max_hist, n - futuro):
            if not _es_cierre_semanal(velas[i]):
                continue
            if not contiguo(i - max_hist, i + futuro):
                continue

            moms = []
            rmoms = []
            valido = True
            for semanas in (1, 2, 3):
                atras = semanas * barras_semana
                mom = (velas[i].close / velas[i - atras].close) - Decimal("1")
                diarios = _retornos_diarios(velas, i, semanas)
                sigma = _std_muestral(diarios)
                if sigma <= 0:
                    valido = False
                    break
                moms.append(mom)
                rmoms.append(_media(diarios) / sigma)
            if not valido:
                continue

            entrada = velas[i].close
            j = i + futuro
            futuras = velas[i + 1:j + 1]
            max_high = max(v.high for v in futuras)
            min_low = min(v.low for v in futuras)
            etiqueta = EtiquetaHorizonte(
                horizonte_horas=HORIZONTE_HORAS_V11,
                retorno_cierre=(velas[j].close / entrada) - Decimal("1"),
                mfe=max(Decimal("0"), (max_high / entrada) - Decimal("1")),
                mae=min(Decimal("0"), (min_low / entrada) - Decimal("1")),
            )
            salida.append(ObservacionMomentumV11(
                estado=EstadoMomentumV11(
                    symbol=symbol,
                    timestamp_ms=velas[i].close_time_ms,
                    close=entrada,
                    mom1=moms[0], mom2=moms[1], mom3=moms[2],
                    rmom1=rmoms[0], rmom2=rmoms[1], rmom3=rmoms[2],
                ),
                etiquetas=(etiqueta,),
            ))

    return tuple(sorted(salida, key=lambda o: (o.estado.timestamp_ms, o.estado.symbol)))
