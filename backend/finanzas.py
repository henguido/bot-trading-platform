"""
Presentacion honesta de cifras financieras  (Fase 6).

INVARIANTE: desconocido != 0.0

Un endpoint que devuelve `"pnl": 0.0` cuando en realidad no sabe el P&L esta
mintiendo, y ademas de forma indistinguible de un P&L que de verdad vale cero.
Aqui se separan los dos casos:

    {"pnl": 0.0,  "pnl_status": "DISPONIBLE"}     -> el P&L es cero de verdad
    {"pnl": null, "pnl_status": "NO_DISPONIBLE"}  -> no tenemos como calcularlo

FUENTES POR MODO — nunca se mezclan:

    dato            PAPER                       LIVE
    ---------------------------------------------------------------------
    cantidad        libro del Simulator         saldo del exchange
    precio medio    posicion del Simulator      transacciones reconciliadas
    P&L             derivado del medio PAPER    derivado del medio LIVE
"""
from __future__ import annotations

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"


def dato(valor, *, motivo=None):
    """
    Normaliza un valor numerico a la representacion tipada.

    `None` (o no finito) se presenta como NO_DISPONIBLE, nunca como 0.0.
    """
    if valor is None:
        return None, NO_DISPONIBLE, motivo
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None, NO_DISPONIBLE, motivo or "valor no numerico"
    if numero != numero or numero in (float("inf"), float("-inf")):
        return None, NO_DISPONIBLE, motivo or "valor no finito"
    return numero, DISPONIBLE, None


def campos(nombre, valor, *, motivo=None, redondeo=None):
    """
    Devuelve {nombre: valor, nombre_status: ...} y, si procede, nombre_motivo.

    Se usan campos planos con sufijo _status para no mezclar numeros y cadenas
    en el mismo campo, que es lo que hacia el frontend antiguo.
    """
    numero, estado, razon = dato(valor, motivo=motivo)
    if numero is not None and redondeo is not None:
        numero = round(numero, redondeo)
    salida = {nombre: numero, f"{nombre}_status": estado}
    if razon:
        salida[f"{nombre}_motivo"] = razon
    return salida


def precio_medio_de(estado_posiciones, symbol):
    """
    Precio medio de una posicion, o None si no lo conocemos.

    Un precio medio de 0.0 NO es un precio: significa que no hay posicion
    registrada o que el coste base se desconoce. Se devuelve None para que el
    llamador lo presente como NO_DISPONIBLE.
    """
    posicion = (estado_posiciones or {}).get(symbol)
    if not posicion:
        return None
    medio = posicion.get("precio_promedio") if isinstance(posicion, dict) else None
    if medio is None:
        return None
    try:
        medio = float(medio)
    except (TypeError, ValueError):
        return None
    return medio if medio > 0 else None


def pnl_no_realizado(precio_actual, precio_medio, cantidad):
    """
    P&L no realizado, o None si falta cualquiera de los ingredientes.

    Sin precio medio no hay coste base, y sin coste base NO hay P&L: no es cero.
    """
    if precio_actual is None or precio_medio is None or cantidad is None:
        return None
    try:
        return (float(precio_actual) - float(precio_medio)) * float(cantidad)
    except (TypeError, ValueError):
        return None
