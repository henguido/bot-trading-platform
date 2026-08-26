"""Motor de decisión seleccionable para desacoplar el loop del proveedor LLM.

`GPT` conserva exactamente el comportamiento existente.
`SAFE_NO_TRADE` es un modo operativo de fallo seguro: no llama IA y devuelve
ESPERAR para cada activo. No es una estrategia rentable; existe para que el bot
pueda arrancar, observar y servir API aunque el proveedor IA no esté disponible.

Una estrategia determinista validada podrá añadirse aquí sin volver a acoplar
`backend.main` a un proveedor concreto.
"""
from __future__ import annotations

ENGINE_GPT = "GPT"
ENGINE_SAFE_NO_TRADE = "SAFE_NO_TRADE"
ENGINES_VALIDOS = (ENGINE_GPT, ENGINE_SAFE_NO_TRADE)


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
        return openai.analyze_multiple_assets(
            activos,
            usdt_disponible,
            sentimiento,
            noticias_str,
            portafolio_contexto,
            market_pairs_filtrados,
            ciclo=ciclo,
            ciclo_id=ciclo_id,
        )

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
