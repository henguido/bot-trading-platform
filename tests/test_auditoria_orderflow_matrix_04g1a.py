from datetime import date,timedelta
from decimal import Decimal

from backend.economia.auditoria_orderflow_matrix_04g1a import Bar04G1A,Content04G1A,Obj04G1A,evaluar_matrix_04g1a
from backend.economia.protocolo_orderflow_matrix_04g1a import (
    BASES_04G1A,CORE_QUOTES_04G1A,FRACCION_DIAS_USABLES_POR_ANIO_MIN_04G1A,
    FRACCION_DIAS_USABLES_TOTAL_MIN_04G1A,MIN_BASES_COMPLETE_DIA_04G1A,
    ML_PERMITIDO_04G1A,PNL_PERMITIDO_04G1A,SELECCION_QUOTE_POR_PERFORMANCE_PERMITIDA_04G1A,
    STATUS_APTO_04G1A,STATUS_NO_APTO_04G1A,
)


def _months():
    out=[]; d=date(2021,12,1)
    while d<=date(2025,12,1):
        out.append(d); d=date(d.year+(d.month==12),1 if d.month==12 else d.month+1,1)
    return out


def _month_days(m):
    nxt=date(m.year+(m.month==12),1 if m.month==12 else m.month+1,1); out=[]; d=m
    while d<nxt: out.append(d); d+=timedelta(days=1)
    return out


def _dataset(active_bases=10):
    listings=[]; contents=[]
    for i,base in enumerate(BASES_04G1A):
        for quote in CORE_QUOTES_04G1A:
            active=i<active_bases; objs=[]
            if active:
                for month in _months():
                    objs.append(Obj04G1A(base,quote,f"{base}{quote}",month,"x.zip",100))
                    bars=[]
                    for d in _month_days(month):
                        buy=Decimal("60") if d.day%2 else Decimal("40")
                        close=Decimal("100")+Decimal((d-date(2021,12,1)).days)/Decimal("100")
                        bars.append(Bar04G1A(d,close,Decimal("100"),buy))
                    contents.append(Content04G1A(base,quote,month,tuple(bars),100,()))
            listings.append((base,quote,True,tuple(objs),None))
    return tuple(listings),tuple(contents)


def test_protocol_fixed_by_availability_not_performance():
    assert CORE_QUOTES_04G1A == ("USDT","EUR","BRL","TRY","UAH")
    assert MIN_BASES_COMPLETE_DIA_04G1A == 10
    assert FRACCION_DIAS_USABLES_TOTAL_MIN_04G1A == Decimal("0.95")
    assert FRACCION_DIAS_USABLES_POR_ANIO_MIN_04G1A == Decimal("0.90")
    assert SELECCION_QUOTE_POR_PERFORMANCE_PERMITIDA_04G1A is False
    assert ML_PERMITIDO_04G1A is False
    assert PNL_PERMITIDO_04G1A is False


def test_ten_complete_bases_pass_without_future_returns():
    listings,contents=_dataset(10)
    result=evaluar_matrix_04g1a(listings,contents)
    assert result["status"]==STATUS_APTO_04G1A
    assert result["complete_bases_min"]==10
    assert result["usable_days_fraction"]==1.0
    assert result["future_return_calculated"] is False
    assert result["ml_trained"] is False
    assert result["pnl_calculated"] is False


def test_nine_complete_bases_fail_closed():
    listings,contents=_dataset(9)
    result=evaluar_matrix_04g1a(listings,contents)
    assert result["status"]==STATUS_NO_APTO_04G1A
    assert result["complete_bases_max"]==9
    assert "USABLE_DAYS_TOTAL_BELOW_GATE" in result["reasons"]
