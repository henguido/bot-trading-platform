"""
Reconstruccion determinista del estado de riesgo desde las TRANSACCIONES.

FUENTE DE VERDAD: la tabla `transacciones`. No existe ninguna tabla derivada de
riesgo, a proposito. P&L realizado, exposicion y bloqueo se recalculan cada vez
a partir de operaciones confirmadas, de modo que:

  - no puede haber dos fuentes de verdad inconsistentes;
  - reiniciar el proceso no altera el resultado;
  - el cambio de dia no depende de ningun booleano en memoria.

METODO DE COSTE: promedio ponderado, el mismo que ya usaba
cargar_estado_portafolio. No se introduce FIFO ni LIFO.

    compra  ->  coste_medio = (qty*coste_medio + cant*precio) / (qty + cant)
                qty += cant
    venta   ->  pnl_realizado += (precio - coste_medio) * cant
                qty -= cant
                el coste medio NO cambia en una venta parcial

LIMITACION DECLARADA: las transacciones no registran comisiones, asi que el
P&L calculado es BRUTO. Con fees el resultado real es algo peor, lo que hace
que el limite de perdida diaria sea ligeramente optimista.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict

from backend.app import models
from backend.app.database import SessionLocal
from backend.risk import reloj


@dataclass(frozen=True)
class Posicion:
    cantidad: float = 0.0          # activo base
    coste_medio: float = 0.0       # USDT por unidad de base

    @property
    def exposicion_coste(self) -> float:
        """Capital desplegado en esta posicion, valorado a coste. Unidad: USDT."""
        return self.cantidad * self.coste_medio


@dataclass(frozen=True)
class EstadoRiesgo:
    dia: date
    posiciones: Dict[str, Posicion] = field(default_factory=dict)
    pnl_realizado_dia: float = 0.0     # USDT, negativo = perdida
    operaciones_dia: int = 0
    # Ordenes cuya situacion no conocemos con certeza (P0-14). Mientras haya
    # alguna, no se puede abrir nueva exposicion: podriamos tener posiciones
    # reales que el ledger local desconoce.
    ordenes_pendientes: int = 0

    @property
    def exposicion_total(self) -> float:
        return sum(p.exposicion_coste for p in self.posiciones.values())

    def exposicion_de(self, symbol: str) -> float:
        pos = self.posiciones.get(symbol)
        return pos.exposicion_coste if pos else 0.0

    def cantidad_disponible(self, symbol: str) -> float:
        pos = self.posiciones.get(symbol)
        return pos.cantidad if pos else 0.0


def _transacciones_del_usuario(db, usuario_id):
    portafolio = (
        db.query(models.Portfolio)
        .filter_by(usuario_id=usuario_id, tipo_activo="crypto")
        .first()
    )
    if not portafolio:
        return []
    return (
        db.query(models.Transaction)
        .filter_by(portafolio_id=portafolio.id)
        .order_by(models.Transaction.fecha_operacion.asc(),
                  models.Transaction.id.asc())
        .all()
    )


@dataclass(frozen=True)
class OperacionConfirmada:
    """Registro normalizado. Unico formato que entiende el reconstructor."""
    symbol: str
    es_compra: bool
    cantidad: float      # activo base
    precio: float        # USDT por unidad de base
    momento_utc: object  # datetime naive en UTC


def reconstruir(operaciones, dia) -> EstadoRiesgo:
    """
    Nucleo determinista. Recorre TODAS las operaciones en orden para mantener el
    coste medio, pero solo acumula P&L y contador de las que caen en `dia`.
    """
    inicio, fin = reloj.ventana_utc(dia)
    posiciones: Dict[str, dict] = {}
    pnl_dia = 0.0
    operaciones_dia = 0

    for op in operaciones:
        pos = posiciones.setdefault(op.symbol, {"cantidad": 0.0, "coste_medio": 0.0})
        en_el_dia = op.momento_utc is not None and inicio <= op.momento_utc < fin

        if op.es_compra:
            nuevo_total = pos["cantidad"] + op.cantidad
            if nuevo_total > 0:
                pos["coste_medio"] = (
                    pos["cantidad"] * pos["coste_medio"] + op.cantidad * op.precio
                ) / nuevo_total
            pos["cantidad"] = nuevo_total
        else:
            vendida = min(op.cantidad, pos["cantidad"])   # nunca se abre corto
            if en_el_dia:
                pnl_dia += (op.precio - pos["coste_medio"]) * vendida
            pos["cantidad"] -= vendida
            if pos["cantidad"] <= 1e-12:
                pos["cantidad"] = 0.0
                pos["coste_medio"] = 0.0

        if en_el_dia:
            operaciones_dia += 1

    return EstadoRiesgo(
        dia=dia,
        posiciones={s: Posicion(cantidad=p["cantidad"], coste_medio=p["coste_medio"])
                    for s, p in posiciones.items()},
        pnl_realizado_dia=pnl_dia,
        operaciones_dia=operaciones_dia,
    )


def calcular_estado_riesgo(usuario_id, *, dia=None, session_factory=SessionLocal) -> EstadoRiesgo:
    """Estado de riesgo en LIVE: fuente de verdad = tabla `transacciones`."""
    dia = dia or reloj.dia_de_riesgo()
    if usuario_id is None:
        return EstadoRiesgo(dia=dia)

    operaciones = []
    pendientes = 0
    with session_factory() as db:
        from backend.app.services import ordenes_repo
        pendientes = len(ordenes_repo.ordenes_no_terminales(db, usuario_id))
        simbolos = {a.id: a.simbolo for a in db.query(models.Asset).all()}
        for tx in _transacciones_del_usuario(db, usuario_id):
            symbol = simbolos.get(tx.activo_id)
            if symbol is None or tx.tipo_operacion not in ("Compra", "Venta"):
                continue
            operaciones.append(OperacionConfirmada(
                symbol=symbol,
                es_compra=(tx.tipo_operacion == "Compra"),
                cantidad=float(tx.cantidad or 0.0),
                precio=float(tx.precio or 0.0),
                momento_utc=tx.fecha_operacion,
            ))
    estado = reconstruir(operaciones, dia)
    return estado._replace(ordenes_pendientes=pendientes) \
        if hasattr(estado, "_replace") else _con_pendientes(estado, pendientes)


def _con_pendientes(estado, pendientes):
    return EstadoRiesgo(dia=estado.dia, posiciones=estado.posiciones,
                        pnl_realizado_dia=estado.pnl_realizado_dia,
                        operaciones_dia=estado.operaciones_dia,
                        ordenes_pendientes=pendientes)


def calcular_estado_riesgo_paper(simulador, *, dia=None) -> EstadoRiesgo:
    """
    Estado de riesgo en PAPER: fuente de verdad = historial del Simulator.

    En PAPER las operaciones no se persisten, asi que el libro en memoria es la
    unica fuente coherente. No se mezcla con la BD: una posicion simulada nunca
    autoriza una venta real, ni al reves.
    """
    dia = dia or reloj.dia_de_riesgo()
    zona = reloj.zona_riesgo()
    operaciones = []

    for entrada in getattr(simulador, "history", []):
        accion = entrada.get("action")
        if accion not in ("COMPRA", "VENTA"):
            continue
        momento = entrada.get("timestamp")
        if isinstance(momento, str):
            # El simulador sella con datetime.now() local; se normaliza a UTC.
            try:
                local = datetime.strptime(momento, "%Y-%m-%d %H:%M:%S")
                momento = zona.localize(local).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                momento = None
        operaciones.append(OperacionConfirmada(
            symbol=entrada.get("symbol"),
            es_compra=(accion == "COMPRA"),
            cantidad=float(entrada.get("quantity") or 0.0),
            precio=float(entrada.get("price") or 0.0),
            momento_utc=momento,
        ))
    return reconstruir(operaciones, dia)
