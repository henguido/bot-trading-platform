const RAW_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const BASE_URL = RAW_BASE_URL.replace(/\/+$/, "");

async function detalleError(response) {
  try {
    const data = await response.json();
    return data?.detail || data?.message || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

export async function apiFetch(path, options = {}, { auth = true } = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (auth) {
    const token = localStorage.getItem("token");
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    if (auth && response.status === 401) {
      localStorage.removeItem("token");
      localStorage.removeItem("user_name");
    }
    const error = new Error(await detalleError(response));
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) return null;
  return response.json();
}

export function login(email, password) {
  return apiFetch("/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  }, { auth: false });
}

export function signup(nombre, email, password) {
  return apiFetch("/signup", {
    method: "POST",
    body: JSON.stringify({ nombre, email, password }),
  }, { auth: false });
}

export function getResumen() {
  return apiFetch("/api/resumen");
}

export function getHistorial() {
  return apiFetch("/api/historial");
}

export function getTransaccionesReales() {
  return apiFetch("/api/transacciones-reales");
}

export async function getWelcomeMessage() {
  const data = await apiFetch("/", {}, { auth: false });
  return data.message;
}
