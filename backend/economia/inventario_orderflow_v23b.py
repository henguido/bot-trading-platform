"""Inventario S3 sin descarga de trades para BOT 2.0-04B-v23b."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Optional, Tuple

import requests

from backend.economia.historico_aggtrades_v23 import _parsear_listado_s3
from backend.economia.protocolo_orderflow_v23b import (
    FECHAS_OBJETIVO_V23B,
    FRACCION_ARCHIVOS_DISPONIBLES_MIN_V23B,
    FRACCION_FECHAS_APTAS_MIN_V23B,
    MAX_KEYS_S3_V23B,
    MIN_SIMBOLOS_POR_FECHA_V23B,
    N_ARCHIVOS_OBJETIVO_V23B,
    N_FECHAS_OBJETIVO_V23B,
    PREFIJO_SPOT_DAILY_V23B,
    PRESUPUESTO_CI_BYTES_V23B,
    S3_LIST_URL_V23B,
    TIMEOUT_V23B_SEGUNDOS,
    UNIVERSO_V23B,
)

_RE_DIA = re.compile(r"-aggTrades-(\d{4})-(\d{2})-(\d{2})\.zip$")
_FECHAS_SET = frozenset(FECHAS_OBJETIVO_V23B)


@dataclass(frozen=True)
class ArchivoObjetivoV23B:
    symbol: str
    fecha: date
    key: str
    size: int


@dataclass(frozen=True)
class ListadoSymbolV23B:
    symbol: str
    archivos: Tuple[ArchivoObjetivoV23B, ...]
    completa: bool
    n_requests: int
    error: Optional[str]


@dataclass(frozen=True)
class ResultadoPlanV23B:
    resultado: str
    apto: bool
    entra_ci: bool
    listados_completos: int
    archivos_presentes: int
    archivos_objetivo: int
    fraccion_archivos: Decimal
    fechas_aptas: int
    fechas_objetivo: int
    fraccion_fechas_aptas: Decimal
    bytes_total: int
    gib_total: Decimal
    archivos_duplicados: int
    archivos_tamano_cero: int
    minimo_simbolos_fecha: int
    maximo_simbolos_fecha: int
    motivos_rechazo: Tuple[str, ...]
    faltantes: Tuple[str, ...]
    simbolos_por_fecha: Tuple[Tuple[str, int], ...]


def _error(exc: Exception) -> str:
    texto = str(exc).replace("\n", " ").replace("\r", " ")
    return f"{type(exc).__name__}: {texto[:300]}"


def _fecha_desde_key(symbol: str, key: str) -> Optional[date]:
    prefijo = f"{PREFIJO_SPOT_DAILY_V23B}/{symbol}/{symbol}-aggTrades-"
    if not key.startswith(prefijo):
        return None
    m = _RE_DIA.search(key)
    if not m:
        return None
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return d if d in _FECHAS_SET else None


def listar_symbol_v23b(
    symbol: str,
    *,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_segundos: int = TIMEOUT_V23B_SEGUNDOS,
) -> ListadoSymbolV23B:
    """Lista solo los ZIP diarios que pertenecen al calendario fijo v23b."""
    if symbol not in UNIVERSO_V23B:
        raise ValueError("symbol fuera del universo v23b")
    if isinstance(timeout_segundos, bool) or not isinstance(timeout_segundos, int) or timeout_segundos <= 0:
        raise ValueError("timeout invalido")

    get = requests.get if http_get is None else http_get
    prefijo = f"{PREFIJO_SPOT_DAILY_V23B}/{symbol}/"
    token = None
    tokens_vistos = set()
    n_requests = 0
    archivos = []
    try:
        while True:
            params = {"list-type": "2", "prefix": prefijo, "max-keys": MAX_KEYS_S3_V23B}
            if token is not None:
                params["continuation-token"] = token
            n_requests += 1
            r = get(S3_LIST_URL_V23B, params=params, timeout=timeout_segundos)
            r.raise_for_status()
            contenido = getattr(r, "content", None)
            if contenido is None:
                contenido = str(r.text).encode("utf-8")
            pares, truncado, siguiente = _parsear_listado_s3(contenido)
            for key, size in pares:
                fecha = _fecha_desde_key(symbol, key)
                if fecha is not None:
                    archivos.append(ArchivoObjetivoV23B(symbol, fecha, key, size))
            if not truncado:
                break
            if not siguiente:
                raise ValueError("S3 truncado sin continuation token")
            if siguiente in tokens_vistos:
                raise ValueError("continuation token S3 repetido")
            tokens_vistos.add(siguiente)
            token = siguiente

        return ListadoSymbolV23B(
            symbol=symbol,
            archivos=tuple(sorted(archivos, key=lambda a: (a.fecha, a.key))),
            completa=True,
            n_requests=n_requests,
            error=None,
        )
    except Exception as exc:
        return ListadoSymbolV23B(symbol, (), False, n_requests, _error(exc))


def evaluar_plan_v23b(listados: Tuple[ListadoSymbolV23B, ...]) -> ResultadoPlanV23B:
    """Aplica exclusivamente gates de cobertura/transporte predeclarados."""
    por_symbol = {l.symbol: l for l in listados}
    motivos = []
    if len(por_symbol) != len(listados):
        motivos.append("LISTADOS_SYMBOL_DUPLICADOS")
    faltan_listados = [s for s in UNIVERSO_V23B if s not in por_symbol]
    if faltan_listados:
        motivos.append("LISTADOS_SYMBOL_FALTANTES")
    completos = sum(1 for s in UNIVERSO_V23B if s in por_symbol and por_symbol[s].completa)
    if completos != len(UNIVERSO_V23B):
        motivos.append("LISTADOS_REMOTOS_INCOMPLETOS")

    por_par = {}
    for listado in listados:
        for archivo in listado.archivos:
            por_par.setdefault((archivo.symbol, archivo.fecha), []).append(archivo)

    presentes = 0
    duplicados = 0
    tamano_cero = 0
    bytes_total = 0
    faltantes = []
    simbolos_por_fecha = []
    for fecha in FECHAS_OBJETIVO_V23B:
        n_fecha = 0
        for symbol in UNIVERSO_V23B:
            candidatos = por_par.get((symbol, fecha), [])
            if len(candidatos) == 1:
                presentes += 1
                n_fecha += 1
                if candidatos[0].size <= 0:
                    tamano_cero += 1
                else:
                    bytes_total += candidatos[0].size
            elif len(candidatos) == 0:
                faltantes.append(f"{symbol}:{fecha.isoformat()}")
            else:
                duplicados += len(candidatos) - 1
        simbolos_por_fecha.append((fecha.isoformat(), n_fecha))

    fraccion_archivos = Decimal(presentes) / Decimal(N_ARCHIVOS_OBJETIVO_V23B)
    fechas_aptas = sum(1 for _, n in simbolos_por_fecha if n >= MIN_SIMBOLOS_POR_FECHA_V23B)
    fraccion_fechas = Decimal(fechas_aptas) / Decimal(N_FECHAS_OBJETIVO_V23B)
    if duplicados:
        motivos.append("ARCHIVOS_OBJETIVO_DUPLICADOS")
    if tamano_cero:
        motivos.append("ARCHIVOS_OBJETIVO_TAMANO_CERO")
    if fraccion_archivos < FRACCION_ARCHIVOS_DISPONIBLES_MIN_V23B:
        motivos.append("COBERTURA_ARCHIVOS_INSUFICIENTE")
    if fraccion_fechas < FRACCION_FECHAS_APTAS_MIN_V23B:
        motivos.append("COBERTURA_CROSS_SECTION_FECHAS_INSUFICIENTE")

    apto = not motivos
    entra_ci = apto and bytes_total <= PRESUPUESTO_CI_BYTES_V23B
    if not apto:
        resultado = "PLAN_TRANSFERENCIA_NO_APTO_V23B"
    elif entra_ci:
        resultado = "PLAN_TRANSFERENCIA_APTO_CI_V23B"
    else:
        resultado = "PLAN_TRANSFERENCIA_APTO_FUERA_CI_V23B"

    conteos = [n for _, n in simbolos_por_fecha]
    return ResultadoPlanV23B(
        resultado=resultado,
        apto=apto,
        entra_ci=entra_ci,
        listados_completos=completos,
        archivos_presentes=presentes,
        archivos_objetivo=N_ARCHIVOS_OBJETIVO_V23B,
        fraccion_archivos=fraccion_archivos,
        fechas_aptas=fechas_aptas,
        fechas_objetivo=N_FECHAS_OBJETIVO_V23B,
        fraccion_fechas_aptas=fraccion_fechas,
        bytes_total=bytes_total,
        gib_total=Decimal(bytes_total) / Decimal(1024**3),
        archivos_duplicados=duplicados,
        archivos_tamano_cero=tamano_cero,
        minimo_simbolos_fecha=min(conteos) if conteos else 0,
        maximo_simbolos_fecha=max(conteos) if conteos else 0,
        motivos_rechazo=tuple(motivos),
        faltantes=tuple(faltantes),
        simbolos_por_fecha=tuple(simbolos_por_fecha),
    )
