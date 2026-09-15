import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../services/api";

function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (localStorage.getItem("token")) {
      navigate("/dashboard");
    }
  }, [navigate]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setErrorMsg("");
    setLoading(true);

    try {
      const data = await login(email, password);
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("user_name", data.nombre);
      navigate("/dashboard");
    } catch (err) {
      setErrorMsg(err.message || "No se pudo iniciar sesión");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 px-4 py-10 text-slate-100">
      <div className="mx-auto grid min-h-[calc(100vh-5rem)] max-w-6xl items-center gap-10 lg:grid-cols-2">
        <section className="hidden lg:block">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400">BOT Trading Platform</p>
          <h1 className="mt-4 max-w-xl text-4xl font-semibold leading-tight tracking-tight text-white">
            Decisiones medibles. Ejecución PAPER auditable.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-slate-400">
            La consola separa señal, costes, riesgo y ejecución. Las posiciones PAPER se reconstruyen desde un journal persistente y las órdenes LIVE permanecen deshabilitadas.
          </p>
          <div className="mt-8 grid max-w-lg grid-cols-2 gap-3 text-sm">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
              <p className="font-medium text-slate-200">P&L trazable</p>
              <p className="mt-1 text-xs leading-5 text-slate-500">Fees, slippage y fills quedan visibles en el journal.</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
              <p className="font-medium text-slate-200">Riesgo determinista</p>
              <p className="mt-1 text-xs leading-5 text-slate-500">El motor de riesgo conserva autoridad sobre el tamaño.</p>
            </div>
          </div>
        </section>

        <form
          onSubmit={handleLogin}
          className="mx-auto w-full max-w-md rounded-3xl border border-slate-800 bg-slate-900/90 p-6 shadow-2xl shadow-black/20 sm:p-8"
        >
          <div className="mb-7">
            <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 text-sm font-bold text-cyan-300">
              BT
            </div>
            <h2 className="text-2xl font-semibold tracking-tight text-white">Iniciar sesión</h2>
            <p className="mt-2 text-sm text-slate-500">Accede a tu consola operativa PAPER.</p>
          </div>

          {errorMsg && (
            <div className="mb-5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {errorMsg}
            </div>
          )}

          <div className="mb-4">
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="email">
              Correo electrónico
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-3 text-slate-100 outline-none transition placeholder:text-slate-700 focus:border-cyan-500/60 focus:ring-2 focus:ring-cyan-500/10"
              placeholder="correo@ejemplo.com"
            />
          </div>

          <div className="mb-6">
            <div className="mb-2 flex items-center justify-between">
              <label className="text-sm font-medium text-slate-300" htmlFor="password">
                Contraseña
              </label>
              <button
                type="button"
                onClick={() => setShowPassword((actual) => !actual)}
                className="text-xs font-medium text-cyan-400 hover:text-cyan-300"
              >
                {showPassword ? "Ocultar" : "Mostrar"}
              </button>
            </div>
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-3 text-slate-100 outline-none transition focus:border-cyan-500/60 focus:ring-2 focus:ring-cyan-500/10"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-cyan-500 px-4 py-3 font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
          >
            {loading ? "Iniciando…" : "Entrar a la consola"}
          </button>

          <p className="mt-6 text-center text-sm text-slate-500">
            ¿No tienes cuenta?{" "}
            <button
              type="button"
              onClick={() => navigate("/signup")}
              className="font-medium text-cyan-400 hover:text-cyan-300"
            >
              Crear una cuenta
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}

export default LoginPage;
