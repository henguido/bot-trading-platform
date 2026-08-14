import { Link } from "react-router-dom";

function Navbar({ token, setToken }) {
  const handleLogout = () => {
    setToken(null);
    localStorage.removeItem("token");
  };

  return (
    <nav className="bg-blue-600 p-4 text-white shadow-md">
      <div className="flex justify-between items-center max-w-6xl mx-auto">
        <Link to="/dashboard" className="text-2xl font-bold">
          BOT Trading
        </Link>
        <div className="space-x-4">
          {token ? (
            <>
              <Link to="/dashboard" className="hover:underline">
                Dashboard
              </Link>
              <Link to="/historial" className="hover:underline">
                Historial
              </Link>
              <button
                onClick={handleLogout}
                className="bg-white text-blue-600 px-4 py-2 rounded hover:bg-gray-200 transition"
              >
                Cerrar sesión
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="hover:underline">
                Iniciar sesión
              </Link>
              <Link to="/signup" className="hover:underline">
                Registrarse
              </Link>
              <Link to="/transacciones-reales">
                Transacciones Reales
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}

export default Navbar;
