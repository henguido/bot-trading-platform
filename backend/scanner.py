"""
Scanner deterministico de candidatos  (Fase BOT 2.0-03B).

QUE HACE
    Reduce el universo de compras nuevas ANTES de gastar IA. Recibe los activos
    que el Eligibility Gate (03A) declaro ejecutables, descarta los
    evidentemente malos con filtros duros, puntua el resto y devuelve el Top N.

QUE NO HACE
    No decide COMPRAR ni VENDER. No dimensiona. No autoriza nada. Solo ORDENA y
    RECORTA candidatos. El MotorRiesgo sigue siendo la unica autoridad y vuelve
    a evaluar de cero cada decision. Nunca pregunta nada a un LLM.

DATOS: UNA SOLA PETICION
    Todo sale de `GET /api/v3/ticker/24hr` sin parametro `symbol`, que en
    python-binance 1.0.28 es `Client.get_ticker()`. Auditado en real: 3.684
    simbolos, ~1,9 MiB, ~400 ms, 1 peticion, cobertura 484/484 del universo y
    cero campos ausentes. Trae precio, bid, ask, volumen, quoteVolume, high,
    low, priceChangePercent y trade count.

    No se usan klines: `get_klines` solo acepta un simbolo, asi que RSI/ATR/
    medias costarian 484 peticiones (~107 s medidos) y reintroducirian el patron
    N+1 que 02B elimino. Fuera de esta fase.

UMBRALES JUSTIFICADOS, NO INVENTADOS
    Cada corte esta anclado a un percentil medido del universo real (484 pares
    crypto/USDT) y tiene un motivo economico. Ver DISTRIBUCION_MEDIDA.

VENTAS
    Este modulo solo filtra COMPRAS NUEVAS. Un activo con posicion abierta se
    conserva SIEMPRE, igual que en 03A: el bot no puede quedarse sin poder
    analizar -y por tanto vender- lo que ya tiene.

DETERMINISMO
    Para un mismo snapshot: mismo universo, mismos features, mismo score, mismo
    ranking. Sin IA, sin azar, sin dependencia del orden de llegada. El
    desempate es estable por `symbol`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

# ─────────────────────────────────────────────────────────────────────────────
# DISTRIBUCION MEDIDA DEL UNIVERSO REAL  (484 pares crypto/USDT, spot, TRADING)
#
#   spread (ask-bid)/mid   p5=1.0   p25=5.1   p50=10.3  p95=42.5  p99=83.7  max=377.4  bps
#   quoteVolume 24h USDT   p5=56k   p25=156k  p50=433k  p75=1,54M p99=61,1M
#   rango 24h (hi-lo)/lo   p5=1.64% p25=2.84% p50=4.11% p75=6.58% p99=31.6%
#   trade count 24h        p5=1091  p25=2712  p50=6831  p75=18262 p99=497k
#
# Los cortes se fijan en la COLA MALA de cada distribucion: quitan lo que es
# evidentemente inoperable sin recortar el universo util.
# ─────────────────────────────────────────────────────────────────────────────

# p95 del spread. A 50 bps, entrar y salir cuesta ~1% del notional: con un
# maximo autorizado de 10 USDT eso es friccion pura. Descarta 16/484 (3,3%).
SPREAD_MAXIMO_BPS = 50.0

# Por debajo de ~1 operacion cada 86 s el precio publicado no es un mercado
# vivo, es un residuo. Ancla: p5 = 1.091. Descarta 21/484 (4,3%).
TRADES_MINIMOS_24H = 1000

# No es una restriccion de liquidez -operamos 10 USDT contra mercados de cientos
# de miles-, es de CALIDAD DE DATO: por debajo de 100k USDT/24h los propios
# estadisticos de 24 h son ruido. Descarta 60/484 (12,4%).
QUOTE_VOLUME_MINIMO_USDT = 100_000.0

# Sin recorrido no hay nada que capturar, y menos aun cubriendo 50 bps de
# friccion. Ancla: p5 = 1,64%. Descarta 16/484 (3,3%), sobre todo stablecoins
# (TUSDUSDT 0,02%, UUSDT 0,03%, USDPUSDT).
RANGO_MINIMO_24H = 0.01

# ─────────────────────────────────────────────────────────────────────────────
# CODIGOS DE MOTIVO — estables y comparables; la logica se apoya en el CODIGO
# ─────────────────────────────────────────────────────────────────────────────
CANDIDATO = "CANDIDATO"
DATOS_INCOMPLETOS = "DATOS_INCOMPLETOS"
SPREAD_EXCESIVO = "SPREAD_EXCESIVO"
MERCADO_INACTIVO = "MERCADO_INACTIVO"
LIQUIDEZ_INSUFICIENTE = "LIQUIDEZ_INSUFICIENTE"
SIN_RECORRIDO = "SIN_RECORRIDO"
FUERA_DEL_TOP = "FUERA_DEL_TOP"
POSICION_ABIERTA = "POSICION_ABIERTA"

MOTIVOS = (CANDIDATO, DATOS_INCOMPLETOS, SPREAD_EXCESIVO, MERCADO_INACTIVO,
           LIQUIDEZ_INSUFICIENTE, SIN_RECORRIDO, FUERA_DEL_TOP, POSICION_ABIERTA)

# ─────────────────────────────────────────────────────────────────────────────
# PESOS DEL SCORE
#
# 🔶 SON UN PUNTO DE PARTIDA, NO UN MODELO VALIDADO. Todavia no hay backtesting
#    (fase posterior), asi que el reparto responde a cuanta CONFIANZA tenemos en
#    que cada feature mida algo economicamente real:
#
#      estrechez  la friccion es el unico coste que conocemos con certeza
#      recorrido  sin rango no hay nada que capturar
#      liquidez   proxy de fiabilidad del precio y de poder salir
#      actividad  proxy de descubrimiento de precio vivo
#      momentum   la senal mas debil que tenemos; peso minimo a proposito
#
#    El score solo ORDENA. No decide, no dimensiona y no autoriza.
# ─────────────────────────────────────────────────────────────────────────────
PESOS = {
    "estrechez": 0.25,
    "recorrido": 0.25,
    "liquidez": 0.25,
    "actividad": 0.15,
    "momentum": 0.10,
}

# Cuantos candidatos de COMPRA NUEVA se envian al LLM como maximo.
#
# ANCLADO A LA MEDICION, no elegido a ojo. Con 402 supervivientes medidos:
#   - el score p95 es 0,8269 y el candidato numero 20 puntua 0,8343, o sea
#     Top 20 == exactamente la cohorte >= p95. El corte cae en un limite
#     natural de la distribucion, no en un numero redondo cualquiera.
#   - coste medido: Top 10 -> 1.235 tokens, Top 20 -> 1.455, Top 30 -> 1.676.
#     El prompt fijo son ~1.018 tokens, asi que cada activo extra cuesta ~53:
#     pasar de 10 a 20 son +220 tokens y sigue siendo un 90,0% menos que los
#     14.521 de 02B. El argumento de coste no distingue entre 10 y 20.
#   - con MAX_EXPOSICION_TOTAL_USDT=100 y 10 USDT por operacion caben 10
#     posiciones simultaneas; 20 candidatos dan el doble de margen de eleccion.
#   - por debajo del Top 20 la dispersion se estrecha mucho (Top 5: spread
#     0,2-3,3 bps) y se pierde variedad para evaluar el ranking.
#
# NO es un limite de riesgo: el MotorRiesgo evalua cada operacion por separado.
TOP_N_POR_DEFECTO = 20


def _numero(valor) -> Optional[float]:
    """float finito, o None. Un dato ilegible es desconocido, no cero."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


@dataclass(frozen=True)
class MetricasMercado:
    """Features de UN simbolo, todas derivadas del mismo ticker/24hr."""
    symbol: str
    precio: float
    bid: float
    ask: float
    quote_volume: float
    trades: float
    rango: float                 # (high - low) / low
    cambio_pct: float            # priceChangePercent, con signo
    spread_bps: float            # (ask - bid) / mid * 10_000


def leer_metricas(symbol, fila) -> Optional[MetricasMercado]:
    """
    Convierte una fila de ticker/24hr en features utilizables.

    Devuelve None si falta o es ilegible algo imprescindible: sin datos no se
    puntua un candidato a la ligera (fail-closed para compra nueva).
    """
    if not isinstance(fila, dict):
        return None
    precio = _numero(fila.get("lastPrice"))
    bid = _numero(fila.get("bidPrice"))
    ask = _numero(fila.get("askPrice"))
    qv = _numero(fila.get("quoteVolume"))
    trades = _numero(fila.get("count"))
    hi = _numero(fila.get("highPrice"))
    lo = _numero(fila.get("lowPrice"))
    cambio = _numero(fila.get("priceChangePercent"))

    if None in (precio, bid, ask, qv, trades, hi, lo):
        return None
    if precio <= 0 or bid <= 0 or ask <= 0 or lo <= 0:
        return None
    if ask < bid or hi < lo or qv < 0 or trades < 0:
        return None

    medio = (bid + ask) / 2.0
    if medio <= 0:
        return None

    return MetricasMercado(
        symbol=symbol, precio=precio, bid=bid, ask=ask, quote_volume=qv,
        trades=trades, rango=(hi - lo) / lo,
        cambio_pct=cambio if cambio is not None else 0.0,
        spread_bps=(ask - bid) / medio * 10_000.0,
    )


def evaluar_filtros(metricas: Optional[MetricasMercado]) -> str:
    """
    Filtros duros. Devuelve `CANDIDATO` o el codigo del primer corte que falla.

    El orden va de mas objetivo a mas interpretable, para que el motivo nombre
    la causa mas evidente.
    """
    if metricas is None:
        return DATOS_INCOMPLETOS
    if metricas.spread_bps > SPREAD_MAXIMO_BPS:
        return SPREAD_EXCESIVO
    if metricas.trades < TRADES_MINIMOS_24H:
        return MERCADO_INACTIVO
    if metricas.quote_volume < QUOTE_VOLUME_MINIMO_USDT:
        return LIQUIDEZ_INSUFICIENTE
    if metricas.rango < RANGO_MINIMO_24H:
        return SIN_RECORRIDO
    return CANDIDATO


@dataclass(frozen=True)
class Candidato:
    """Un superviviente, con su score y el desglose que lo explica."""
    symbol: str
    score: float
    features: Dict[str, float]
    metricas: MetricasMercado

    def __str__(self) -> str:
        detalle = " ".join(f"{k}={v:.3f}" for k, v in sorted(self.features.items()))
        return (f"{self.symbol} score={self.score:.4f} [{detalle}] "
                f"spread={self.metricas.spread_bps:.1f}bps "
                f"qv={self.metricas.quote_volume:,.0f} "
                f"rango={self.metricas.rango*100:.2f}%")


def _percentiles(valores: Sequence[float]) -> List[float]:
    """
    Rango percentil de cada valor dentro de su propio conjunto, en [0, 1].

    Se usa rango y no min-max porque el universo tiene colas brutales -un spread
    de 377 bps frente a una mediana de 10- que aplastarian cualquier
    normalizacion lineal. Los empates reciben el MISMO percentil, asi que dos
    activos con el mismo dato puntuan igual: eso es lo que hace el ranking
    reproducible.
    """
    n = len(valores)
    if n == 0:
        return []
    if n == 1:
        return [0.5]
    ordenados = sorted(valores)
    # Posicion media de los iguales -> mismo percentil para valores iguales.
    posicion: Dict[float, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordenados[j + 1] == ordenados[i]:
            j += 1
        posicion[ordenados[i]] = (i + j) / 2.0 / (n - 1)
        i = j + 1
    return [posicion[v] for v in valores]


def puntuar(metricas: Sequence[MetricasMercado], *,
            pesos: Optional[Dict[str, float]] = None) -> List[Candidato]:
    """
    Puntua y ORDENA los supervivientes. Determinista y sin estado.

    El score es una suma ponderada de rangos percentiles, cada uno en [0, 1],
    asi que el total tambien cae en [0, 1] y es directamente comparable entre
    activos del MISMO ciclo. No es una probabilidad ni una prediccion.

    Orden: score descendente y, a igualdad, `symbol` ascendente. El desempate
    por symbol es lo que garantiza que dos ejecuciones con el mismo snapshot
    devuelvan exactamente la misma lista, independientemente del orden de
    llegada.
    """
    w = dict(PESOS if pesos is None else pesos)
    if not metricas:
        return []

    # Se ordena por symbol ANTES de calcular nada: asi los percentiles no
    # dependen del orden en que llegaron los activos.
    items = sorted(metricas, key=lambda m: m.symbol)

    p_liquidez = _percentiles([math.log10(max(m.quote_volume, 1.0)) for m in items])
    p_actividad = _percentiles([math.log10(max(m.trades, 1.0)) for m in items])
    p_recorrido = _percentiles([m.rango for m in items])
    p_momentum = _percentiles([m.cambio_pct for m in items])
    # Menos spread es mejor: se invierte el percentil.
    p_estrechez = [1.0 - p for p in _percentiles([m.spread_bps for m in items])]

    candidatos = []
    for i, m in enumerate(items):
        features = {
            "liquidez": p_liquidez[i],
            "actividad": p_actividad[i],
            "recorrido": p_recorrido[i],
            "momentum": p_momentum[i],
            "estrechez": p_estrechez[i],
        }
        score = sum(features[k] * w.get(k, 0.0) for k in features)
        candidatos.append(Candidato(symbol=m.symbol, score=score,
                                    features=features, metricas=m))

    candidatos.sort(key=lambda c: (-c.score, c.symbol))
    return candidatos


# ─────────────────────────────────────────────────────────────────────────────
# TELEMETRIA — minima y en memoria, sin persistencia ni migracion
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ResumenScanner:
    """Contadores del scanner en un ciclo. No influye en ninguna decision."""
    entrada: int = 0                 # elegibles BUY que llegan al scanner
    preservados: int = 0             # posiciones abiertas, nunca filtradas
    descartados: int = 0             # caidos por filtro duro
    puntuados: int = 0               # supervivientes que se puntuaron
    top_n: int = 0                   # N solicitado
    seleccionados: int = 0           # los que salen del Top
    por_motivo: Dict[str, int] = field(default_factory=dict)
    scores: List[float] = field(default_factory=list)

    def anotar(self, motivo: str) -> None:
        try:
            self.por_motivo[motivo] = self.por_motivo.get(motivo, 0) + 1
        except Exception:
            pass

    @property
    def enviados(self) -> int:
        return self.seleccionados + self.preservados

    def _distribucion(self) -> str:
        if not self.scores:
            return ""
        v = sorted(self.scores)
        n = len(v)
        return (f" scores[min={v[0]:.3f} p50={v[n // 2]:.3f} "
                f"max={v[-1]:.3f}]")

    def linea(self, duracion_ms=None, requests=None) -> str:
        try:
            desglose = " ".join(
                f"{m}={n}" for m, n in sorted(self.por_motivo.items(),
                                              key=lambda kv: (-kv[1], kv[0])))
            extra = ""
            if requests is not None:
                extra += f" | requests={requests}"
            if duracion_ms is not None:
                extra += f" | {duracion_ms} ms"
            return (f"[SCANNER] entrada={self.entrada} descartados={self.descartados} "
                    f"puntuados={self.puntuados} topN={self.top_n} "
                    f"seleccionados={self.seleccionados} "
                    f"preservados={self.preservados} -> a_GPT={self.enviados}"
                    f"{' | ' + desglose if desglose else ''}"
                    f"{self._distribucion()}{extra}")
        except Exception:
            return "[SCANNER] resumen no disponible"


# ─────────────────────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────
def aplicar(activos, metricas_por_symbol, *, top_n, resumen=None,
            pesos=None) -> list:
    """
    Recorta `activos` al Top N de candidatos de COMPRA, conservando posiciones.

    `activos` son los dicts que el bucle ya construyo para el prompt. Los que
    traen `_position_detected` se conservan SIEMPRE, sin puntuarlos: el scanner
    no puede dejar al bot sin poder analizar una salida.

    Devuelve una lista nueva; no muta la entrada. Si ningun candidato pasa los
    filtros duros, devuelve solo las posiciones abiertas -y si tampoco hay,
    devuelve lista vacia, con lo que el ciclo no llama al LLM. Eso es el
    comportamiento correcto, no un fallo: no se fuerza el Top N.
    """
    r = resumen if resumen is not None else ResumenScanner()
    r.top_n = int(top_n)

    preservados, aspirantes = [], []
    for a in activos or ():
        if a.get("_position_detected"):
            preservados.append(a)
        else:
            aspirantes.append(a)
    r.preservados = len(preservados)
    r.entrada = len(aspirantes)
    for _ in preservados:
        r.anotar(POSICION_ABIERTA)

    # ── Filtros duros ───────────────────────────────────────────────────────
    supervivientes, por_symbol = [], {}
    for a in aspirantes:
        sym = a.get("symbol")
        m = leer_metricas(sym, (metricas_por_symbol or {}).get(sym))
        motivo = evaluar_filtros(m)
        r.anotar(motivo)
        if motivo != CANDIDATO:
            r.descartados += 1
            continue
        supervivientes.append(m)
        por_symbol[sym] = a
    r.puntuados = len(supervivientes)

    # ── Score y recorte ─────────────────────────────────────────────────────
    ordenados = puntuar(supervivientes, pesos=pesos)
    try:
        r.scores = [c.score for c in ordenados]
    except Exception:
        pass

    # Si sobreviven menos que N se envian los que hay: nunca se rellena el Top
    # con activos que no pasaron los filtros.
    elegidos = ordenados[:max(0, int(top_n))]
    r.seleccionados = len(elegidos)
    for c in ordenados[len(elegidos):]:
        r.anotar(FUERA_DEL_TOP)

    salida = [por_symbol[c.symbol] for c in elegidos if c.symbol in por_symbol]
    # Las posiciones abiertas van primero: el prompt ya las prioriza y asi el
    # orden del scanner no altera esa precedencia.
    return preservados + salida
