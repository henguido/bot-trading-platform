"""Auditoría complete-case de matriz OF fija BOT 2.0-04G-1a."""
from __future__ import annotations

import csv
import io
import math
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from statistics import stdev
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import requests

from backend.economia.protocolo_orderflow_matrix_04g1a import (
    ARCHIVO_DESDE_04G1A, BASES_04G1A, CORE_QUOTES_04G1A,
    DATA_BASE_URL_04G1A, FEATURE_DESDE_04G1A, FEATURE_HASTA_04G1A,
    FRACCION_DIAS_USABLES_POR_ANIO_MIN_04G1A,
    FRACCION_DIAS_USABLES_TOTAL_MIN_04G1A, INTERVALO_04G1A,
    MAX_WORKERS_DOWNLOAD_04G1A, MAX_WORKERS_LIST_04G1A,
    MIN_BASES_COMPLETE_DIA_04G1A, REINTENTOS_04G1A, ROOT_PREFIX_04G1A,
    S3_LIST_URL_04G1A, STATUS_APTO_04G1A, STATUS_NO_APTO_04G1A,
    TIMEOUT_04G1A_SEGUNDOS, VENTANA_STD_DIAS_04G1A,
)

_MONTH_RE = re.compile(r"-(?P<year>\d{4})-(?P<month>\d{2})\.zip$")

@dataclass(frozen=True)
class Obj04G1A:
    base: str; quote: str; symbol: str; month: date; key: str; size: int

@dataclass(frozen=True)
class Bar04G1A:
    day: date; close: Decimal; quote_volume: Decimal; taker_buy_quote: Decimal
    @property
    def sell_quote(self) -> Decimal:
        return self.quote_volume - self.taker_buy_quote

@dataclass(frozen=True)
class Content04G1A:
    base: str; quote: str; month: date; bars: Tuple[Bar04G1A, ...]; bytes_: int; errors: Tuple[str, ...]


def _tag(tag: str) -> str: return tag.rsplit("}", 1)[-1]

def _first(root: ET.Element, name: str) -> Optional[str]:
    for e in root.iter():
        if _tag(e.tag) == name and e.text is not None: return e.text
    return None


def _get(url: str, params: Optional[Mapping[str, str]] = None) -> requests.Response:
    last: Optional[Exception] = None
    for attempt in range(REINTENTOS_04G1A + 1):
        try:
            r = requests.get(url, params=params, headers={"User-Agent":"bot-trading-research-04g1a/1.0"}, timeout=TIMEOUT_04G1A_SEGUNDOS)
            r.raise_for_status(); return r
        except requests.RequestException as exc:
            last = exc
            if attempt < REINTENTOS_04G1A: time.sleep(0.35 * (attempt + 1))
    assert last is not None; raise last


def _list_pair(base: str, quote: str):
    symbol = f"{base}{quote}"; prefix = f"{ROOT_PREFIX_04G1A}/{symbol}/{INTERVALO_04G1A}/"
    token = None; objs: List[Obj04G1A] = []
    try:
        while True:
            params={"list-type":"2","prefix":prefix,"max-keys":"1000"}
            if token: params["continuation-token"] = token
            root=ET.fromstring(_get(S3_LIST_URL_04G1A, params).content)
            for c in root.iter():
                if _tag(c.tag)!="Contents": continue
                key=size=None
                for ch in c:
                    if _tag(ch.tag)=="Key": key=ch.text
                    elif _tag(ch.tag)=="Size": size=ch.text
                if not key or size is None or not key.endswith(".zip"): continue
                m=_MONTH_RE.search(key)
                if not m: continue
                month=date(int(m.group("year")),int(m.group("month")),1)
                if ARCHIVO_DESDE_04G1A <= month <= date(2025,12,1) and int(size)>0:
                    objs.append(Obj04G1A(base,quote,symbol,month,key,int(size)))
            truncated=(_first(root,"IsTruncated") or "false").lower()=="true"
            if not truncated: return base,quote,True,tuple(sorted(objs,key=lambda x:x.month)),None
            nxt=_first(root,"NextContinuationToken")
            if not nxt or nxt==token: return base,quote,False,tuple(objs),"LISTING_TOKEN_INVALID"
            token=nxt
    except Exception as exc:
        return base,quote,False,(),f"{type(exc).__name__}:{exc}"


def _day(raw: str):
    v=int(raw); div=1_000_000 if v>=100_000_000_000_000 else 1_000
    dt=datetime.fromtimestamp(v/div,tz=timezone.utc)
    return dt.date(), (dt.hour,dt.minute,dt.second,dt.microsecond)==(0,0,0,0)


def _parse(payload: bytes, obj: Obj04G1A) -> Content04G1A:
    bars=[]; errors=[]
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            names=[n for n in z.namelist() if n.lower().endswith('.csv') and not n.endswith('/')]
            if len(names)!=1: return Content04G1A(obj.base,obj.quote,obj.month,(),len(payload),("ZIP_CSV_COUNT_INVALID",))
            with z.open(names[0]) as raw:
                reader=csv.reader(io.TextIOWrapper(raw,encoding='utf-8-sig',newline=''))
                for num,row in enumerate(reader,1):
                    if not row: continue
                    if num==1:
                        try: int(row[0])
                        except ValueError: continue
                    if len(row)!=12: errors.append("COLUMN_COUNT_INVALID"); continue
                    try:
                        d,aligned=_day(row[0]); close=Decimal(row[4]); qv=Decimal(row[7]); trades=int(row[8]); buy=Decimal(row[10])
                    except (ValueError,InvalidOperation,OverflowError): errors.append("ROW_PARSE_INVALID"); continue
                    if not aligned: errors.append("OPEN_TIME_NOT_UTC_DAY")
                    if (d.year,d.month)!=(obj.month.year,obj.month.month): errors.append("DAY_OUTSIDE_MONTH")
                    if close<=0 or qv<0 or buy<0 or buy>qv or trades<0: errors.append("DOMAIN_INVALID")
                    bars.append(Bar04G1A(d,close,qv,buy))
    except (zipfile.BadZipFile,OSError,UnicodeError) as exc:
        return Content04G1A(obj.base,obj.quote,obj.month,(),len(payload),(f"ZIP_PARSE_ERROR:{type(exc).__name__}",))
    days=[b.day for b in bars]
    if len(days)!=len(set(days)): errors.append("DUPLICATE_DAY")
    if days!=sorted(days): errors.append("DAYS_NOT_ASCENDING")
    return Content04G1A(obj.base,obj.quote,obj.month,tuple(bars),len(payload),tuple(sorted(set(errors))))


def _download(obj: Obj04G1A) -> Content04G1A:
    try: return _parse(_get(f"{DATA_BASE_URL_04G1A}/{obj.key}").content,obj)
    except Exception as exc: return Content04G1A(obj.base,obj.quote,obj.month,(),0,(f"DOWNLOAD_ERROR:{type(exc).__name__}",))


def _raw_of(bar: Bar04G1A) -> Optional[float]:
    buy=float(bar.taker_buy_quote); sell=float(bar.sell_quote)
    if buy<=0 or sell<=0 or not math.isfinite(buy) or not math.isfinite(sell): return None
    return math.log(buy)-math.log(sell)


def _std_of(series: Mapping[date,Bar04G1A], day: date) -> Optional[float]:
    vals=[]
    for offset in range(VENTANA_STD_DIAS_04G1A-1,-1,-1):
        bar=series.get(day-timedelta(days=offset))
        v=_raw_of(bar) if bar else None
        if v is None: return None
        vals.append(v)
    sigma=stdev(vals)
    if not math.isfinite(sigma) or sigma<=0: return None
    out=vals[-1]/sigma
    return out if math.isfinite(out) else None


def _dates(start: date,end: date):
    out=[]; d=start
    while d<=end: out.append(d); d+=timedelta(days=1)
    return tuple(out)


def evaluar_matrix_04g1a(listings, contents) -> Dict[str,object]:
    reasons=[]; expected=len(BASES_04G1A)*len(CORE_QUOTES_04G1A)
    if len(listings)!=expected: reasons.append("LISTING_COUNT_MISMATCH")
    incomplete=[x for x in listings if not x[2]]
    if incomplete: reasons.append("LISTING_INCOMPLETE")
    errors=[c for c in contents if c.errors]
    if errors: reasons.append("CONTENT_ERRORS")

    daily: Dict[Tuple[str,str],Dict[date,Bar04G1A]]={}
    for c in contents:
        if c.errors: continue
        target=daily.setdefault((c.base,c.quote),{})
        for b in c.bars:
            if b.day in target: reasons.append("CROSS_FILE_DUPLICATE_DAY")
            else: target[b.day]=b

    counts={}; usable_by_year={y:0 for y in range(2022,2026)}; days_by_year={y:0 for y in range(2022,2026)}
    for day in _dates(FEATURE_DESDE_04G1A,FEATURE_HASTA_04G1A):
        complete=0
        for base in BASES_04G1A:
            features=[]
            for quote in CORE_QUOTES_04G1A:
                features.append(_std_of(daily.get((base,quote),{}),day))
            usdt=daily.get((base,"USDT"),{})
            now=usdt.get(day); prev=usdt.get(day-timedelta(days=1))
            lagged_return=(float(now.close/prev.close-Decimal("1")) if now and prev else None)
            if all(v is not None for v in features) and lagged_return is not None and math.isfinite(lagged_return): complete+=1
        counts[day.isoformat()]=complete
        days_by_year[day.year]+=1
        if complete>=MIN_BASES_COMPLETE_DIA_04G1A: usable_by_year[day.year]+=1

    usable=sum(v>=MIN_BASES_COMPLETE_DIA_04G1A for v in counts.values())
    total=len(counts); fraction=Decimal(usable)/Decimal(total)
    yearly={str(y): float(Decimal(usable_by_year[y])/Decimal(days_by_year[y])) for y in days_by_year}
    if fraction<FRACCION_DIAS_USABLES_TOTAL_MIN_04G1A: reasons.append("USABLE_DAYS_TOTAL_BELOW_GATE")
    for y in range(2022,2026):
        yf=Decimal(usable_by_year[y])/Decimal(days_by_year[y])
        if yf<FRACCION_DIAS_USABLES_POR_ANIO_MIN_04G1A: reasons.append(f"USABLE_DAYS_{y}_BELOW_GATE")

    total_bytes=sum(c.bytes_ for c in contents)
    return {
        "status": STATUS_APTO_04G1A if not reasons else STATUS_NO_APTO_04G1A,
        "core_quotes": list(CORE_QUOTES_04G1A),
        "pair_listings_complete": expected-len(incomplete), "pair_listings_expected": expected,
        "downloaded_files": len(contents), "downloaded_rows": sum(len(c.bars) for c in contents),
        "compressed_gib": round(total_bytes/(1024**3),6), "content_error_files": len(errors),
        "feature_days": total, "usable_days": usable, "usable_days_fraction": float(fraction),
        "usable_fraction_by_year": yearly,
        "complete_bases_min": min(counts.values()) if counts else 0,
        "complete_bases_max": max(counts.values()) if counts else 0,
        "complete_bases_by_day": counts,
        "reasons": sorted(set(reasons)),
        "future_return_calculated": False, "ml_trained": False, "pnl_calculated": False,
        "quote_selected_by_performance": False, "imputation_used": False,
        "credentials_used": False, "development_2026_open": False,
    }


def auditar_matrix_04g1a() -> Dict[str,object]:
    targets=[(b,q) for b in BASES_04G1A for q in CORE_QUOTES_04G1A]
    listings=[]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_LIST_04G1A) as ex:
        futs=[ex.submit(_list_pair,*t) for t in targets]
        for f in as_completed(futs): listings.append(f.result())
    listings.sort(key=lambda x:(x[0],x[1]))
    objs=[o for _,_,complete,os,_ in listings if complete for o in os]
    contents=[]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_DOWNLOAD_04G1A) as ex:
        futs=[ex.submit(_download,o) for o in objs]
        for f in as_completed(futs): contents.append(f.result())
    contents.sort(key=lambda c:(c.base,c.quote,c.month))
    return evaluar_matrix_04g1a(tuple(listings),tuple(contents))
