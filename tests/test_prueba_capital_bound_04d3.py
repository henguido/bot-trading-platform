from decimal import Decimal

from backend.economia.prueba_capital_bound_04d3 import demostrar_cota_04d3
from backend.economia.protocolo_capital_bound_04d3 import VEREDICTO_04D3


def test_2022_no_puede_superar_gate_sin_leverage():
    result = demostrar_cota_04d3()
    assert result.retorno_notional_2022 == Decimal("0.012413")
    assert result.capital_minimo_multiple == Decimal("1")
    assert result.retorno_committed_maximo_2022 == Decimal("0.012413")
    assert result.gate_peor_anio == Decimal("0.02")
    assert result.gate_superable is False
    assert result.verdict == VEREDICTO_04D3
