import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import EconomicReadinessCard from "../components/EconomicReadinessCard";
import BalanceChart from "./BalanceChart";
import { getPaperReadiness, getResumen } from "../services/api";

const toneForNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "text-slate-300";
  if (Number(value) > 0) return "text-emerald-400";
  if (Number(value) < 0) return "text-rose-400";
  return "text-slate-200";
};

function StatusPill({ ok, children }) {
  return (
    <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${
      ok
        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
        : "border-amber-500/30 bg-amber-500/10 text-amber-300"
    }`}>
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-400" : "bg-amber-400"}`} />
      {children}
    </span>
  );
}

function MetricCard({ label, value, caption, tone = "text-white" }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 shadow-lg shadow-black/10">
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tracking-tight ${tone}`}>{value}</p>
      <p className="mt-1 text-xs text-slate-500">{caption}</p>
    </div>
  );
}

function DashboardPage() {
  const navigate = useNavigate();
  const [balanceUSDT, setBalanceUSDT] = useState(null);
  const [balances, setBalances] = useState([]);
  const [estrategias, setEstrategias] = useState([]);
  const [totalUSD, setTotalUSD] = useState(null);
  const [operativo, setOperativo] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [cargando, setCargando] = useState(true);
  const [readiness, setReadiness] = useState(null);
  const [readinessError, setReadinessError] = useState("");
  const [readinessLoading, setReadinessLoading] = useState(true);
  const [meta, setMeta] = useState({
    modo: "",
    pnlRealizado: null,
    pnlTotal: null,
    pnlTotalStatus: "NO_DISPONIBLE",
    pnlTotalNetoLiquidacion: false,
    fees: null,
    operaciones: 0,
    posiciones: 0,
  });

  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    if (!storedToken) {
      navigate("/login");
      return;
    }

    setCargando(true);
    getResumen()
      .then((data) => {
        if (!Array.isArray(data.resumen)) {
          throw new Error("Respuesta inválida del backend");
        }

        const usdt = data.resumen.find((b) => b.symbol === "USDT");
        setBalanceUSDT(usdt ? Number(usdt.cantidad) : 0);
        setBalances(data.resumen.map((b) => ({
          asset: b.symbol === "USDT" ? "USDT" : b.symbol.replace("USDT", ""),
          symbol: b.symbol,
          free: Number(b.cantidad),
          price_usdt: b.precio_actual,
          total_usd: b.valor_actual,
          average_price: b.average_price,
          average_price_status: b.average_price_status,
          pnl: b.pnl,
          pnl_status: b.pnl_status,
          pnl_metodologia: b.pnl_metodologia,
        })));

        const porEstrategia = data.estrategias_paper?.estrategias;
        const filasEstrategia = porEstrategia && typeof porEstrategia === "object"
          ? Object.entries(porEstrategia)
              .map(([nombre, fila]) => ({ nombre, ...fila }))
              .sort((a, b) => Number(b.pnl_realizado_neto_usd || 0) - Number(a.pnl_realizado_neto_usd || 0))
          : [];
        setEstrategias(filasEstrategia);
        setOperativo(data.estado_operativo || null);
        setTotalUSD(data.valor_total_usd);
        setMeta({
          modo: data.modo || "",
          pnlRealizado: data.pnl_realizado_usd ?? null,
          pnlTotal: data.pnl_total ?? null,
          pnlTotalStatus: data.pnl_total_status || "NO_DISPONIBLE",
          pnlTotalNetoLiquidacion: Boolean(data.pnl_total_es_neto_liquidacion),
          fees: data.fees_total_usd ?? null,
          operaciones: data.operaciones ?? 0,
          posiciones: data.posiciones_abiertas ?? 0,
        });
        setErrorMsg("");
      })
      .catch((err) => {
        if (err.status === 401) {
          navigate("/login");
          return;
        }
        setBalanceUSDT(null);
        setTotalUSD(null);
        setBalances([]);
        setEstrategias([]);
        setOperativo(null);
        setErrorMsg(err.message || "No se pudo cargar el resumen");
      })
      .finally(() => setCargando(false));
  }, [navigate]);

  useEffect(() => {
    let activo = true;
    setReadinessLoading(true);

    getPaperReadiness()
      .then((data) => {
        if (!activo) return;
        if (!data || typeof data !== "object" || !data.fee) {
          throw new Error("Respuesta de readiness inválida");
        }
        setReadiness(data);
        setReadinessError("");
      })
      .catch((err) => {
        if (!activo) return;
        if (err.status === 401) {
          navigate("/login");
          return;
        }
        setReadiness(null);
        setReadinessError(err.message || "No se pudo verificar el readiness económico");
      })
      .finally(() => {
        if (activo) setReadinessLoading(false);
      });

    return () => {
      activo = false;
    };
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user_name");
    navigate("/login");
  };

  const usd = (valor) => {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return "—";
    return `$${Number(valor).toFixed(2)}`;
  };

  const numero = (valor, decimales = 4) => {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return "—";
    return Number(valor).toLocaleString(undefined, { maximumFractionDigits: decimales });
  };

  const bps = (valor) => {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return "—";
    return `${Number(valor).toFixed(1)} bps`;
  };

  const porcentaje = (valor, yaEsPct = false) => {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return "—";
    const n = yaEsPct ? Number(valor) : Number(valor) * 100;
    return `${n.toFixed(1)}%`;
  };

  const posiciones = useMemo(
    () => balances.filter((b) => b.asset !== "USDT" && Number(b.free) > 0),
    [balances],
  );

  const deployedPct = operativo?.capital_desplegado_pct ?? 0;
  const deployedBar = Math.max(0, Math.min(100, Number(deployedPct) || 0));
  const usuario = localStorage.getItem("user_name") || "Operador";
  const limites = operativo?.limites_riesgo;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/95">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 font-bold text-cyan-300">
                BT
              </div>
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-white">BOT Trading Platform</h1>
                <p className="text-sm text-slate-500">Consola operativa y economía PAPER</p>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <StatusPill ok={meta.modo === "PAPER"}>MODO {meta.modo || "—"}</StatusPill>
            {operativo && (
              <StatusPill ok={operativo.decision_engine_status !== "OBSERVACION_SIN_COMPRAS"}>
                {operativo.decision_engine}
              </StatusPill>
            )}
            <button
              onClick={() => navigate("/observabilidad")}
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-300 transition hover:border-cyan-500/40 hover:text-cyan-300"
            >
              Observabilidad
            </button>
            <button
              onClick={() => navigate("/historial")}
              className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-500/10"
            >
              Journal
            </button>
            <div className="ml-0 flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 lg:ml-2">
              <div className="text-right">
                <p className="text-xs text-slate-500">Sesión</p>
                <p className="text-sm font-medium text-slate-200">{usuario}</p>
              </div>
              <button
                onClick={handleLogout}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:border-rose-500/50 hover:bg-rose-500/10 hover:text-rose-300"
              >
                Salir
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {errorMsg && (
          <div className="mb-5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            {errorMsg}
          </div>
        )}

        {cargando ? (
          <div className="grid min-h-[360px] place-items-center rounded-2xl border border-slate-800 bg-slate-900/50">
            <div className="text-center">
              <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-slate-700 border-t-cyan-400" />
              <p className="mt-3 text-sm text-slate-500">Cargando estado PAPER…</p>
            </div>
          </div>
        ) : (
          <>
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Valor del portafolio"
                value={usd(totalUSD)}
                caption={operativo ? `Capital inicial ${usd(operativo.capital_inicial_usd)}` : "Mark-to-market actual"}
              />
              <MetricCard
                label="Capital disponible"
                value={usd(balanceUSDT)}
                caption="USDT libre en el ledger PAPER"
              />
              <MetricCard
                label="Capital desplegado"
                value={usd(operativo?.capital_desplegado_usd)}
                caption={`${porcentaje(operativo?.capital_desplegado_pct, true)} del capital inicial`}
              />
              <MetricCard
                label="P&L realizado"
                value={usd(meta.pnlRealizado)}
                caption={`Retorno ${porcentaje(operativo?.retorno_realizado_pct, true)} · neto de fills`}
                tone={toneForNumber(meta.pnlRealizado)}
              />
            </section>

            <section className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-5">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 lg:col-span-2">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Motor de decisión</p>
                    <p className="mt-2 text-lg font-semibold text-white">{operativo?.decision_engine || "—"}</p>
                    <p className="mt-1 max-w-xl text-sm leading-6 text-slate-400">
                      {operativo?.decision_engine_description || "Estado del motor no disponible."}
                    </p>
                  </div>
                  <StatusPill ok={operativo?.decision_engine_status !== "OBSERVACION_SIN_COMPRAS"}>
                    {operativo?.decision_engine_status === "OBSERVACION_SIN_COMPRAS" ? "Observación" : "Operativo"}
                  </StatusPill>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Gate de rentabilidad</p>
                <div className="mt-3">
                  <StatusPill ok={Boolean(operativo?.profitability_gate_05e_enabled)}>
                    {operativo?.profitability_gate_05e_enabled ? "05E activo" : "05E apagado"}
                  </StatusPill>
                </div>
                <p className="mt-3 text-xs leading-5 text-slate-500">
                  {operativo?.profitability_gate_05e_enabled
                    ? "Filtro promovido y activo en PAPER."
                    : "Apagado por seguridad: evidencia OOS insuficiente para promoverlo."}
                </p>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Ejecución PAPER</p>
                <p className="mt-2 text-sm font-semibold text-slate-200">Order book + VWAP</p>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Slippage se modela con datos disponibles; fee taker solo con fuente verificable. Desconocido ≠ 0. LIVE deshabilitado.
                </p>
              </div>

              <EconomicReadinessCard
                readiness={readiness}
                loading={readinessLoading}
                error={readinessError}
              />
            </section>

            {operativo?.mensajes?.length > 0 && (
              <section className="mt-4 grid gap-2">
                {operativo.mensajes.map((mensaje) => (
                  <div key={mensaje} className="flex gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-100/80">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                    <span>{mensaje}</span>
                  </div>
                ))}
              </section>
            )}

            {limites && (
              <section className="mt-4 overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">
                <div className="border-b border-slate-800 px-5 py-3">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm font-medium text-slate-300">Límites de riesgo vigentes</p>
                    <p className="text-xs text-slate-600">Día de riesgo: {limites.timezone_dia_riesgo}</p>
                  </div>
                </div>
                <div className="grid gap-px bg-slate-800 sm:grid-cols-2 xl:grid-cols-5">
                  <div className="bg-slate-950/70 px-5 py-4">
                    <p className="text-xs text-slate-600">Asignación / operación</p>
                    <p className="mt-1 font-semibold text-slate-200">{porcentaje(limites.asignacion_maxima_por_operacion_pct, true)}</p>
                  </div>
                  <div className="bg-slate-950/70 px-5 py-4">
                    <p className="text-xs text-slate-600">Tope / operación</p>
                    <p className="mt-1 font-semibold text-slate-200">{usd(limites.monto_maximo_por_operacion_usd)}</p>
                  </div>
                  <div className="bg-slate-950/70 px-5 py-4">
                    <p className="text-xs text-slate-600">Pérdida diaria máxima</p>
                    <p className="mt-1 font-semibold text-rose-300">{usd(limites.perdida_realizada_diaria_maxima_usd)}</p>
                  </div>
                  <div className="bg-slate-950/70 px-5 py-4">
                    <p className="text-xs text-slate-600">Exposición total máxima</p>
                    <p className="mt-1 font-semibold text-slate-200">{usd(limites.exposicion_total_maxima_usd)}</p>
                  </div>
                  <div className="bg-slate-950/70 px-5 py-4">
                    <p className="text-xs text-slate-600">Exposición / activo</p>
                    <p className="mt-1 font-semibold text-slate-200">{usd(limites.exposicion_por_activo_maxima_usd)}</p>
                  </div>
                </div>
              </section>
            )}

            <section className="mt-6 grid gap-6 lg:grid-cols-3">
              <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70 lg:col-span-2">
                <div className="flex flex-col gap-3 border-b border-slate-800 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="font-semibold text-white">Posiciones y efectivo</h2>
                    <p className="mt-1 text-xs text-slate-500">Fuente: journal PAPER persistente</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-slate-500">Exposición sobre capital inicial</p>
                    <p className="text-sm font-semibold text-cyan-300">{porcentaje(deployedPct, true)}</p>
                  </div>
                </div>

                <div className="h-1 bg-slate-800">
                  <div className="h-full bg-cyan-400 transition-all" style={{ width: `${deployedBar}%` }} />
                </div>

                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-950/40 text-xs uppercase tracking-wider text-slate-500">
                      <tr>
                        <th className="px-5 py-3 text-left font-medium">Activo</th>
                        <th className="px-4 py-3 text-right font-medium">Cantidad</th>
                        <th className="px-4 py-3 text-right font-medium">Precio</th>
                        <th className="px-4 py-3 text-right font-medium">Coste medio</th>
                        <th className="px-4 py-3 text-right font-medium">Valor</th>
                        <th className="px-5 py-3 text-right font-medium">P&L abierto</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/80">
                      {balances.map((b) => (
                        <tr key={b.symbol} className="transition hover:bg-slate-800/30">
                          <td className="px-5 py-4">
                            <div className="flex items-center gap-3">
                              <span className={`flex h-8 w-8 items-center justify-center rounded-lg text-xs font-bold ${
                                b.asset === "USDT" ? "bg-emerald-500/10 text-emerald-300" : "bg-cyan-500/10 text-cyan-300"
                              }`}>
                                {b.asset.slice(0, 3)}
                              </span>
                              <div>
                                <p className="font-medium text-slate-200">{b.asset}</p>
                                <p className="text-xs text-slate-600">{b.asset === "USDT" ? "Efectivo" : b.symbol}</p>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-4 text-right tabular-nums text-slate-300">{numero(b.free, 6)}</td>
                          <td className="px-4 py-4 text-right tabular-nums text-slate-300">{usd(b.price_usdt)}</td>
                          <td className="px-4 py-4 text-right tabular-nums text-slate-400">
                            {b.average_price_status === "DISPONIBLE" ? usd(b.average_price) : "—"}
                          </td>
                          <td className="px-4 py-4 text-right font-medium tabular-nums text-slate-200">{usd(b.total_usd)}</td>
                          <td className={`px-5 py-4 text-right font-semibold tabular-nums ${
                            b.pnl_status === "DISPONIBLE" ? toneForNumber(b.pnl) : "text-slate-600"
                          }`}>
                            {b.pnl_status === "DISPONIBLE" ? usd(b.pnl) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {meta.posiciones > 0 && (
                  <div className="border-t border-slate-800 px-5 py-3 text-xs leading-5 text-slate-500">
                    P&L abierto = mark-to-market con coste de entrada ejecutado; todavía no descuenta una salida hipotética. El P&L realizado sí usa fills y fees persistidos.
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="font-semibold text-white">Distribución</h2>
                    <p className="mt-1 text-xs text-slate-500">Valor actual del portafolio</p>
                  </div>
                  <StatusPill ok={Boolean(operativo?.valoracion_completa)}>
                    {operativo?.valoracion_completa ? "Completa" : "Parcial"}
                  </StatusPill>
                </div>
                <BalanceChart data={balances} />
                <div className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-800 pt-4">
                  <div>
                    <p className="text-xs text-slate-500">Operaciones</p>
                    <p className="mt-1 text-lg font-semibold text-slate-200">{meta.operaciones}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Fees acumuladas</p>
                    <p className="mt-1 text-lg font-semibold text-slate-200">{usd(meta.fees)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Posiciones</p>
                    <p className="mt-1 text-lg font-semibold text-slate-200">{posiciones.length}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">P&L total</p>
                    <p className={`mt-1 text-lg font-semibold ${toneForNumber(meta.pnlTotal)}`}>
                      {meta.pnlTotalStatus === "DISPONIBLE" ? usd(meta.pnlTotal) : "—"}
                    </p>
                  </div>
                </div>
              </div>
            </section>

            <section className="mt-6 overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70">
              <div className="flex flex-col gap-2 border-b border-slate-800 px-5 py-4 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <h2 className="font-semibold text-white">Rendimiento por estrategia</h2>
                  <p className="mt-1 text-xs text-slate-500">Atribución FIFO por estrategia de entrada · P&L neto de fees ejecutadas</p>
                </div>
                <p className="text-xs text-slate-600">Desconocido ≠ 0</p>
              </div>

              {estrategias.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-950/40 text-xs uppercase tracking-wider text-slate-500">
                      <tr>
                        <th className="px-5 py-3 text-left font-medium">Estrategia</th>
                        <th className="px-4 py-3 text-right font-medium">Cierres</th>
                        <th className="px-4 py-3 text-right font-medium">P&L neto</th>
                        <th className="px-4 py-3 text-right font-medium">Retorno</th>
                        <th className="px-4 py-3 text-right font-medium">Esperado</th>
                        <th className="px-4 py-3 text-right font-medium">Error</th>
                        <th className="px-4 py-3 text-right font-medium">Win rate</th>
                        <th className="px-5 py-3 text-right font-medium">Abierto</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/80">
                      {estrategias.map((e) => (
                        <tr key={e.nombre} className="transition hover:bg-slate-800/30">
                          <td className="px-5 py-4 font-medium text-slate-200">{e.nombre}</td>
                          <td className="px-4 py-4 text-right tabular-nums text-slate-400">{e.cierres ?? 0}</td>
                          <td className={`px-4 py-4 text-right font-semibold tabular-nums ${toneForNumber(e.pnl_realizado_neto_usd)}`}>
                            {usd(e.pnl_realizado_neto_usd)}
                          </td>
                          <td className="px-4 py-4 text-right tabular-nums text-slate-300">{bps(e.retorno_realizado_neto_bps)}</td>
                          <td className="px-4 py-4 text-right tabular-nums text-slate-400">{bps(e.expected_net_bps_ponderado)}</td>
                          <td className={`px-4 py-4 text-right tabular-nums ${toneForNumber(e.error_expected_vs_realizado_bps)}`}>
                            {bps(e.error_expected_vs_realizado_bps)}
                          </td>
                          <td className="px-4 py-4 text-right tabular-nums text-slate-300">{porcentaje(e.positive_rate)}</td>
                          <td className="px-5 py-4 text-right tabular-nums text-slate-400">{usd(e.coste_abierto_usd)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="px-5 py-10 text-center">
                  <p className="text-sm font-medium text-slate-300">Todavía no hay evidencia cerrada por estrategia</p>
                  <p className="mx-auto mt-2 max-w-xl text-xs leading-5 text-slate-500">
                    La consola mostrará P&L neto, retorno, error frente a lo esperado y win rate cuando existan ventas PAPER que cierren lotes atribuidos.
                  </p>
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}

export default DashboardPage;
