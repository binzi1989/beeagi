import { useState } from "react";

interface FeedbackCenterProps {
  taskId?: string;
  onSubmit: (payload: {
    explicitScore?: number;
    corrections?: string;
    implicitSignals: Record<string, unknown>;
  }) => Promise<void>;
}

export function FeedbackCenter({ taskId, onSubmit }: FeedbackCenterProps) {
  const [explicitScore, setExplicitScore] = useState(0.92);
  const [corrections, setCorrections] = useState("Need tighter risk analysis in final output.");
  const [retryCount, setRetryCount] = useState(0);
  const [editDistance, setEditDistance] = useState(0.12);
  const [adoptionRate, setAdoptionRate] = useState(0.87);

  const submit = async () => {
    await onSubmit({
      explicitScore,
      corrections,
      implicitSignals: {
        retryCount,
        editDistance,
        adoptionRate
      }
    });
  };

  return (
    <section className="panel">
      <header className="panel-title-row">
        <h2>Feedback Center</h2>
        <span className="badge">{taskId ? "task bound" : "no task"}</span>
      </header>
      <div className="field">
        <label>Explicit Score</label>
        <input
          type="number"
          step={0.01}
          min={0}
          max={1}
          value={explicitScore}
          onChange={(e) => setExplicitScore(Number(e.target.value))}
        />
      </div>
      <div className="field">
        <label>Corrections</label>
        <textarea value={corrections} rows={3} onChange={(e) => setCorrections(e.target.value)} />
      </div>
      <div className="row">
        <div className="field">
          <label>Retry Count</label>
          <input type="number" min={0} value={retryCount} onChange={(e) => setRetryCount(Number(e.target.value))} />
        </div>
        <div className="field">
          <label>Edit Distance</label>
          <input
            type="number"
            step={0.01}
            min={0}
            max={1}
            value={editDistance}
            onChange={(e) => setEditDistance(Number(e.target.value))}
          />
        </div>
        <div className="field">
          <label>Adoption Rate</label>
          <input
            type="number"
            step={0.01}
            min={0}
            max={1}
            value={adoptionRate}
            onChange={(e) => setAdoptionRate(Number(e.target.value))}
          />
        </div>
      </div>
      <button className="button button-primary" onClick={submit} disabled={!taskId}>
        Submit Feedback
      </button>
    </section>
  );
}
