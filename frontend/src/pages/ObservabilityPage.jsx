import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getDecisionCycles, getHealth } from "../services/api";

const PRIMARY_REASON_LABELS = {
  OPERACION_EJECUTADA: "Operación ejecutada",
  EJECUCION_FALLIDA: "Falló la ejecución",
  RIESGO_BLOQUEO: "Bloqueado por riesgo",
  RENTABILIDAD_BLOQUEO: "Bloqueado por rentabilidad",
  PROPUESTA_SIN_EJECUCION: "Propuesta sin ejecución",
  MOTOR_ESPERAR: "Motor decidió esperar",
  MOTOR_SIN_RESULTADOS: "Motor sin resultados",
  SIN_CANDIDATOS_DESPUES_SCANNER: "Sin candidatos después del scanner",
  SIN_EJECUCION: "Sin ejecución",
};

const reasonLabel = (reason) => PRIMARY_REASON_LABELS[reason] || String(reason || "Sin diagnóstico").replaceAll("_", " ");

const pct = (part, total) => {
  const numerator = Math.max(0, Number(part) || 0);
  const denominator = Math.max(0, Number(total) || 0);
  if (!denominator) return null;
  return Math.max(0, Math.min(100, (numerator / denominator) * 100));
};

const pctLabel = (value) => value == null ? "—" : `${value.toFixed(1)}%`;

function Pill({ status = "neutral", children }) {
  const styles = {
    ok: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    warn: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    bad: "border-rose-500/30 bg-rose-500/10 text-rose-300",
    neutral: "border-slate-700 bg-slate-800/70 text-slate-300",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${styles[status]}`}>
      {children}
    </span>
  );
}

function FunnelStage({ label, value, max, previous, detail }) {
  const numeric = Math.max(0, Number(value) || 0);
  const denominator = Math.max(1, Number(max) || 1);
  const width = Math.max(3, Math.min(100, (numeric / denominator) * 100));
  const retention = previous == null ? null : pct(numeric, previous);
  const loss = retention == null ? null : Math.max(0, 100 - retention);
  return (
    <div>
      <div className="mb-1 flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-300">{label}</p>
          {detail && <p className="text-[11px] text-slate-600">{detail}</p>}
        </div>
        <div className="text-right">
          <span className="font-mono text-sm font-semibold text-slate-200">{numeric}</span>
          {retention != null && (
            <p className="mt-0.5 text-[11px] text-slate-500">
              {pctLabel(retention)} retenido · {pctLabel(loss)} caída
            </p>
          )}
        </div>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
        <div className="h-full rounded-full bg-cyan-400/80" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function SmallMetric({ label, value, detail }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/45 px-3 py-3">
      <p className="text-[11px] uppercase tracking-wider text-slate-600">{label}</p>
      <p className="mt-1 font-mono text-lg font-semibold text-slate-200">{Number(value || 0)}</p>
      <p className="mt-1 text-[11px] leading-4 text-slate-600">{detail}</p>
    </div>
  );
}

function ObservabilityPage() {
  const navigate = useNavigate();
  const [health, setHealth] = useState(null);
  const [cycles, setCycles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);

  const load = useCallback(async ({ initial = false } = {}) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    try {
      const [healthData, cyclesData] = await Promise.all([
        getHealth(),
        getDecisionCycles(12),
      ]);
      setHealth(healthData || null);
      setCycles(Array.isArray(cyclesData) ? cyclesData : []);
      setUpdatedAt(new Date());
      setError("");
    } catch (err) {
      if (err.status === 401) {
        navigate("/login");
        return;
      }
      setError(err.message || "No se pudo cargar observabilidad");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [navigate]);

  useEffect(() => {
    load({ initial: true });
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 30_000);
    const onVisible = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load]);

  const latest = cycles[0] || null;
  const counts = latest?.contadores || {};
  const universe = Number(counts.universo || 0);
  const afterEligibility = Number(counts.elegibles_compra || 0) + Number(counts.preservados_venta || 0);
  const afterScanner = Number(counts.scanner_seleccionados || 0) + Number(counts.scanner_preservados || 0);
  const engineResults = Number(counts.motor_resultados || 0);
  const riskApproved = Number(counts.riesgo_aprobadas || 0);
  const executions = Number(counts.ejecuciones_ok || 0);
  const funnelMax = Math.max(universe, afterEligibility, afterScanner, engineResults, riskApproved, executions, 1);

  const funnelStages = useMemo(() => [
    { label: "Elegibilidad", previous: universe, value: afterEligibility },
    { label: "Scanner", previous: afterEligibility, value: afterScanner },
    { label: "Motor de decisión", previous: afterScanner, value: engineResults },
    { label: "Riesgo", previous: engineResults, value: riskApproved },
    { label: "Ejecución", previous: riskApproved, value: executions },
  ].map((stage) => ({
    ...stage,
    retention: pct(stage.value, stage.previous),
  })), [universe, afterEligibility, afterScanner, engineResults, riskApproved, executions]);

  const biggestDrop = useMemo(() => {
    const comparable = funnelStages.filter((stage) => stage.retention != null && stage.previous > 0);
    if (!comparable.length) return null;
    return comparable.reduce((worst, stage) => (
      stage.retention < worst.retention ? stage : worst
    ));
  }, [funnelStages]);

  const topReasons = useMemo(() => {
    if (!latest?.motivos || typeof latest.motivos !== "object") return [];
    return Object.entries(latest.motivos)
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .slice(0, 8);
  }, [latest]);

  // backend.esquema usa "OK" como estado canonico. Se tolera ALINEADO solo
  // para leer snapshots antiguos, pero la UI ya no marca como malo un /health real.
  const schemaState = health?.esquema?.estado;
  const schemaOk = schemaState === "OK" || schemaState === "ALINEADO";
  const healthOk = Boolean(health?.bucle_activo && health?.es_lider && schemaOk);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/95">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400">Observabilidad</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-white">Por qué operó — o por qué no</h1>
            <p className="mt-1 text-sm text-slate-500">Embudo persistente por ciclo. Solo lectura; no modifica decisiones.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => navigate("/dashboard")}
              className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
            >
              Dashboard
            </button>
            <button
              onClick={() => navigate("/historial")}
              className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
            >
              Journal
            </button>
            <button
              onClick={() => load()}
              disabled={refreshing}
              className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-500/15 disabled:opacity-50"
            >
              {refreshing ? "Actualizando…" : "Actualizar"}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {error && (
          <div className="mb-5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>
        )}

        {loading ? (
          <div className="grid min-h-[360px] place-items-center rounded-2xl border border-slate-800 bg-slate-900/50">
            <div className="text-center">
              <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-slate-700 border-t-cyan-400" />
              <p className="mt-3 text-sm text-slate-500">Cargando estado operativo…</p>
            </div>
          </div>
        ) : (
          <>
            <section className="grid gap-4 md:grid-cols-4">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                <p className="text-xs uppercase tracking-wider text-slate-500">Proceso</p>
                <div className="mt-3"><Pill status={healthOk ? "ok" : "warn"}>{healthOk ? "Operativo" : "Revisar"}</Pill></div>
                <p className="mt-3 text-xs leading-5 text-slate-500">{health?.motivo_inactivo || "Sin bloqueo reportado"}</p>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                <p className="text-xs uppercase tracking-wider text-slate-500">Liderazgo</p>
                <p className="mt-2 text-xl font-semibold text-white">{health?.es_lider ? "Líder" : "No líder"}</p>
                <p className="mt-1 text-xs text-slate-500">Loop {health?.bucle_activo ? "activo" : "inactivo"}</p>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                <p className="text-xs uppercase tracking-wider text-slate-500">Esquema</p>
                <div className="mt-3"><Pill status={schemaOk ? "ok" : "bad"}>{schemaState || "Desconocido"}</Pill></div>
                <p className="mt-3 text-xs text-slate-500">{health?.esquema?.revision_actual || "—"} → {health?.esquema?.revision_esperada || "—"}</p>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                <p className="text-xs uppercase tracking-wider text-slate-500">Última lectura</p>
                <p className="mt-2 text-sm font-semibold text-slate-200">{updatedAt ? updatedAt.toLocaleTimeString() : "—"}</p>
                <p className="mt-1 text-xs text-slate-500">Auto-refresh 30 s con pestaña visible</p>
              </div>
            </section>

            <section className="mt-6 grid gap-6 lg:grid-cols-3">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 lg:col-span-2">
                <div className="flex flex-col gap-2 border-b border-slate-800 pb-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="font-semibold text-white">Último ciclo</h2>
                    <p className="mt-1 text-xs text-slate-500">{latest?.timestamp ? new Date(latest.timestamp).toLocaleString() : "Todavía sin ciclos persistidos"}</p>
                  </div>
                  {latest && <Pill status={latest.hubo_ejecucion ? "ok" : "warn"}>{reasonLabel(latest.motivo_principal)}</Pill>}
                </div>

                {latest ? (
                  <>
                    <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      <SmallMetric label="Descartados elegibilidad" value={counts.descartados_elegibilidad} detail="No llegaron al scanner" />
                      <SmallMetric label="Descartados scanner" value={counts.scanner_descartados} detail="Fuera del Top-N ejecutable" />
                      <SmallMetric label="Bloqueos rentabilidad" value={Number(counts.rentabilidad_pre_bloqueados || 0) + Number(counts.rentabilidad_post_bloqueados || 0)} detail="05E solo si el gate fue aplicado" />
                      <SmallMetric label="Rechazos de riesgo" value={counts.riesgo_rechazadas} detail="MotorRiesgo mantuvo autoridad" />
                    </div>

                    {biggestDrop && (
                      <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">Mayor caída del ciclo</p>
                        <p className="mt-1 text-sm text-slate-300">
                          <span className="font-semibold text-white">{biggestDrop.label}</span>: {biggestDrop.previous} → {biggestDrop.value} candidatos · {pctLabel(100 - biggestDrop.retention)} de caída.
                        </p>
                        <p className="mt-1 text-[11px] text-slate-500">Diagnóstico descriptivo; no cambia el ranking ni las decisiones del bot.</p>
                      </div>
                    )}

                    <div className="mt-5 space-y-4">
                      <FunnelStage label="Universo" value={universe} max={funnelMax} detail="Activos evaluables al inicio · 100% referencia" />
                      <FunnelStage label="Elegibilidad" value={afterEligibility} max={funnelMax} previous={universe} detail="Compras ejecutables + posiciones preservadas" />
                      <FunnelStage label="Scanner" value={afterScanner} max={funnelMax} previous={afterEligibility} detail="Top-N + posiciones abiertas" />
                      <FunnelStage label="Motor de decisión" value={engineResults} max={funnelMax} previous={afterScanner} detail={latest.decision_engine || "—"} />
                      <FunnelStage label="Riesgo aprobado" value={riskApproved} max={funnelMax} previous={engineResults} detail="MotorRiesgo" />
                      <FunnelStage label="Ejecuciones" value={executions} max={funnelMax} previous={riskApproved} detail="Fills registrados" />
                    </div>
                  </>
                ) : (
                  <div className="py-12 text-center text-sm text-slate-500">El primer ciclo aparecerá después de migrar 0007 y ejecutar el bot.</div>
                )}
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
                <h2 className="font-semibold text-white">Motivos del ciclo</h2>
                <p className="mt-1 text-xs text-slate-500">Contadores agregados; no crea una fila por símbolo.</p>
                <div className="mt-4 space-y-2">
                  {topReasons.length ? topReasons.map(([reason, count]) => (
                    <div key={reason} className="flex items-start justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2.5">
                      <span className="break-all text-xs leading-5 text-slate-400">{reason.replaceAll("_", " ")}</span>
                      <span className="font-mono text-xs font-semibold text-slate-200">{count}</span>
                    </div>
                  )) : (
                    <p className="py-8 text-center text-xs text-slate-600">Sin motivos registrados todavía.</p>
                  )}
                </div>
              </div>
            </section>

            <section className="mt-6 overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70">
              <div className="border-b border-slate-800 px-5 py-4">
                <h2 className="font-semibold text-white">Ciclos recientes</h2>
                <p className="mt-1 text-xs text-slate-500">Historial compacto para detectar patrones de NO TRADE.</p>
              </div>
              {cycles.length ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-950/40 text-xs uppercase tracking-wider text-slate-500">
                      <tr>
                        <th className="px-5 py-3 text-left font-medium">Fecha</th>
                        <th className="px-4 py-3 text-left font-medium">Motor</th>
                        <th className="px-4 py-3 text-left font-medium">Resultado principal</th>
                        <th className="px-4 py-3 text-right font-medium">Scanner</th>
                        <th className="px-4 py-3 text-right font-medium">Compras</th>
                        <th className="px-4 py-3 text-right font-medium">Riesgo OK</th>
                        <th className="px-5 py-3 text-right font-medium">Ejecuciones</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/80">
                      {cycles.map((cycle) => {
                        const c = cycle.contadores || {};
                        return (
                          <tr key={cycle.ciclo_id} className="hover:bg-slate-800/30">
                            <td className="px-5 py-3 text-slate-400">{cycle.timestamp ? new Date(cycle.timestamp).toLocaleString() : "—"}</td>
                            <td className="px-4 py-3 text-slate-300">{cycle.decision_engine || "—"}</td>
                            <td className="px-4 py-3"><Pill status={cycle.hubo_ejecucion ? "ok" : "warn"}>{reasonLabel(cycle.motivo_principal)}</Pill></td>
                            <td className="px-4 py-3 text-right font-mono text-slate-400">{Number(c.scanner_seleccionados || 0) + Number(c.scanner_preservados || 0)}</td>
                            <td className="px-4 py-3 text-right font-mono text-slate-400">{c.motor_comprar || 0}</td>
                            <td className="px-4 py-3 text-right font-mono text-slate-400">{c.riesgo_aprobadas || 0}</td>
                            <td className="px-5 py-3 text-right font-mono font-semibold text-slate-200">{c.ejecuciones_ok || 0}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="px-5 py-10 text-center text-sm text-slate-500">Sin ciclos auditados todavía.</div>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}

export default ObservabilityPage;
