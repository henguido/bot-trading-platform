"""Ejecuta BOT 2.0-04B-v23b: inventario de tamaños, sin descargar trades."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.economia.inventario_orderflow_v23b import evaluar_plan_v23b, listar_symbol_v23b
from backend.economia.protocolo_orderflow_v23b import (
    DESARROLLO_2026_ABIERTO_V23B,
    N_ARCHIVOS_OBJETIVO_V23B,
    N_FECHAS_OBJETIVO_V23B,
    PRESUPUESTO_CI_GIB_V23B,
    UNIVERSO_V23B,
    USA_CONTENIDO_TRADES_V23B,
    USA_RETORNOS_V23B,
)

ARTEFACTO = Path("artifacts/orderflow-transfer-plan-v23b-2022-2025.json")


def main() -> int:
    print(
        f"[04B-v23b] start symbols={len(UNIVERSO_V23B)} dates={N_FECHAS_OBJETIVO_V23B} "
        f"files={N_ARCHIVOS_OBJETIVO_V23B} budget={PRESUPUESTO_CI_GIB_V23B}GiB "
        f"returns={USA_RETORNOS_V23B} content={USA_CONTENIDO_TRADES_V23B} "
        f"2026_OPEN={DESARROLLO_2026_ABIERTO_V23B}"
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        listados = tuple(pool.map(listar_symbol_v23b, UNIVERSO_V23B))

    resultado = evaluar_plan_v23b(listados)
    payload = {
        "resultado": resultado.resultado,
        "apto": resultado.apto,
        "entra_ci": resultado.entra_ci,
        "listados_completos": resultado.listados_completos,
        "listados_total": len(UNIVERSO_V23B),
        "archivos_presentes": resultado.archivos_presentes,
        "archivos_objetivo": resultado.archivos_objetivo,
        "fraccion_archivos": str(resultado.fraccion_archivos),
        "fechas_aptas": resultado.fechas_aptas,
        "fechas_objetivo": resultado.fechas_objetivo,
        "fraccion_fechas_aptas": str(resultado.fraccion_fechas_aptas),
        "minimo_simbolos_fecha": resultado.minimo_simbolos_fecha,
        "maximo_simbolos_fecha": resultado.maximo_simbolos_fecha,
        "bytes_total": resultado.bytes_total,
        "gib_total": str(resultado.gib_total),
        "presupuesto_ci_gib": PRESUPUESTO_CI_GIB_V23B,
        "archivos_duplicados": resultado.archivos_duplicados,
        "archivos_tamano_cero": resultado.archivos_tamano_cero,
        "motivos_rechazo": list(resultado.motivos_rechazo),
        "faltantes": list(resultado.faltantes),
        "simbolos_por_fecha": [
            {"fecha": fecha, "simbolos": n} for fecha, n in resultado.simbolos_por_fecha
        ],
        "listados": [
            {
                "symbol": l.symbol,
                "completa": l.completa,
                "n_requests": l.n_requests,
                "n_archivos_objetivo_encontrados": len(l.archivos),
                "error": l.error,
            }
            for l in listados
        ],
    }
    ARTEFACTO.parent.mkdir(parents=True, exist_ok=True)
    ARTEFACTO.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[04B-v23b] {resultado.resultado}: listings={resultado.listados_completos}/{len(UNIVERSO_V23B)} "
        f"files={resultado.archivos_presentes}/{resultado.archivos_objetivo} "
        f"dates={resultado.fechas_aptas}/{resultado.fechas_objetivo} "
        f"symbols/date={resultado.minimo_simbolos_fecha}-{resultado.maximo_simbolos_fecha} "
        f"size={resultado.gib_total:.6f}GiB enters_ci={resultado.entra_ci}"
    )
    print(
        "[04B-v23b] reject_reasons="
        + (",".join(resultado.motivos_rechazo) if resultado.motivos_rechazo else "ninguno")
    )
    return 0 if resultado.apto else 1


if __name__ == "__main__":
    raise SystemExit(main())
