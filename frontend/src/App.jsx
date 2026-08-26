import { Navigate, Route, Routes } from "react-router-dom";
import Navbar from "./components/Navbar";
import DashboardPage from "./pages/DashboardPage";
import HistorialPage from "./pages/HistorialPage";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import TransaccionesRealesPage from "./pages/TransaccionesRealesPage";

function Inicio() {
  const token = localStorage.getItem("token");
  return <Navigate to={token ? "/dashboard" : "/login"} replace />;
}

function App() {
  return (
    <div>
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<Inicio />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/historial" element={<HistorialPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/transacciones-reales" element={<TransaccionesRealesPage />} />
          <Route path="*" element={<Inicio />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
