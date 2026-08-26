import { Fragment, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getHistorial } from "../services/api";

function HistorialPage() {
  const navigate = useNavigate();
  const [historial, setHistorial] = useState([]);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    setCargando(true);
    getHistorial()
      .then((data) => {
        if (Array.isArray(data)) {
          setHistorial(data);
          setError("");
        } else {
          setError("Error al obtener historial");
        }
      })
      .catch((err) => {
        if (err.status === 401) {
          navigate("/login");
          return;
        }
        setError(err.message || "Error de conexión con el backend");
      })
      .finally(() => setCargando(false));
  }, [navigate]);

  const metricas = useMemo(() => {
    const compras = historial.filter((x) => x.side === "BUY" || x.action === "COMPRAR").length;
    const ventas = historial.filter((x) => x.side === "SELL" || x.action === "VENDER").length;
    const fees = historial.reduce((acc, x) => {
      const n = Number(x.fee_usd);
      return Number.isFinite(n) ? acc + n : acc;
    }, 0);
    const slips = historial
      .map((x) => Number(x.slippage_bps))
      .filter((x) => Number.isFinite(x));
    return {
      compras,
      ventas,
      fees,
      slippageMedio: slips.length ? slips.reduce((a, b) => a + b, 0) / slips.length : null,
    };
  }, [historial]);

  const usd = (valor, decimales = 4) => {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return "—";
    return `$${Number(valor).toFixed(decimales)}`;
  };

  const numero = (valor, decimales = 6) => {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return "—";
    return Number(valor).toLocaleString(undefined, { maximumFractionDigits: decimales });
  };

  const bps = (valor) => {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return "—";
    return `${Number(valor).toFixed(2)} bps`;
  };

  const toggleExpand = (item, index) => {
    const id = item.paper_operation_id ?? index;
    setExpandedId((actual) => (actual === id ? null : id));
  };

  return (
    <div className="min-h-screen bg-slate-950 px-4 py-6 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-cyan-400">PAPER ledger</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-white">Journal de ejecuciones</h1>
            <p className="mt-1 text-sm text-slate-500">Fills persistidos, fricción ejecutada y contexto económico de cada operación.</p>
          </div>
          <button
            onClick={() => navigate("/dashboard")}
            className="self-start rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-cyan-500/40 hover:text-cyan-300 sm:self-auto"
          >
            Volver al dashboard
          </button>
        </div>

        {error && (
          <div className="mb-5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            {error}
          </div>
        )}

        <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <p className="text-xs uppercase tracking-[0.15em] text-slate-500">Fills registrados</p>
            <p className="mt-2 text-2xl font-semibold text-white">{historial.length}</p>
            <p className="mt-1 text-xs text-slate-600">Fuente: paper_operaciones</p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <p className="text-xs uppercase tracking-[0.15em] text-slate-500">Compras / ventas</p>
            <p className="mt-2 text-2xl font-semibold text-white">{metricas.compras} / {metricas.ventas}</p>
            <p className="mt-1 text-xs text-slate-600">Solo ejecuciones confirmadas PAPER</p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <p className="text-xs uppercase tracking-[0.15em] text-slate-500">Fees ejecutadas</p>
            <p className="mt-2 text-2xl font-semibold text-amber-300">{usd(metricas.fees)}</p>
            <p className="mt-1 text-xs text-slate-600">Suma de comisiones persistidas</p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <p className="text-xs uppercase tracking-[0.15em] text-slate-500">Slippage medio</p>
            <p className="mt-2 text-2xl font-semibold text-cyan-300">{bps(metricas.slippageMedio)}</p>
            <p className="mt-1 text-xs text-slate-600">Sobre fills con dato disponible</p>
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70">
          <div className="border-b border-slate-800 px-5 py-4">
            <h2 className="font-semibold text-white">Operaciones</h2>
            <p className="mt-1 text-xs text-slate-500">Selecciona una fila para ver referencia, notional, fee y expectativa económica.</p>
          </div>

          {cargando ? (
            <div className="grid h-56 place-items-center">
              <div className="text-center">
                <div className="mx-auto h-7 w-7 animate-spin rounded-full border-2 border-slate-700 border-t-cyan-400" />
                <p className="mt-3 text-sm text-slate-500">Cargando journal…</p>
              </div>
            </div>
          ) : historial.length === 0 && !error ? (
            <div className="px-5 py-14 text-center">
              <p className="text-sm font-medium text-slate-300">No hay fills PAPER registrados</p>
              <p className="mt-2 text-xs text-slate-500">Las decisiones o señales que no llegan a ejecución no aparecen aquí.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-950/40 text-xs uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-5 py-3 text-left font-medium">Fecha</th>
                    <th className="px-4 py-3 text-left font-medium">Activo</th>
                    <th className="px-4 py-3 text-left font-medium">Lado</th>
                    <th className="px-4 py-3 text-right font-medium">Cantidad</th>
                    <th className="px-4 py-3 text-right font-medium">Fill</th>
                    <th className="px-4 py-3 text-right font-medium">Fee</th>
                    <th className="px-4 py-3 text-right font-medium">Slippage</th>
                    <th className="px-5 py-3 text-left font-medium">Estrategia</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {historial.map((item, index) => {
                    const id = item.paper_operation_id ?? index;
                    const abierta = expandedId === id;
                    const compra = item.side === "BUY" || item.action === "COMPRAR";
                    return (
                      <Fragment key={id}>
                        <tr
                          onClick={() => toggleExpand(item, index)}
                          className={`cursor-pointer transition ${abierta ? "bg-slate-800/50" : "hover:bg-slate-800/30"}`}
                        >
                          <td className="whitespace-nowrap px-5 py-4 text-xs text-slate-400">{item.timestamp || "—"}</td>
                          <td className="px-4 py-4 font-medium text-slate-200">{item.symbol}</td>
                          <td className="px-4 py-4">
                            <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${
                              compra
                                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                                : "border-rose-500/30 bg-rose-500/10 text-rose-300"
                            }`}>
                              {compra ? "BUY" : "SELL"}
                            </span>
                          </td>
                          <td className="px-4 py-4 text-right tabular-nums text-slate-300">{numero(item.base_quantity ?? item.quantity)}</td>
                          <td className="px-4 py-4 text-right tabular-nums text-slate-200">{usd(item.fill_price ?? item.price, 6)}</td>
                          <td className="px-4 py-4 text-right tabular-nums text-amber-300/90">{usd(item.fee_usd, 6)}</td>
                          <td className="px-4 py-4 text-right tabular-nums text-slate-400">{bps(item.slippage_bps)}</td>
                          <td className="px-5 py-4 text-slate-300">{item.strategy || "Sin estrategia"}</td>
                        </tr>

                        {abierta && (
                          <tr className="bg-slate-950/35">
                            <td colSpan="8" className="px-5 py-5">
                              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
                                <div>
                                  <p className="text-xs text-slate-600">Precio referencia</p>
                                  <p className="mt-1 font-medium text-slate-300">{usd(item.reference_price, 6)}</p>
                                </div>
                                <div>
                                  <p className="text-xs text-slate-600">Quote bruto</p>
                                  <p className="mt-1 font-medium text-slate-300">{usd(item.quote_gross, 6)}</p>
                                </div>
                                <div>
                                  <p className="text-xs text-slate-600">Quote neto</p>
                                  <p className="mt-1 font-medium text-slate-300">{usd(item.quote_net, 6)}</p>
                                </div>
                                <div>
                                  <p className="text-xs text-slate-600">Fee taker</p>
                                  <p className="mt-1 font-medium text-slate-300">{bps(item.fee_taker_bps)}</p>
                                </div>
                                <div>
                                  <p className="text-xs text-slate-600">Edge esperado</p>
                                  <p className="mt-1 font-medium text-slate-300">{bps(item.expected_edge_bps)}</p>
                                </div>
                                <div>
                                  <p className="text-xs text-slate-600">Coste esperado</p>
                                  <p className="mt-1 font-medium text-slate-300">{bps(item.expected_cost_bps)}</p>
                                </div>
                                <div>
                                  <p className="text-xs text-slate-600">Neto esperado</p>
                                  <p className="mt-1 font-semibold text-cyan-300">{bps(item.expected_net_bps)}</p>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default HistorialPage;
