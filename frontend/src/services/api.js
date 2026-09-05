const RAW_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const BASE_URL = RAW_BASE_URL.replace(/\/+$/, "");
export const DEFAULT_TIMEOUT_MS = 15000;

async function detalleError(response) {
  try {
    const data = await response.json();
    return data?.detail || data?.message || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

function timeoutError(timeoutMs) {
  const error = new Error(`La API no respondió en ${Math.round(timeoutMs / 1000)} s`);
  error.code = "API_TIMEOUT";
  error.timeout = true;
  return error;
}

async function fetchConTimeout(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const controller = new AbortController();
  const externalSignal = options.signal;
  let timeoutTriggered = false;

  const abortarPorCaller = () => controller.abort(externalSignal?.reason);
  if (externalSignal) {
    if (externalSignal.aborted) {
      abortarPorCaller();
    } else {
      externalSignal.addEventListener("abort", abortarPorCaller, { once: true });
    }
  }

  const timer = setTimeout(() => {
    timeoutTriggered = true;
    controller.abort();
  }, timeoutMs);

  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (timeoutTriggered && error?.name === "AbortError") {
      throw timeoutError(timeoutMs);
    }
    throw error;
  } finally {
    clearTimeout(timer);
    externalSignal?.removeEventListener?.("abort", abortarPorCaller);
  }
}

export async function apiFetch(
  path,
  options = {},
  { auth = true, timeoutMs = DEFAULT_TIMEOUT_MS } = {},
) {
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

  const response = await fetchConTimeout(
    `${BASE_URL}${path}`,
    { ...options, headers },
    timeoutMs,
  );
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

export function getDecisionCycles(limite = 12) {
  const seguro = Math.max(1, Math.min(Number(limite) || 12, 100));
  return apiFetch(`/api/decision-cycles?limite=${seguro}`);
}

export function getHealth() {
  return apiFetch("/health", {}, { auth: false });
}

export function getPaperReadiness() {
  return apiFetch("/api/readiness");
}

export async function downloadPaperJournal(formato = "csv") {
  const seguro = formato === "json" ? "json" : "csv";
  const headers = new Headers();
  const token = localStorage.getItem("token");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetchConTimeout(
    `${BASE_URL}/api/paper/journal/export?formato=${seguro}`,
    { headers },
    DEFAULT_TIMEOUT_MS,
  );
  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem("token");
      localStorage.removeItem("user_name");
    }
    const error = new Error(await detalleError(response));
    error.status = response.status;
    throw error;
  }

  return {
    blob: await response.blob(),
    filename: seguro === "csv" ? "paper-journal.csv" : "paper-journal.json",
  };
}

export async function getWelcomeMessage() {
  const data = await apiFetch("/", {}, { auth: false });
  return data.message;
}
