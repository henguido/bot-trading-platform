"""Motor de decisión seleccionable para desacoplar el loop del proveedor LLM.

`GPT` conserva el comportamiento de decisiones existente, pero cualquier campo
económico que intente devolver el LLM se elimina: el modelo no puede inventar
edge, costes ni rentabilidad esperada.

`SAFE_NO_TRADE` es un modo operativo de fallo seguro: no llama IA y devuelve
ESPERAR para cada activo. No es una estrategia rentable; existe para que el bot
pueda arrancar, observar y servir API aunque el proveedor IA no esté disponible.

Una estrategia determinista validada podrá añadirse aquí sin volver a acoplar
`backend.main` a un proveedor concreto. Solo esos motores de confianza podrán
adjuntar contexto económico para el journal PAPER.
"""
from __future__ import annotations

import math

ENGINE_GPT = "GPT"
ENGINE_SAFE_NO_TRADE = "SAFE_NO_TRADE"
ENGINES_VALIDOS = (ENGINE_GPT, ENGINE_SAFE_NO_TRADE)

CAMPOS_ECONOMICOS = (
    "strategy",
    "expected_edge_bps",
    "expected_cost_bps",
    "expected_net_bps",
)


def _sin_economia_no_confiable(resultados):
    """Copia resultados GPT quitando economía que el LLM no puede conocer."""
    salida = []
    for resultado in resultados or ():
        if not isinstance(resultado, dict):
            salida.append(resultado)
            continue
        limpio = dict(resultado)
        for campo in CAMPOS_ECONOMICOS:
            limpio.pop(campo, None)
        salida.append(limpio)
    return salida


def _numero_finito_o_none(valor, nombre):
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ValueError(f"{nombre} no puede ser booleano")
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nombre} no es numerico") from None
    if not math.isfinite(numero):
        raise ValueError(f"{nombre} debe ser finito")
    return numero


def contexto_economico_de(resultado: dict) -> dict:
    """Normaliza telemetría económica emitida por un motor determinista.

    Desconocido permanece ausente; nunca se convierte a cero. Esta función no
    calcula ni autoriza una operación y no participa en MotorRiesgo.
    """
    if not isinstance(resultado, dict):
        return {}

    estrategia = resultado.get("strategy")
    if estrategia is not None:
        if not isinstance(estrategia, str) or not estrategia.strip():
            raise ValueError("strategy debe ser texto no vacio")
        estrategia = estrategia.strip()

    edge = _numero_finito_o_none(resultado.get("expected_edge_bps"),
                                 "expected_edge_bps")
    coste = _numero_finito_o_none(resultado.get("expected_cost_bps"),
                                  "expected_cost_bps")
    neto = _numero_finito_o_none(resultado.get("expected_net_bps"),
                                 "expected_net_bps")

    salida = {}
    if estrategia is not None:
        salida["strategy"] = estrategia
    if edge is not None:
        salida["expected_edge_bps"] = edge
    if coste is not None:
        salida["expected_cost_bps"] = coste
    if neto is not None:
        salida["expected_net_bps"] = neto
    return salida


def contexto_economico_para_ejecucion(engine: str, resultado: dict) -> tuple[dict, str | None]:
    """Extrae economía confiable sin permitir que la telemetría altere trading.

    Defensa en profundidad:
    - GPT y SAFE_NO_TRADE nunca pueden aportar economía, aunque un resultado
      llegara a contener esos campos por una regresión futura.
    - un motor no registrado tampoco puede introducirla;
    - para un motor determinista registrado, los valores se normalizan y los
      desconocidos siguen ausentes;
    - si la telemetría económica es inválida, se devuelve `{}` + diagnóstico.
      Un error de observabilidad no cambia una decisión ya tomada ni el sizing
      de MotorRiesgo.

    Cuando se incorpore un motor determinista validado, bastará con declararlo
    en ENGINES_VALIDOS y hacer que `decidir` devuelva sus campos económicos.
    """
    motor = str(engine or "").strip().upper()
    if motor in (ENGINE_GPT, ENGINE_SAFE_NO_TRADE):
        return {}, None
    if motor not in ENGINES_VALIDOS:
        return {}, "MOTOR_ECONOMICO_NO_CONFIABLE"
    try:
        return contexto_economico_de(resultado), None
    except ValueError as exc:
        return {}, f"ECONOMIA_INVALIDA:{exc}"


def decidir(
    engine: str,
    *,
    openai,
    activos,
    usdt_disponible,
    sentimiento,
    noticias_str,
    portafolio_contexto,
    market_pairs_filtrados,
    ciclo,
    ciclo_id,
):
    """Devuelve `(resultados, explicacion)` con el contrato legacy del loop."""
    motor = str(engine or "").strip().upper()

    if motor == ENGINE_GPT:
        resultados, explicacion = openai.analyze_multiple_assets(
            activos,
            usdt_disponible,
            sentimiento,
            noticias_str,
            portafolio_contexto,
            market_pairs_filtrados,
            ciclo=ciclo,
            ciclo_id=ciclo_id,
        )
        return _sin_economia_no_confiable(resultados), explicacion

    if motor == ENGINE_SAFE_NO_TRADE:
        resultados = []
        for activo in activos or ():
            symbol = activo.get("symbol") if isinstance(activo, dict) else None
            if not symbol:
                continue
            resultados.append({
                "symbol": symbol,
                "decision": "ESPERAR",
                "quantity": 0.0,
                "risk_score": 0.0,
            })
        return resultados, "SAFE_NO_TRADE: IA omitida; compras nuevas bloqueadas."

    raise ValueError(f"DECISION_ENGINE no soportado: {engine!r}")