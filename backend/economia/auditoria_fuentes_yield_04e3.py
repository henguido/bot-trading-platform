"""Auditoría BOT 2.0-04E-3 de fuentes de yield públicas.

Solo inventaría metadata S3 de Binance Options. Lido/Aave se clasifican por
mecánica/acceso documentado. No descarga ZIPs ni calcula PnL.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Dict, Optional, Sequence, Tuple

import requests

from backend.economia.protocolo_fuentes_yield_04e3 import (
    AAVE_HISTORICO_OFICIAL_SIN_KEY_VERIFICADO_04E3,
    AAVE_SEMANTICA_EXACTA_04E3,
    AAVE_STATUS_04E3,
    ANIOS_04E3,
    BINANCE_S3_04E3,
    CREDENCIALES_PERMITIDAS_04E3,
    DESCARGAR_CONTENIDO_OPTIONS_PERMITIDO_04E3,
    DESARROLLO_2026_ABIERTO_04E3,
    HASTA_EXCLUSIVO_04E3,
    IMPUTACION_YIELD_PERMITIDA_04E3,
    LIDO_HISTORICO_OFICIAL_SIN_KEY_VERIFICADO_04E3,
    LIDO_SEMANTICA_EXACTA_04E3,
    LIDO_STATUS_04E3,
    LIVE_PERMITIDO_04E3,
    MAX_PAGINAS_S3_04E3,
    MIN_DIAS_OPTIONS_POR_ANIO_04E3,
    OPTIONS_EOH_PREFIX_04E3,
    OPTIONS_STATUS_APTO_04E3,
    OPTIONS_STATUS_INCOMPLETO_04E3,
    PAPER_OPERATIVO_PERMITIDO_04E3,
    PNL_PERMITIDO_04E3,
    REINTENTOS_04E3,
    RENDER_PERMITIDO_04E3,
    TIMEOUT_04E3_SEGUNDOS,
    USAR_PRECIO_SECUNDARIO_COMO_YIELD_PERMITIDO_04E3,
    DESDE_04E3,
)

_DATE_RE = re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)")
_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


@dataclass(frozen=True)
class ObjetoS3_04E3:
    key: str
    size: int


@dataclass(frozen=True)
class ResultadoOptions04E3:
    status: str
    prefix: str
    listings_complete: bool
    pages: int
    zip_objects_total: int
    zero_size_zip_objects: int
    duplicate_keys: int
    first_date: str | None
    last_date: str | None
    days_by_year: Tuple[Tuple[int, int], ...]
    zip_objects_by_year: Tuple[Tuple[int, int], ...]
    compressed_bytes_2022_2025: int
    compressed_gib_2022_2025: float
    apt: bool
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class FuenteEstatica04E3:
    source: str
    exact_yield_semantics: bool
    official_historical_no_key_verified: bool
    status: str
    apt_for_next_stage: bool
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class ResultadoFuentesYield04E3:
    options: ResultadoOptions04E3
    lido: FuenteEstatica04E3
    aave: FuenteEstatica04E3
    candidates_apt_for_next_stage: Tuple[str, ...]
    pnl_calculated: bool
    option_content_downloaded: bool
    credentials_used: bool
    development_2026_opened: bool


class S3Publico04E3:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()

    def _get(self, params: Dict[str, object]) -> str:
        last_exc: Exception | None = None
        for attempt in range(REINTENTOS_04E3 + 1):
            try:
                r = self.session.get(BINANCE_S3_04E3, params=params, timeout=TIMEOUT_04E3_SEGUNDOS)
                r.raise_for_status()
                if not r.text.strip():
                    raise ValueError("S3 listing vacío")
                return r.text
            except Exception as exc:  # pragma: no cover - retry path exercised by CI network
                last_exc = exc
                if attempt < REINTENTOS_04E3:
                    time.sleep(0.25 * (attempt + 1))
        assert last_exc is not None
        raise last_exc

    def listar_objetos(self, prefix: str) -> Tuple[Tuple[ObjetoS3_04E3, ...], int, bool]:
        token: str | None = None
        pages = 0
        out: list[ObjetoS3_04E3] = []
        completed = False
        while pages < MAX_PAGINAS_S3_04E3:
            params: Dict[str, object] = {"list-type": "2", "prefix": prefix, "max-keys": 1000}
            if token:
                params["continuation-token"] = token
            xml = self._get(params)
            rows, truncated, next_token = parse_s3_page_04e3(xml)
            out.extend(rows)
            pages += 1
            if not truncated:
                completed = True
                break
            if not next_token:
                raise ValueError("S3 truncado sin continuation token")
            token = next_token
        return tuple(out), pages, completed


def _text(node: ET.Element, name: str) -> str | None:
    child = node.find(f"s3:{name}", _NS)
    if child is None:
        child = node.find(name)
    return child.text if child is not None else None


def parse_s3_page_04e3(xml: str) -> Tuple[Tuple[ObjetoS3_04E3, ...], bool, str | None]:
    root = ET.fromstring(xml)
    contents = root.findall("s3:Contents", _NS) or root.findall("Contents")
    rows: list[ObjetoS3_04E3] = []
    for content in contents:
        key = _text(content, "Key")
        size_raw = _text(content, "Size")
        if not key or size_raw is None:
            raise ValueError("S3 Contents incompleto")
        size = int(size_raw)
        if size < 0:
            raise ValueError("S3 Size negativo")
        rows.append(ObjetoS3_04E3(key=key, size=size))
    truncated_raw = (_text(root, "IsTruncated") or "false").strip().lower()
    truncated = truncated_raw == "true"
    token = _text(root, "NextContinuationToken")
    return tuple(rows), truncated, token


def extraer_fecha_key_04e3(key: str) -> date | None:
    matches = list(_DATE_RE.finditer(key))
    if not matches:
        return None
    # El nombre de archivo puede contener más de una fecha en otros datasets;
    # EOH Summary debe usar la última fecha explícita del key.
    year, month, day = map(int, matches[-1].groups())
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"fecha inválida en key {key}") from exc


def evaluar_options_04e3(
    objects: Sequence[ObjetoS3_04E3], *, pages: int, listings_complete: bool
) -> ResultadoOptions04E3:
    keys = [row.key for row in objects]
    dup = len(keys) - len(set(keys))
    zip_rows = [row for row in objects if row.key.endswith(".zip")]
    zero = sum(1 for row in zip_rows if row.size == 0)
    dates: list[date] = []
    obj_year = Counter()
    day_year: Dict[int, set[date]] = {year: set() for year in ANIOS_04E3}
    compressed = 0
    for row in zip_rows:
        d = extraer_fecha_key_04e3(row.key)
        if d is None:
            continue
        dates.append(d)
        if DESDE_04E3 <= d < HASTA_EXCLUSIVO_04E3:
            obj_year[d.year] += 1
            day_year[d.year].add(d)
            compressed += row.size

    reasons: list[str] = []
    if not listings_complete:
        reasons.append("LISTADO_S3_INCOMPLETO")
    if not zip_rows:
        reasons.append("SIN_ZIPS_OPTIONS")
    if dup:
        reasons.append("KEYS_DUPLICADOS")
    if zero:
        reasons.append("ZIPS_TAMANO_CERO")
    for year in ANIOS_04E3:
        if len(day_year[year]) < MIN_DIAS_OPTIONS_POR_ANIO_04E3:
            reasons.append(f"COBERTURA_{year}_MENOR_{MIN_DIAS_OPTIONS_POR_ANIO_04E3}_DIAS")

    apt = not reasons
    return ResultadoOptions04E3(
        status=OPTIONS_STATUS_APTO_04E3 if apt else OPTIONS_STATUS_INCOMPLETO_04E3,
        prefix=OPTIONS_EOH_PREFIX_04E3,
        listings_complete=listings_complete,
        pages=pages,
        zip_objects_total=len(zip_rows),
        zero_size_zip_objects=zero,
        duplicate_keys=dup,
        first_date=min(dates).isoformat() if dates else None,
        last_date=max(dates).isoformat() if dates else None,
        days_by_year=tuple((year, len(day_year[year])) for year in ANIOS_04E3),
        zip_objects_by_year=tuple((year, obj_year[year]) for year in ANIOS_04E3),
        compressed_bytes_2022_2025=compressed,
        compressed_gib_2022_2025=compressed / (1024 ** 3),
        apt=apt,
        reasons=tuple(reasons),
    )


def _fuente_estatica(
    source: str, *, semantics: bool, historical_no_key: bool, status: str
) -> FuenteEstatica04E3:
    reasons: list[str] = []
    if not semantics:
        reasons.append("MECANICA_YIELD_NO_EXACTA")
    if not historical_no_key:
        reasons.append("TRANSPORTE_HISTORICO_OFICIAL_SIN_KEY_NO_VERIFICADO")
    apt = semantics and historical_no_key
    return FuenteEstatica04E3(
        source=source,
        exact_yield_semantics=semantics,
        official_historical_no_key_verified=historical_no_key,
        status=status,
        apt_for_next_stage=apt,
        reasons=tuple(reasons),
    )


def ejecutar_auditoria_fuentes_yield_04e3(
    s3: Optional[S3Publico04E3] = None,
) -> ResultadoFuentesYield04E3:
    if any(
        (
            PNL_PERMITIDO_04E3,
            DESCARGAR_CONTENIDO_OPTIONS_PERMITIDO_04E3,
            CREDENCIALES_PERMITIDAS_04E3,
            PAPER_OPERATIVO_PERMITIDO_04E3,
            LIVE_PERMITIDO_04E3,
            RENDER_PERMITIDO_04E3,
            DESARROLLO_2026_ABIERTO_04E3,
            IMPUTACION_YIELD_PERMITIDA_04E3,
            USAR_PRECIO_SECUNDARIO_COMO_YIELD_PERMITIDO_04E3,
        )
    ):
        raise RuntimeError("locks 04E-3 violados")

    s3 = s3 or S3Publico04E3()
    objects, pages, completed = s3.listar_objetos(OPTIONS_EOH_PREFIX_04E3)
    options = evaluar_options_04e3(objects, pages=pages, listings_complete=completed)
    lido = _fuente_estatica(
        "LIDO_STETH",
        semantics=LIDO_SEMANTICA_EXACTA_04E3,
        historical_no_key=LIDO_HISTORICO_OFICIAL_SIN_KEY_VERIFICADO_04E3,
        status=LIDO_STATUS_04E3,
    )
    aave = _fuente_estatica(
        "AAVE_LENDING",
        semantics=AAVE_SEMANTICA_EXACTA_04E3,
        historical_no_key=AAVE_HISTORICO_OFICIAL_SIN_KEY_VERIFICADO_04E3,
        status=AAVE_STATUS_04E3,
    )
    apt = []
    if options.apt:
        apt.append("BINANCE_OPTIONS")
    if lido.apt_for_next_stage:
        apt.append(lido.source)
    if aave.apt_for_next_stage:
        apt.append(aave.source)
    return ResultadoFuentesYield04E3(
        options=options,
        lido=lido,
        aave=aave,
        candidates_apt_for_next_stage=tuple(apt),
        pnl_calculated=False,
        option_content_downloaded=False,
        credentials_used=False,
        development_2026_opened=False,
    )
