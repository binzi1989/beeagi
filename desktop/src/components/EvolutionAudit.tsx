import { EvolutionEventView, HardeningReportResponse } from "../types";

interface EvolutionAuditProps {
  events: EvolutionEventView[];
  hardeningReport?: HardeningReportResponse;
  onRunHardeningCheck: () => Promise<void>;
  busy: boolean;
}

export function EvolutionAudit({ events, hardeningReport, onRunHardeningCheck, busy }: EvolutionAuditProps) {
  return (
    <section className="panel panel-scroll">
      <header className="panel-title-row">
        <h2>Evolution Audit</h2>
        <span className="badge">{events.length}</span>
      </header>
      <button className="button" onClick={onRunHardeningCheck} disabled={busy}>
        {busy ? "Running Health Check..." : "Run Hardening Check"}
      </button>
      {hardeningReport && (
        <div className="plan-preview">
          <h3>Hardening Report: {hardeningReport.overall.toUpperCase()}</h3>
          <p className="hint">
            Generated at {new Date(hardeningReport.generatedAt).toLocaleString()} | audits{" "}
            {hardeningReport.summary.recentAuditCount} | events {hardeningReport.summary.recentEventCount}
          </p>
          <ul>
            {hardeningReport.checks.map((check) => (
              <li key={check.id}>
                [{check.level.toUpperCase()}] {check.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="event-list">
        {events.map((event) => (
          <article key={event.id} className="event-item">
            <div className="event-head">
              <strong>{event.topic}</strong>
              <span>{new Date(event.createdAt).toLocaleString()}</span>
            </div>
            <pre>{JSON.stringify(event.payload, null, 2)}</pre>
          </article>
        ))}
        {events.length === 0 && <p className="hint">No evolution events yet.</p>}
      </div>
    </section>
  );
}
