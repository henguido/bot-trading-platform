import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

function DashboardPage() {
  const navigate = useNavigate();
  const [token, setToken] = useState("");
  const [balance, setBalance] = useState(null);

  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    if (!storedToken) {
      navigate("/login");
    } else {
      setToken(storedToken);

      // Obtener saldo de Binance
      fetch("https://bot-trading-backend.onrender.com/balance")
        .then((res) => res.json())
        .then((data) => {
          if (data.usdt !== undefined) {
            setBalance(data.usdt);
          } else {
            setBalance("Error al obtener saldo");
          }
        })
        .catch(() => setBalance("Error de conexión"));
    }
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center p-4">
      <div className="bg-white shadow-xl rounded-xl p-8 w-full max-w-xl text-center animate-fade-in">
        <h1 className="text-3xl font-bold text-gray-800 mb-4">
          👋 Bienvenido a BOT Trading Platform
        </h1>

        <p className="text-gray-600 mb-2 text-lg">Token guardado:</p>
        <div className="bg-gray-100 border border-gray-300 text-gray-700 text-sm p-4 rounded-md break-words mb-4">
          {token}
        </div>

        <div className="mt-6">
          <p className="text-gray-700">💰 Saldo disponible en Binance (USDT):</p>
          <div className="bg-green-100 text-green-800 font-semibold mt-1 p-2 rounded">
            {balance ?? "Cargando..."}
          </div>
        </div>

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
