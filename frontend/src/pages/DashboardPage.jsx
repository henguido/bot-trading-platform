import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import BalanceChart from "./BalanceChart";

function DashboardPage() {
  const navigate = useNavigate();
  const [token, setToken] = useState("");
  const [balanceUSDT, setBalanceUSDT] = useState("Cargando...");
  const [balances, setBalances] = useState([]);
  const [totalUSD, setTotalUSD] = useState("Cargando...");

  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    if (!storedToken) {
      navigate("/login");
    } else {
      setToken(storedToken);

      fetch("http://localhost:8000/api/resumen")
        .then((res) => res.json())
        .then((data) => {
          if (Array.isArray(data.resumen)) {
            const usdt = data.resumen.find((b) => b.symbol.startsWith("USDT"));
            setBalanceUSDT(usdt ? usdt.cantidad : "0.00");
            // No se sustituye por 0 lo que la API declara NO_DISPONIBLE:
            // un dato desconocido debe verse como desconocido.
            setBalances(data.resumen.map(b => ({
              asset: b.symbol === "USDT" ? "USDT" : b.symbol.replace("USDT", ""),
              free: b.cantidad,
              locked: 0,
              price_usdt: b.precio_actual,
              total_usd: b.valor_actual,
              average_price: b.average_price,
              average_price_status: b.average_price_status,
              pnl: b.pnl,
              pnl_status: b.pnl_status
            })));
            setTotalUSD(data.valor_total_usd);
          } else {
            setBalanceUSDT("Error");
            setTotalUSD("Error");
          }
        });

    }
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center p-4">
      <div className="bg-white shadow-xl rounded-xl p-8 w-full max-w-3xl text-center animate-fade-in">
        <h1 className="text-3xl font-bold text-gray-800 mb-4">
          👋 Bienvenido a BOT Trading Platform
        </h1>

        {localStorage.getItem("user_name") && (
          <p className="text-gray-700 text-lg mb-4">
            👤 Bienvenido, <strong>{localStorage.getItem("user_name")}</strong>
          </p>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-left mb-6">
          <div>
            <p className="text-gray-700 font-medium mb-1">
              💰 Saldo USDT disponible:
            </p>
            <div className="bg-green-100 text-green-800 font-semibold p-2 rounded">
              {balanceUSDT}
            </div>
          </div>
          <div>
            <p className="text-gray-700 font-medium mb-1">
              💵 Total estimado en USD:
            </p>
            <div className="bg-blue-100 text-blue-800 font-semibold p-2 rounded">
              {totalUSD}
            </div>
          </div>
        </div>

        {balances.length > 0 && (
          <>
            <div className="mt-4 text-left">
              <h2 className="text-xl font-semibold mb-2 text-gray-800">
                📊 Monedas con saldo
              </h2>
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
                    <th className="px-4 py-2">Ganancia/Pérdida</th>
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
                        {b.total_usd?.toFixed(2) ?? "0.00"}
                      </td>
                      <td className="px-4 py-2 text-indigo-700">
                        {b.average_price_status === "DISPONIBLE"
                          ? b.average_price.toFixed(2)
                          : <span className="text-gray-400" title="No hay coste base registrado">No disponible</span>}
                      </td>
                      <td className={`px-4 py-2 font-semibold ${
                        b.pnl_status !== "DISPONIBLE" ? 'text-gray-400'
                          : b.pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
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
