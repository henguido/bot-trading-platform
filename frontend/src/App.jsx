import { Navigate, Route, Routes } from "react-router-dom";
import Navbar from "./components/Navbar";
import DashboardPage from "./pages/DashboardPage";
import HistorialPage from "./pages/HistorialPage";
import LoginPage from "./pages/LoginPage";
import ObservabilityPage from "./pages/ObservabilityPage";
import SignupPage from "./pages/SignupPage";
import TransaccionesRealesPage from "./pages/TransaccionesRealesPage";

function haySesion() {
  return Boolean(localStorage.getItem("token"));
}

function Inicio() {
  return <Navigate to={haySesion() ? "/dashboard" : "/login"} replace />;
}

function RutaPrivada({ children }) {
  if (!haySesion()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function App() {
  return (
    <div>
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<Inicio />} />
          <Route
            path="/dashboard"
            element={<RutaPrivada><DashboardPage /></RutaPrivada>}
          />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/historial"
            element={<RutaPrivada><HistorialPage /></RutaPrivada>}
          />
          <Route
            path="/observabilidad"
            element={<RutaPrivada><ObservabilityPage /></RutaPrivada>}
          />
          <Route path="/signup" element={<SignupPage />} />
          <Route
            path="/transacciones-reales"
            element={<RutaPrivada><TransaccionesRealesPage /></RutaPrivada>}
          />
          <Route path="*" element={<Inicio />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
