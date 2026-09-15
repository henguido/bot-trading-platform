const formatTimestamp = (value) => {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString();
};

function issueCopy(error, hasSnapshot) {
  if (error?.code === "API_TIMEOUT") {
    return {
      badge: "TIMEOUT",
      title: "Tiempo de espera agotado",
      detail: hasSnapshot
        ? "La actualización tardó demasiado. Los datos visibles son el último snapshot confirmado y pueden estar desactualizados."
        : "La API no respondió dentro del límite. No hay datos confirmados para mostrar.",
      tone: "amber",
    };
  }

  if (!error?.status) {
    return {
      badge: "SIN CONEXIÓN",
      title: "Backend no accesible",
      detail: hasSnapshot
        ? "No se pudo contactar el backend. Los datos visibles son el último snapshot confirmado y pueden estar desactualizados."
        : "No se pudo contactar el backend. Verifica que el servicio PAPER esté iniciado antes de usar esta vista.",
      tone: "rose",
    };
  }

  return {
    badge: `HTTP ${error.status}`,
    title: "No se pudo actualizar la observabilidad",
    detail: hasSnapshot
      ? "El backend rechazó la actualización. El snapshot visible se conserva como referencia, pero no representa necesariamente el estado actual."
      : "El backend rechazó la solicitud y no hay datos confirmados para mostrar.",
    tone: "rose",
  };
}

function DataFreshnessAlert({ error, lastUpdated, onRetry, retrying = false }) {
  if (!error) return null;

  const hasSnapshot = Boolean(lastUpdated);
  const issue = issueCopy(error, hasSnapshot);
  const updatedLabel = formatTimestamp(lastUpdated);
  const tone = issue.tone === "amber"
    ? {
        wrapper: "border-amber-500/30 bg-amber-500/10",
        badge: "border-amber-500/30 bg-amber-500/10 text-amber-300",
        title: "text-amber-100",
        detail: "text-amber-100/70",
        button: "border-amber-500/30 text-amber-200 hover:bg-amber-500/10",
      }
    : {
        wrapper: "border-rose-500/30 bg-rose-500/10",
        badge: "border-rose-500/30 bg-rose-500/10 text-rose-300",
        title: "text-rose-100",
        detail: "text-rose-100/70",
        button: "border-rose-500/30 text-rose-200 hover:bg-rose-500/10",
      };

  return (
    <div role="alert" aria-live="polite" className={`mb-5 rounded-xl border px-4 py-3 ${tone.wrapper}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-wider ${tone.badge}`}>
              {issue.badge}
            </span>
            <p className={`text-sm font-semibold ${tone.title}`}>{issue.title}</p>
          </div>
          <p className={`mt-1 text-xs leading-5 ${tone.detail}`}>
            {issue.detail}
            {updatedLabel ? ` Última lectura confirmada: ${updatedLabel}.` : ""}
          </p>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            disabled={retrying}
            className={`shrink-0 rounded-lg border px-3 py-2 text-xs font-semibold transition disabled:cursor-wait disabled:opacity-50 ${tone.button}`}
          >
            {retrying ? "Reintentando…" : "Reintentar"}
          </button>
        )}
      </div>
    </div>
  );
}

export default DataFreshnessAlert;
