import { useState } from "react";
import Navbar from "./components/Navbar";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";

function App() {
  const [page, setPage] = useState("dashboard");

  return (
    <div>
      <Navbar onNavigate={setPage} />
      <main className="p-4">
        {page === "dashboard" && <DashboardPage />}
        {page === "login" && <LoginPage />}
        {page === "signup" && <SignupPage />}
      </main>
    </div>
  );
}

export default App;
