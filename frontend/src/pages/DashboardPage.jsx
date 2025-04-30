import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

function DashboardPage() {
  const navigate = useNavigate();
  const [token, setToken] = useState("");

  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    if (!storedToken) {
      navigate("/login");
    } else {
      setToken(storedToken);
    }
  }, [navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white p-6 rounded shadow-md max-w-lg w-full text-center">
        <h1 className="text-2xl font-bold mb-4">Bienvenido al Dashboard</h1>
        <p className="text-gray-700 mb-2">Tu token:</p>
        <code className="break-all text-sm text-gray-600 bg-gray-100 border rounded p-2 block">
          {token}
        </code>
        <button
          className="mt-6 bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
          onClick={() => {
            localStorage.removeItem("token");
            navigate("/login");
          }}
        >
          Cerrar Sesión
        </button>
      </div>
    </div>
  );
}

export default DashboardPage;
