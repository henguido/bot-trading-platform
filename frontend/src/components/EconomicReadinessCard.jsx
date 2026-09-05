const STATUS_LABELS = {
  VERIFICADA: "Verificada",
  VENCIDA: "Vencida",
  INVALIDA: "Inválida",
  NO_DISPONIBLE: "No disponible",
  CUENTA_DISPONIBLE_SIN_VERIFICAR: "Cuenta sin verificar",
};

const SOURCE_LABELS = {
  MANUAL_VERIFIED: "Manual verificada",
  BINANCE_ACCOUNT: "Cuenta Binance",
};

function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "—";
  if (value < 60) return "menos de 1 min";

  const minutes = Math.floor(value / 60);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  if (days > 0) return hours > 0 ? `${days} d ${hours} h` : `${days} d`;
  if (hours > 0) return `${hours} h ${minutes % 60} min`;
  return `${minutes} min`;
}

function ReadinessBadge({ readiness }) {
  const ready = Boolean(readiness?.ready);
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${
      ready
        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
        : "border-rose-500/30 bg-rose-500/10 text-rose-300"
    }`}>
      {ready ? "READY" : "BLOQUEADO"}
    </span>
  );
}

function DataPoint({ label, value, tone = "text-slate-200" }) {
  return (
    <div>
      <dt className="text-xs text-slate-600">{label}</dt>
      <dd className={`mt-1 text-sm font-semibold ${tone}`}>{value}</dd>
    </div>
  );
}

export default function EconomicReadinessCard({ readiness, loading = false, error = "" }) {
  if (loading) {
    return (
      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4" aria-busy="true">
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Readiness económico</p>
        <p className="mt-3 text-sm text-slate-500">Validando evidencia de fee…</p>
      </section>
    );
  }

  if (error || !readiness) {
    return (
      <section className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-amber-300">Readiness económico</p>
        <p className="mt-3 text-sm leading-5 text-amber-100/80">
          No se pudo verificar la fee ni el gate PAPER. Este estado no se interpreta como listo.
        </p>
      </section>
    );
  }

  const fee = readiness.fee || {};
  const bps = Number(fee.bps_per_side);
  const hasBps = fee.bps_per_side !== null
    && fee.bps_per_side !== undefined
    && Number.isFinite(bps);
  const age = Number(fee.age_seconds);
  const maxAge = Number(fee.max_age_seconds);
  const hasAge = fee.age_seconds !== null
    && fee.age_seconds !== undefined
    && Number.isFinite(age);
  const hasMaxAge = fee.max_age_seconds !== null
    && fee.max_age_seconds !== undefined
    && Number.isFinite(maxAge);
  const hasValidity = hasAge && hasMaxAge;
  const remaining = hasValidity ? Math.max(0, maxAge - age) : null;
  const verified = fee.status === "VERIFICADA";

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Readiness económico</p>
          <p className="mt-1 text-xs text-slate-600">Evidencia segura del gate PAPER</p>
        </div>
        <ReadinessBadge readiness={readiness} />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
        <DataPoint
          label="Fee taker"
          value={hasBps ? `${bps.toFixed(1)} bps/lado` : "No verificable"}
          tone={verified ? "text-emerald-300" : "text-rose-300"}
        />
        <DataPoint
          label="Estado"
          value={STATUS_LABELS[fee.status] || fee.status || "No disponible"}
          tone={verified ? "text-emerald-300" : "text-amber-300"}
        />
        <DataPoint label="Fuente" value={SOURCE_LABELS[fee.source] || fee.source || "—"} />
        <DataPoint label="Antigüedad" value={hasValidity ? formatDuration(age) : "—"} />
        <DataPoint
          label="Vigencia restante"
          value={remaining === null ? "—" : formatDuration(remaining)}
          tone={remaining === 0 ? "text-rose-300" : "text-slate-200"}
        />
        <DataPoint
          label="Controles"
          value={`${Number(readiness.blockers) || 0} bloqueos · ${Number(readiness.warnings) || 0} avisos`}
        />
      </dl>
    </section>
  );
}
