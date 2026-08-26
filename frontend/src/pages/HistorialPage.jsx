import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getHistorial } from "../services/api";

function HistorialPage() {
  const navigate = useNavigate();
  const [historial, setHistorial] = useState([]);
  const [error, setError] = useState("");
  const [expandedIndex, setExpandedIndex] = useState(null);

  useEffect(() => {
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
      });
  }, [navigate]);

  const toggleExpand = (index) => {
    setExpandedIndex(index === expandedIndex ? null : index);
  };

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-5xl mx-auto bg-white rounded-xl shadow-md p-6">
        <h1 className="text-3xl font-bold mb-4 text-gray-800">📜 Historial de Operaciones</h1>

        {error && (
          <p className="text-red-600 text-center mb-4 font-semibold">{error}</p>
        )}

        {historial.length === 0 && !error ? (
          <p className="text-gray-600 text-center">No hay operaciones registradas.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full bg-white border border-gray-200">
              <thead className="bg-gray-100">
                <tr>
                  <th className="px-4 py-2 border-b text-left">Símbolo</th>
                  <th className="px-4 py-2 border-b text-left">Acción</th>
                  <th className="px-4 py-2 border-b text-left">Cantidad</th>
                  <th className="px-4 py-2 border-b text-left">Precio</th>
                  <th className="px-4 py-2 border-b text-left">Fecha</th>
                </tr>
              </thead>
              <tbody>
                {historial.map((item, index) => (
                  <>
                    <tr
                      key={index}
                      onClick={() => toggleExpand(index)}
                      className="cursor-pointer hover:bg-gray-50 transition duration-200"
                    >
                      <td className="px-4 py-2 border-b">{item.symbol}</td>
                      <td className="px-4 py-2 border-b">{item.action}</td>
                      <td className="px-4 py-2 border-b">{item.quantity}</td>
                      <td className="px-4 py-2 border-b">${item.price}</td>
                      <td className="px-4 py-2 border-b">{item.timestamp}</td>
                    </tr>
                    {expandedIndex === index && (
                      <tr>
                        <td colSpan="5" className="bg-gray-50 px-4 py-4 border-b">
                          <pre className="text-sm whitespace-pre-wrap text-gray-700">
                            {JSON.stringify(item.context || item.decision_gpt || {}, null, 2)}
                          </pre>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default HistorialPage;
