from types import SimpleNamespace

from backend.app.services.ordenes import Lado
from backend.economia.pretrade import evaluar_pretrade
from backend.economia.rentabilidad import evaluar_desde_componentes
from backend.risk.motor import PropuestaOperacion


class MotorFake:
    def __init__(self):
        self.llamadas = 0

    def evaluar(self, propuesta, *, capital_disponible, estado):
        self.llamadas += 1
        return SimpleNamespace(
            aprobado=True,
            symbol=propuesta.symbol,
            side=propuesta.side,
            capital=capital_disponible,
            estado=estado,
        )


def rentable(apta=True):
    return evaluar_desde_componentes(
        edge_bruto_bps="40" if apta else "20",
        margen_neto_minimo_bps="10",
        notional_usd="100",
        spread_bps="4",
        fee_taker_bps_por_lado="5",
        slippage_bps_por_lado="2",
        exigir_costo_ia=False,
    )


def propuesta(lado):
    return PropuestaOperacion(
        symbol="BTCUSDT",
        side=lado,
        precio=50000.0,
        base_quantity_modelo=0.001,
        min_notional=1.0,
    )


def test_compra_sin_rentabilidad_no_llega_al_motor_riesgo():
    motor = MotorFake()
    r = evaluar_pretrade(
        propuesta=propuesta(Lado.COMPRA),
        rentabilidad=None,
        motor_riesgo=motor,
        capital_disponible=100.0,
        estado=object(),
    )
    assert r.bloqueada_por_rentabilidad is True
    assert r.motivo == "RENTABILIDAD_AUSENTE"
    assert r.llego_a_riesgo is False
    assert motor.llamadas == 0


def test_compra_no_rentable_no_llega_al_motor_riesgo():
    motor = MotorFake()
    evaluacion = rentable(apta=False)
    assert evaluacion.apta is False
    r = evaluar_pretrade(
        propuesta=propuesta(Lado.COMPRA),
        rentabilidad=evaluacion,
        motor_riesgo=motor,
        capital_disponible=100.0,
        estado=object(),
    )
    assert r.bloqueada_por_rentabilidad is True
    assert r.llego_a_riesgo is False
    assert motor.llamadas == 0


def test_compra_rentable_si_llega_al_motor_pero_riesgo_sigue_siendo_autoridad():
    motor = MotorFake()
    r = evaluar_pretrade(
        propuesta=propuesta(Lado.COMPRA),
        rentabilidad=rentable(apta=True),
        motor_riesgo=motor,
        capital_disponible=100.0,
        estado={"estado": "paper"},
    )
    assert r.bloqueada_por_rentabilidad is False
    assert r.llego_a_riesgo is True
    assert r.veredicto_riesgo.aprobado is True
    assert motor.llamadas == 1


def test_venta_no_se_bloquea_por_edge_desconocido():
    motor = MotorFake()
    r = evaluar_pretrade(
        propuesta=propuesta(Lado.VENTA),
        rentabilidad=None,
        motor_riesgo=motor,
        capital_disponible=100.0,
        estado={"posicion": "abierta"},
    )
    assert r.bloqueada_por_rentabilidad is False
    assert r.llego_a_riesgo is True
    assert motor.llamadas == 1
