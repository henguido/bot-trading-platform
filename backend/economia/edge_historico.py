"""Dataset historico deterministico para estimar Expected Edge (BOT 2.0-04B-0).

Este modulo NO predice, NO decide y NO hace red. Convierte klines ya obtenidos
en observaciones auditables:

    features(t)  -> solo datos conocidos hasta el cierre de t
    labels(t+h)  -> retornos y excursiones FUTURAS, solo para evaluacion

La separacion es deliberada para impedir look-ahead. El scanner 03B usa ademas
spread bid/ask, que NO puede reconstruirse con klines; por tanto este modulo no
pretende reproducir su score historico exacto.

Binance Vision usa microsegundos en archivos Spot recientes mientras el REST
tradicional entrega timestamps en milisegundos. Internamente TODO se normaliza
a milisegundos antes de construir continuidad, splits o labels.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Sequence, Tuple

HORIZONTES_EXPLORATORIOS_HORAS = (4, 8, 12, 24)
VENTANA_ESTADO_HORAS = 24
_UMBRAL_MICROSEGUNDOS = 100_000_000_000_000       # 1e14
_UMBRAL_NANOSEGUNDOS = 100_000_000_000_000_000    # 1e17


def _decimal(valor, nombre: str) -> Decimal:
    if valor is None or isinstance(valor, bool):
        raise ValueError(f"{nombre} invalido")
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{nombre} no numerico") from None
    if not d.is_finite():
        raise ValueError(f"{nombre} no finito")
    return d


def _entero(valor, nombre: str) -> int:
    if valor is None or isinstance(valor, bool):
        raise ValueError(f"{nombre} invalido")
    try:
        i = int(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nombre} no entero") from None
    return i


def _timestamp_ms(valor, nombre: str) -> int:
    """Acepta ms o us de Binance y devuelve SIEMPRE milisegundos.

    Magnitudes >=1e17 se rechazan: este pipeline solo declara soporte para las
    dos unidades que Binance documenta/usa en las fuentes contempladas.
    """
    i = _entero(valor, nombre)
    if i < 0:
        raise ValueError(f"{nombre} negativo")
    if i >= _UMBRAL_NANOSEGUNDOS:
        raise ValueError(f"{nombre} unidad no soportada")
    if i >= _UMBRAL_MICROSEGUNDOS:
        return i // 1000
    return i


@dataclass(frozen=True)
class Vela:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time_ms: int
    quote_volume: Decimal
    trades: int


@dataclass(frozen=True)
class EstadoHistorico:
    """Features disponibles al cierre de una vela, sin datos futuros."""
    symbol: str
    timestamp_ms: int
    close: Decimal
    quote_volume_24h: Decimal
    trades_24h: int
    rango_24h: Decimal
    momentum_cierre_24h_pct: Decimal


@dataclass(frozen=True)
class EtiquetaHorizonte:
    """Lo ocurrido DESPUES de t; nunca debe entrar como feature."""
    horizonte_horas: int
    retorno_cierre: Decimal
    mfe: Decimal  # max favorable excursion vs close(t), siempre >= 0
    mae: Decimal  # max adverse excursion vs close(t), siempre <= 0


@dataclass(frozen=True)
class ObservacionEdge:
    estado: EstadoHistorico
    etiquetas: Tuple[EtiquetaHorizonte, ...]

    def etiqueta(self, horizonte_horas: int) -> EtiquetaHorizonte:
        for e in self.etiquetas:
            if e.horizonte_horas == horizonte_horas:
                return e
        raise KeyError(horizonte_horas)


def vela_desde_kline(fila) -> Vela:
    """Convierte una fila Binance Spot (REST o Vision) en Vela validada."""
    if not isinstance(fila, (list, tuple)) or len(fila) < 9:
        raise ValueError("kline incompleto")

    t0 = _timestamp_ms(fila[0], "open_time")
    o = _decimal(fila[1], "open")
    h = _decimal(fila[2], "high")
    l = _decimal(fila[3], "low")
    c = _decimal(fila[4], "close")
    vol = _decimal(fila[5], "volume")
    t1 = _timestamp_ms(fila[6], "close_time")
    qv = _decimal(fila[7], "quote_volume")
    trades = _entero(fila[8], "trades")

    if t1 <= t0:
        raise ValueError("timestamps de kline invalidos")
    if min(o, h, l, c) <= 0:
        raise ValueError("precios deben ser positivos")
    if h < max(o, l, c) or l > min(o, h, c):
        raise ValueError("OHLC inconsistente")
    if vol < 0 or qv < 0 or trades < 0:
        raise ValueError("volumen/trades no pueden ser negativos")

    return Vela(t0, o, h, l, c, vol, t1, qv, trades)


def velas_desde_klines(filas: Iterable) -> Tuple[Vela, ...]:
    """Parsea, ordena por open time y rechaza duplicados."""
    velas = sorted((vela_desde_kline(f) for f in filas), key=lambda v: v.open_time_ms)
    for anterior, actual in zip(velas, velas[1:]):
        if actual.open_time_ms == anterior.open_time_ms:
            raise ValueError(f"kline duplicado en {actual.open_time_ms}")
    return tuple(velas)


def _validar_parametros(intervalo_horas: int, ventana_horas: int,
                        horizontes_horas: Sequence[int]) -> Tuple[int, Tuple[int, ...]]:
    if isinstance(intervalo_horas, bool) or not isinstance(intervalo_horas, int) or intervalo_horas <= 0:
        raise ValueError("intervalo_horas debe ser entero positivo")
    if isinstance(ventana_horas, bool) or not isinstance(ventana_horas, int) or ventana_horas <= 0:
        raise ValueError("ventana_horas debe ser entero positivo")
    if ventana_horas % intervalo_horas:
        raise ValueError("ventana_horas debe ser multiplo del intervalo")

    hs = tuple(horizontes_horas)
    if (not hs or any(isinstance(h, bool) or not isinstance(h, int) for h in hs)
            or len(set(hs)) != len(hs)
            or any(h <= 0 or h % intervalo_horas for h in hs)):
        raise ValueError("horizontes deben ser enteros positivos, unicos y multiplos del intervalo")
    return ventana_horas // intervalo_horas, tuple(sorted(hs))


def construir_observaciones(
    symbol: str,
    velas: Sequence[Vela],
    *,
    intervalo_horas: int = 1,
    ventana_horas: int = VENTANA_ESTADO_HORAS,
    horizontes_horas: Sequence[int] = HORIZONTES_EXPLORATORIOS_HORAS,
) -> Tuple[ObservacionEdge, ...]:
    """Construye observaciones sin look-ahead y omite cualquier ventana con gaps.

    El estado usa `ventana_horas / intervalo_horas` velas incluyendo t y el
    momentum compara close(t) con close(t-ventana_horas). Las etiquetas usan
    exclusivamente velas futuras t+1..t+h.

    Un hueco temporal no se rellena ni se interpreta como una vela plana: la
    observacion completa se omite. Desconocido no es cero.
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol obligatorio")
    ventana_barras, horizontes = _validar_parametros(
        intervalo_horas, ventana_horas, horizontes_horas)
    pasos = {h: h // intervalo_horas for h in horizontes}
    max_pasos = max(pasos.values())
    n = len(velas)
    if n < ventana_barras + max_pasos + 1:
        return ()

    intervalo_ms = intervalo_horas * 60 * 60 * 1000

    # prefijo de rupturas: permite verificar continuidad de [a,b] en O(1).
    rupturas = [0] * n
    for i in range(1, n):
        gap = 0 if velas[i].open_time_ms - velas[i - 1].open_time_ms == intervalo_ms else 1
        rupturas[i] = rupturas[i - 1] + gap

    def contiguo(a: int, b: int) -> bool:
        return 0 <= a <= b < n and rupturas[b] == rupturas[a]

    salida = []
    # i necesita close(t-ventana), barras de estado y futuro max_h.
    for i in range(ventana_barras, n - max_pasos):
        inicio_hist = i - ventana_barras
        fin_futuro = i + max_pasos
        if not contiguo(inicio_hist, fin_futuro):
            continue

        actuales = velas[i - ventana_barras + 1:i + 1]
        entrada = velas[i].close
        if entrada <= 0:  # ya validado, guarda defensiva
            continue

        low24 = min(v.low for v in actuales)
        high24 = max(v.high for v in actuales)
        qv24 = sum((v.quote_volume for v in actuales), Decimal("0"))
        trades24 = sum(v.trades for v in actuales)
        close_ventana_atras = velas[inicio_hist].close

        estado = EstadoHistorico(
            symbol=symbol,
            timestamp_ms=velas[i].close_time_ms,
            close=entrada,
            quote_volume_24h=qv24,
            trades_24h=trades24,
            rango_24h=(high24 - low24) / low24,
            momentum_cierre_24h_pct=((entrada / close_ventana_atras) - Decimal("1")) * Decimal("100"),
        )

        etiquetas = []
        for h in horizontes:
            j = i + pasos[h]
            futuras = velas[i + 1:j + 1]
            cierre_futuro = velas[j].close
            max_high = max(v.high for v in futuras)
            min_low = min(v.low for v in futuras)
            etiquetas.append(EtiquetaHorizonte(
                horizonte_horas=h,
                retorno_cierre=(cierre_futuro / entrada) - Decimal("1"),
                mfe=max(Decimal("0"), (max_high / entrada) - Decimal("1")),
                mae=min(Decimal("0"), (min_low / entrada) - Decimal("1")),
            ))

        salida.append(ObservacionEdge(estado=estado, etiquetas=tuple(etiquetas)))

    return tuple(salida)
