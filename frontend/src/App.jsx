import { Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import HistorialPage from "./pages/HistorialPage";
import TransaccionesRealesPage from "./pages/TransaccionesRealesPage"; // ✅ Corregido

function App() {
  return (
    <div>
      <Navbar />
      <main className="p-4">
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/historial" element={<HistorialPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/transacciones-reales" element={<TransaccionesRealesPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
