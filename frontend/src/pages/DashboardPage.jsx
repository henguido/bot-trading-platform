import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import BalanceChart from "./BalanceChart";
import { getResumen } from "../services/api";

function DashboardPage() {
  const navigate = useNavigate();
  const [balanceUSDT, setBalanceUSDT] = useState("Cargando...");
  const [balances, setBalances] = useState([]);
  const [estrategias, setEstrategias] = useState([]);
  const [totalUSD, setTotalUSD] = useState("Cargando...");
  const [errorMsg, setErrorMsg] = useState("");
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

    getResumen()
      .then((data) => {
        if (!Array.isArray(data.resumen)) {
          throw new Error("Respuesta inválida del backend");
        }
        const usdt = data.resumen.find((b) => b.symbol.startsWith("USDT"));
        setBalanceUSDT(usdt ? usdt.cantidad : "0.00");
        setBalances(data.resumen.map((b) => ({
          asset: b.symbol === "USDT" ? "USDT" : b.symbol.replace("USDT", ""),
          free: b.cantidad,
          locked: 0,
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
          ? Object.entries(porEstrategia).map(([nombre, fila]) => ({
              nombre,
              ...fila,
            })).sort((a, b) => Number(b.pnl_realizado_neto_usd || 0) - Number(a.pnl_realizado_neto_usd || 0))
          : [];
        setEstrategias(filasEstrategia);
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
        setBalanceUSDT("Error");
        setTotalUSD("Error");
        setEstrategias([]);
        setErrorMsg(err.message || "No se pudo cargar el resumen");
      });
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user_name");
    navigate("/login");
  };

  const usd = (valor) => {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return "—";
    return Number(valor).toFixed(2);
  };

  const bps = (valor) => {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return "—";
    return `${Number(valor).toFixed(1)} bps`;
  };

  const porcentaje = (valor) => {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return "—";
    return `${(Number(valor) * 100).toFixed(1)}%`;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center p-4">
      <div className="bg-white shadow-xl rounded-xl p-8 w-full max-w-6xl text-center animate-fade-in">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <h1 className="text-3xl font-bold text-gray-800">
            👋 Bienvenido a BOT Trading Platform
          </h1>
          {meta.modo && (
            <span className={`self-center px-3 py-1 rounded-full text-xs font-bold tracking-wide ${
              meta.modo === "PAPER"
                ? "bg-amber-100 text-amber-800 border border-amber-300"
                : "bg-red-100 text-red-800 border border-red-300"
            }`}>
              MODO {meta.modo}
            </span>
          )}
        </div>

        {localStorage.getItem("user_name") && (
          <p className="text-gray-700 text-lg mb-4">
            👤 Bienvenido, <strong>{localStorage.getItem("user_name")}</strong>
          </p>
        )}

        {errorMsg && (
          <div className="bg-red-100 text-red-700 text-sm rounded p-3 mb-4 border border-red-300">
            {errorMsg}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-left mb-4">
          <div>
            <p className="text-gray-700 font-medium mb-1">💰 Saldo USDT disponible:</p>
            <div className="bg-green-100 text-green-800 font-semibold p-2 rounded">
              {balanceUSDT}
            </div>
          </div>
          <div>
            <p className="text-gray-700 font-medium mb-1">💵 Total estimado en USD:</p>
            <div className="bg-blue-100 text-blue-800 font-semibold p-2 rounded">
              {totalUSD === null ? "No disponible" : totalUSD}
            </div>
          </div>
        </div>

        {meta.modo === "PAPER" && (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 text-left mb-6">
            <div className="border border-gray-200 rounded-lg p-3">
              <p className="text-xs text-gray-500">P&L realizado</p>
              <p className={`font-semibold ${Number(meta.pnlRealizado) >= 0 ? "text-green-700" : "text-red-700"}`}>
                ${usd(meta.pnlRealizado)}
              </p>
              <p className="text-[11px] text-gray-400">Neto de fees ejecutadas</p>
            </div>
            <div className="border border-gray-200 rounded-lg p-3">
              <p className="text-xs text-gray-500">P&L total mostrado</p>
              <p className={`font-semibold ${Number(meta.pnlTotal) >= 0 ? "text-green-700" : "text-red-700"}`}>
                {meta.pnlTotalStatus === "DISPONIBLE" ? `$${usd(meta.pnlTotal)}` : "—"}
              </p>
              <p className="text-[11px] text-gray-400">
                {meta.pnlTotalNetoLiquidacion ? "Neto realizado" : "Incluye MTM pre-salida"}
              </p>
            </div>
            <div className="border border-gray-200 rounded-lg p-3">
              <p className="text-xs text-gray-500">Fees acumuladas</p>
              <p className="font-semibold text-gray-800">${usd(meta.fees)}</p>
            </div>
            <div className="border border-gray-200 rounded-lg p-3">
              <p className="text-xs text-gray-500">Operaciones</p>
              <p className="font-semibold text-gray-800">{meta.operaciones}</p>
            </div>
            <div className="border border-gray-200 rounded-lg p-3">
              <p className="text-xs text-gray-500">Posiciones abiertas</p>
              <p className="font-semibold text-gray-800">{meta.posiciones}</p>
            </div>
          </div>
        )}

        {meta.modo === "PAPER" && estrategias.length > 0 && (
          <div className="mb-6 text-left">
            <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 mb-2">
              <div>
                <h2 className="text-xl font-semibold text-gray-800">Rendimiento por estrategia</h2>
                <p className="text-xs text-gray-500">
                  Atribución FIFO por estrategia de entrada; P&L realizado neto de fees ejecutadas.
                </p>
              </div>
              <span className="text-xs text-gray-400">Desconocido nunca se interpreta como 0</span>
            </div>
            <div className="overflow-x-auto border border-gray-200 rounded-lg">
              <table className="min-w-full bg-white text-sm">
                <thead>
                  <tr className="bg-gray-100 text-gray-700">
                    <th className="px-3 py-2 text-left">Estrategia</th>
                    <th className="px-3 py-2 text-right">Cierres</th>
                    <th className="px-3 py-2 text-right">P&L neto</th>
                    <th className="px-3 py-2 text-right">Retorno realizado</th>
                    <th className="px-3 py-2 text-right">Neto esperado</th>
                    <th className="px-3 py-2 text-right">Error vs esperado</th>
                    <th className="px-3 py-2 text-right">Tasa positiva</th>
                    <th className="px-3 py-2 text-right">Coste aún abierto</th>
                  </tr>
                </thead>
                <tbody>
                  {estrategias.map((e) => (
                    <tr key={e.nombre} className="border-t hover:bg-gray-50">
                      <td className="px-3 py-2 font-medium text-gray-800">{e.nombre}</td>
                      <td className="px-3 py-2 text-right">{e.cierres ?? 0}</td>
                      <td className={`px-3 py-2 text-right font-semibold ${
                        Number(e.pnl_realizado_neto_usd) >= 0 ? "text-green-700" : "text-red-700"
                      }`}>
                        ${usd(e.pnl_realizado_neto_usd)}
                      </td>
                      <td className="px-3 py-2 text-right">{bps(e.retorno_realizado_neto_bps)}</td>
                      <td className="px-3 py-2 text-right">{bps(e.expected_net_bps_ponderado)}</td>
                      <td className="px-3 py-2 text-right">{bps(e.error_expected_vs_realizado_bps)}</td>
                      <td className="px-3 py-2 text-right">{porcentaje(e.positive_rate)}</td>
                      <td className="px-3 py-2 text-right">${usd(e.coste_abierto_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Las posiciones abiertas no cuentan como beneficio realizado. El retorno de una estrategia se actualiza cuando existen ventas que cierran sus lotes de entrada.
            </p>
          </div>
        )}

        {balances.length > 0 && (
          <>
            <div className="mt-4 text-left">
              <h2 className="text-xl font-semibold mb-2 text-gray-800">📊 Monedas con saldo</h2>
              <div className="overflow-x-auto">
                <table className="min-w-full bg-white border border-gray-200 rounded">
                  <thead>
                    <tr className="bg-gray-100">
                      <th className="px-4 py-2">Moneda</th>
                      <th className="px-4 py-2">Disponible</th>
                      <th className="px-4 py-2">Bloqueado</th>
                      <th className="px-4 py-2">Precio USDT</th>
                      <th className="px-4 py-2">Valor USD</th>
                      <th className="px-4 py-2">Precio Promedio</th>
                      <th className="px-4 py-2">
                        {meta.modo === "PAPER" ? "P&L abierto*" : "Ganancia/Pérdida"}
                      </th>
                      <th className="px-4 py-2">Confianza</th>
                    </tr>
                  </thead>
                  <tbody>
                    {balances.map((b) => (
                      <tr key={b.asset} className="border-t hover:bg-gray-50">
                        <td className="px-4 py-2 text-gray-800">{b.asset}</td>
                        <td className="px-4 py-2 text-green-700">{b.free}</td>
                        <td className="px-4 py-2 text-yellow-700">{b.locked}</td>
                        <td className="px-4 py-2 text-blue-700">
                          {b.price_usdt && b.price_usdt > 0 ? b.price_usdt.toFixed(6) : "—"}
                        </td>
                        <td className="px-4 py-2 text-black font-medium">
                          {b.total_usd?.toFixed(2) ?? "—"}
                        </td>
                        <td className="px-4 py-2 text-indigo-700">
                          {b.average_price_status === "DISPONIBLE"
                            ? b.average_price.toFixed(2)
                            : <span className="text-gray-400" title="No hay coste base registrado">No disponible</span>}
                        </td>
                        <td className={`px-4 py-2 font-semibold ${
                          b.pnl_status !== "DISPONIBLE" ? "text-gray-400"
                            : b.pnl >= 0 ? "text-green-600" : "text-red-600"}`}>
                          {b.pnl_status === "DISPONIBLE"
                            ? b.pnl.toFixed(2)
                            : <span title="No hay coste base para calcular el P&L">No disponible</span>}
                        </td>
                        <td className="px-4 py-2 text-purple-800">N/D</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {meta.modo === "PAPER" && meta.posiciones > 0 && (
                <p className="text-xs text-gray-500 mt-2">
                  * El P&L abierto es mark-to-market: incluye el coste de entrada ya ejecutado, pero no una fee ni slippage hipotéticos de salida. El P&L realizado sí usa los fills y fees persistidos.
                </p>
              )}
            </div>

            <BalanceChart data={balances} />
          </>
        )}

        <button
          onClick={handleLogout}
          className="mt-6 bg-red-600 hover:bg-red-700 text-white font-semibold px-6 py-2 rounded-lg transition duration-300"
        >
          🔒 Cerrar Sesión
        </button>
      </div>
    </div>
  );
}

export default DashboardPage;
