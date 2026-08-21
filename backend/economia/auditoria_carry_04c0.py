"""Auditoría de infraestructura histórica para cash-and-carry BOT 2.0-04C-0.

Solo lista metadatos públicos S3 de Binance Vision. No descarga ZIP ni calcula PnL.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional, Tuple

import requests

S3_LIST_URL_04C0 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
TIMEOUT_04C0_SEGUNDOS = 30
MAX_KEYS_04C0 = 1000
UNDERLYINGS_04C0 = ("BTC", "ETH")
YEARS_04C0 = tuple(range(2022, 2026))
MESES_04C0 = tuple((y, m) for y in YEARS_04C0 for m in range(1, 13))

_RE_MES = re.compile(r"-(\d{4})-(\d{2})\.zip$")
_RE_DATED = re.compile(r"^(BTC|ETH)USDT_(\d{6})$")


@dataclass(frozen=True)
class ObjetoS3Carry04C0:
    key: str
    size: int


@dataclass(frozen=True)
class ListadoS3Carry04C0:
    prefix: str
    objetos: Tuple[ObjetoS3Carry04C0, ...]
    completo: bool
    n_requests: int
    error: Optional[str]


@dataclass(frozen=True)
class ContratoDated04C0:
    underlying: str
    symbol: str
    expiry: date
    meses_trade: Tuple[Tuple[int, int], ...]
    meses_mark: Tuple[Tuple[int, int], ...]
    continuidad_trade: Decimal
    cobertura_mark_sobre_trade: Decimal
    bytes_trade: int
    bytes_mark: int
    apto_trade: bool
    apto_mark: bool


@dataclass(frozen=True)
class AuditoriaCarry04C0:
    spot_meses: Tuple[Tuple[str, int, int, int], ...]
    funding_meses: Tuple[Tuple[str, int, int, int], ...]
    contratos: Tuple[ContratoDated04C0, ...]
    contratos_por_anio: Tuple[Tuple[str, int, int], ...]
    n_contratos: int
    fraccion_contratos_trade_continuos: Decimal
    fraccion_contratos_mark_aptos: Decimal
    bytes_total: int
    dataset_apto: bool
    motivos_rechazo: Tuple[str, ...]
    errores_listado: Tuple[str, ...]


def _error(exc: Exception) -> str:
    texto = str(exc).replace("\n", " ").replace("\r", " ")
    return f"{type(exc).__name__}: {texto[:300]}"


def _child_text(node: ET.Element, name: str) -> Optional[str]:
    for child in node:
        if child.tag.rsplit("}", 1)[-1] == name:
            return child.text
    return None


def _parse_s3(xml_bytes: bytes) -> Tuple[Tuple[ObjetoS3Carry04C0, ...], bool, Optional[str]]:
    root = ET.fromstring(xml_bytes)
    objetos = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "Contents":
            continue
        key = _child_text(node, "Key")
        size_txt = _child_text(node, "Size")
        if key is None or size_txt is None:
            raise ValueError("Contents S3 incompleto")
        size = int(size_txt)
        if size < 0:
            raise ValueError("Size S3 negativo")
        objetos.append(ObjetoS3Carry04C0(key, size))

    truncado_txt = None
    token = None
    for node in root:
        local = node.tag.rsplit("}", 1)[-1]
        if local == "IsTruncated":
            truncado_txt = (node.text or "").strip().lower()
        elif local == "NextContinuationToken":
            token = node.text
    if truncado_txt not in {"true", "false"}:
        raise ValueError("IsTruncated S3 invalido")
    truncado = truncado_txt == "true"
    if truncado and not token:
        raise ValueError("S3 truncado sin continuation token")
    return tuple(objetos), truncado, token


def listar_prefix_04c0(
    prefix: str,
    *,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_segundos: int = TIMEOUT_04C0_SEGUNDOS,
) -> ListadoS3Carry04C0:
    if not prefix.startswith("data/") or ".." in prefix:
        raise ValueError("prefix invalido")
    get = requests.get if http_get is None else http_get
    token = None
    vistos = set()
    objetos = []
    n_requests = 0
    try:
        while True:
            params = {"list-type": "2", "prefix": prefix, "max-keys": MAX_KEYS_04C0}
            if token is not None:
                params["continuation-token"] = token
            n_requests += 1
            r = get(S3_LIST_URL_04C0, params=params, timeout=timeout_segundos)
            r.raise_for_status()
            contenido = getattr(r, "content", None)
            if contenido is None:
                contenido = str(r.text).encode("utf-8")
            pagina, truncado, siguiente = _parse_s3(contenido)
            objetos.extend(pagina)
            if not truncado:
                break
            assert siguiente is not None
            if siguiente in vistos:
                raise ValueError("continuation token S3 repetido")
            vistos.add(siguiente)
            token = siguiente
        return ListadoS3Carry04C0(prefix, tuple(objetos), True, n_requests, None)
    except Exception as exc:
        return ListadoS3Carry04C0(prefix, (), False, n_requests, _error(exc))


def _periodo(key: str) -> Optional[Tuple[int, int]]:
    m = _RE_MES.search(key)
    if not m:
        return None
    y, mes = int(m.group(1)), int(m.group(2))
    if (y, mes) not in MESES_04C0:
        return None
    return y, mes


def _meses_entre(inicio: Tuple[int, int], fin: Tuple[int, int]) -> Tuple[Tuple[int, int], ...]:
    y, m = inicio
    fy, fm = fin
    out = []
    while (y, m) <= (fy, fm):
        out.append((y, m))
        m += 1
        if m == 13:
            y += 1
            m = 1
    return tuple(out)


def _frac(num: int, den: int) -> Decimal:
    return Decimal(num) / Decimal(den) if den else Decimal("0")


def _expiry(symbol: str) -> Optional[Tuple[str, date]]:
    m = _RE_DATED.match(symbol)
    if not m:
        return None
    underlying, yymmdd = m.groups()
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    try:
        expiry = date(2000 + yy, mm, dd)
    except ValueError:
        return None
    if expiry.year not in YEARS_04C0:
        return None
    return underlying, expiry


def _dated_objects(objetos: Iterable[ObjetoS3Carry04C0], family: str):
    # family: klines o markPriceKlines; solo 1h y ZIP mensuales.
    rx = re.compile(
        rf"^data/futures/um/monthly/{re.escape(family)}/((?:BTC|ETH)USDT_\d{{6}})/1h/\1-1h-(\d{{4}})-(\d{{2}})\.zip$"
    )
    out = defaultdict(list)
    for obj in objetos:
        m = rx.match(obj.key)
        if not m or obj.size <= 0:
            continue
        symbol, y, mes = m.group(1), int(m.group(2)), int(m.group(3))
        if (y, mes) in MESES_04C0 and _expiry(symbol) is not None:
            out[symbol].append((y, mes, obj.size))
    return out


def auditar_carry_04c0(
    *,
    http_get: Optional[Callable[..., Any]] = None,
) -> AuditoriaCarry04C0:
    listados = []
    for underlying in UNDERLYINGS_04C0:
        spot = f"{underlying}USDT"
        listados.append(listar_prefix_04c0(f"data/spot/monthly/klines/{spot}/1h/", http_get=http_get))
        listados.append(listar_prefix_04c0(f"data/futures/um/monthly/fundingRate/{spot}/", http_get=http_get))
        listados.append(listar_prefix_04c0(f"data/futures/um/monthly/klines/{spot}_", http_get=http_get))
        listados.append(listar_prefix_04c0(f"data/futures/um/monthly/markPriceKlines/{spot}_", http_get=http_get))

    errores = tuple(f"{l.prefix}: {l.error}" for l in listados if not l.completo)
    por_prefix = {l.prefix: l for l in listados}

    spot_res = []
    funding_res = []
    bytes_total = 0
    for underlying in UNDERLYINGS_04C0:
        spot = f"{underlying}USDT"
        lp = por_prefix[f"data/spot/monthly/klines/{spot}/1h/"]
        objetos_spot = [o for o in lp.objetos if o.key.endswith(".zip") and o.size > 0]
        meses_spot = {_periodo(o.key) for o in objetos_spot}
        meses_spot.discard(None)
        bytes_spot = sum(o.size for o in objetos_spot if _periodo(o.key) is not None)
        bytes_total += bytes_spot
        spot_res.append((spot, len(meses_spot), 48, bytes_spot))

        lf = por_prefix[f"data/futures/um/monthly/fundingRate/{spot}/"]
        objetos_funding = [o for o in lf.objetos if o.key.endswith(".zip") and o.size > 0]
        meses_funding = {_periodo(o.key) for o in objetos_funding}
        meses_funding.discard(None)
        bytes_funding = sum(o.size for o in objetos_funding if _periodo(o.key) is not None)
        bytes_total += bytes_funding
        funding_res.append((spot, len(meses_funding), 48, bytes_funding))

    trade_by = defaultdict(list)
    mark_by = defaultdict(list)
    for underlying in UNDERLYINGS_04C0:
        spot = f"{underlying}USDT"
        lt = por_prefix[f"data/futures/um/monthly/klines/{spot}_"]
        lm = por_prefix[f"data/futures/um/monthly/markPriceKlines/{spot}_"]
        for symbol, vals in _dated_objects(lt.objetos, "klines").items():
            trade_by[symbol].extend(vals)
        for symbol, vals in _dated_objects(lm.objetos, "markPriceKlines").items():
            mark_by[symbol].extend(vals)

    contratos = []
    por_anio = Counter()
    for symbol in sorted(trade_by):
        exp = _expiry(symbol)
        if exp is None:
            continue
        underlying, expiry = exp
        trade_vals = trade_by[symbol]
        mark_vals = mark_by.get(symbol, [])
        trade_meses = tuple(sorted({(y, m) for y, m, _ in trade_vals}))
        mark_meses = tuple(sorted({(y, m) for y, m, _ in mark_vals}))
        if not trade_meses:
            continue
        esperado = _meses_entre(trade_meses[0], (expiry.year, expiry.month))
        trade_set = set(trade_meses)
        mark_set = set(mark_meses)
        continuidad = _frac(sum(p in trade_set for p in esperado), len(esperado))
        mark_cov = _frac(sum(p in mark_set for p in esperado), len(esperado))
        bytes_trade = sum(size for _, _, size in trade_vals)
        bytes_mark = sum(size for _, _, size in mark_vals)
        bytes_total += bytes_trade + bytes_mark
        apto_trade = continuidad == Decimal("1")
        apto_mark = mark_cov >= Decimal("0.90")
        contratos.append(
            ContratoDated04C0(
                underlying=underlying,
                symbol=symbol,
                expiry=expiry,
                meses_trade=trade_meses,
                meses_mark=mark_meses,
                continuidad_trade=continuidad,
                cobertura_mark_sobre_trade=mark_cov,
                bytes_trade=bytes_trade,
                bytes_mark=bytes_mark,
                apto_trade=apto_trade,
                apto_mark=apto_mark,
            )
        )
        por_anio[(underlying, expiry.year)] += 1

    n = len(contratos)
    frac_trade = _frac(sum(c.apto_trade for c in contratos), n)
    frac_mark = _frac(sum(c.apto_mark for c in contratos), n)
    contratos_anio = tuple((u, y, por_anio[(u, y)]) for u in UNDERLYINGS_04C0 for y in YEARS_04C0)

    motivos = []
    if errores:
        motivos.append("LISTADOS_S3_INCOMPLETOS")
    if any(actual != esperado for _, actual, esperado, _ in spot_res):
        motivos.append("SPOT_48_MESES_INCOMPLETO")
    if any(actual < 46 for _, actual, _, _ in funding_res):
        motivos.append("FUNDING_PERP_COBERTURA_INSUFICIENTE")
    if any(qty < 2 for _, _, qty in contratos_anio):
        motivos.append("VENCIMIENTOS_POR_ANIO_INSUFICIENTES")
    if frac_trade < Decimal("0.90"):
        motivos.append("CONTINUIDAD_KLINES_DATED_INSUFICIENTE")
    if frac_mark < Decimal("0.90"):
        motivos.append("COBERTURA_MARK_PRICE_INSUFICIENTE")

    return AuditoriaCarry04C0(
        spot_meses=tuple(spot_res),
        funding_meses=tuple(funding_res),
        contratos=tuple(contratos),
        contratos_por_anio=contratos_anio,
        n_contratos=n,
        fraccion_contratos_trade_continuos=frac_trade,
        fraccion_contratos_mark_aptos=frac_mark,
        bytes_total=bytes_total,
        dataset_apto=not motivos,
        motivos_rechazo=tuple(motivos),
        errores_listado=errores,
    )
