import { Link, useLocation, useNavigate } from "react-router-dom";

function Navbar() {
  const location = useLocation();
  const navigate = useNavigate();
  const token = localStorage.getItem("token");

  // Dashboard e historial tienen cabecera operativa propia. Evita dos barras
  // apiladas y mantiene las pantallas de trabajo con mas espacio util.
  if (location.pathname === "/dashboard" || location.pathname === "/historial") {
    return null;
  }

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user_name");
    navigate("/login");
  };

  return (
    <nav className="border-b border-slate-800 bg-slate-950 text-slate-100">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <Link to={token ? "/dashboard" : "/login"} className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 text-xs font-bold text-cyan-300">
            BT
          </span>
          <div>
            <p className="font-semibold tracking-tight text-white">BOT Trading</p>
            <p className="text-[11px] text-slate-500">Plataforma PAPER</p>
          </div>
        </Link>

        <div className="flex items-center gap-2 text-sm">
          {token ? (
            <>
              <Link
                to="/dashboard"
                className="rounded-lg px-3 py-2 text-slate-400 transition hover:bg-slate-900 hover:text-slate-100"
              >
                Dashboard
              </Link>
              <Link
                to="/historial"
                className="rounded-lg px-3 py-2 text-slate-400 transition hover:bg-slate-900 hover:text-slate-100"
              >
                Journal
              </Link>
              <button
                onClick={handleLogout}
                className="rounded-lg border border-slate-700 px-3 py-2 text-slate-300 transition hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-300"
              >
                Salir
              </button>
            </>
          ) : (
            <>
              <Link
                to="/login"
                className="rounded-lg px-3 py-2 text-slate-400 transition hover:bg-slate-900 hover:text-slate-100"
              >
                Iniciar sesión
              </Link>
              <Link
                to="/signup"
                className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 font-medium text-cyan-300 transition hover:bg-cyan-500/15"
              >
                Crear cuenta
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}

export default Navbar;
