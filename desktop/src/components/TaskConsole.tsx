import { useMemo, useState } from "react";
import { TaskDetail, TaskSpec } from "../types";

interface TaskConsoleProps {
  latestTask?: TaskDetail;
  onCreateTask: (spec: TaskSpec) => Promise<void>;
  busy: boolean;
}

export function TaskConsole({ latestTask, onCreateTask, busy }: TaskConsoleProps) {
  const [goal, setGoal] = useState("Design a go-to-market launch workflow for a new AI feature.");
  const [contextRefs, setContextRefs] = useState("doc://market-research,db://customer-segments");
  const [constraintsText, setConstraintsText] = useState('{"tone":"strategic","budget":"mid"}');
  const [constraintsError, setConstraintsError] = useState<string | null>(null);
  const [qualityTarget, setQualityTarget] = useState(0.9);
  const [priority, setPriority] = useState(2);

  const riskFlags = useMemo(() => latestTask?.planGraph?.riskFlags ?? [], [latestTask]);

  const createTask = async () => {
    let constraints: Record<string, unknown>;
    try {
      constraints = JSON.parse(constraintsText || "{}") as Record<string, unknown>;
      setConstraintsError(null);
    } catch {
      setConstraintsError("Constraints JSON is invalid. Please fix it before launching.");
      return;
    }
    const spec: TaskSpec = {
      goal,
      constraints,
      contextRefs: contextRefs
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      qualityTarget,
      priority
    };
    await onCreateTask(spec);
  };

  return (
    <section className="panel panel-tall">
      <header className="panel-title-row">
        <h2>Task Command Console</h2>
        <span className="badge">{latestTask?.status ?? "idle"}</span>
      </header>
      <div className="field">
        <label>Goal</label>
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={4} />
      </div>
      <div className="field">
        <label>Context Refs (comma separated)</label>
        <input value={contextRefs} onChange={(e) => setContextRefs(e.target.value)} />
      </div>
      <div className="field">
        <label>Constraints (JSON)</label>
        <textarea
          value={constraintsText}
          onChange={(e) => {
            setConstraintsText(e.target.value);
            if (constraintsError) {
              setConstraintsError(null);
            }
          }}
          rows={3}
        />
        {constraintsError && <p className="hint">{constraintsError}</p>}
      </div>
      <div className="row">
        <div className="field">
          <label>Quality Target</label>
          <input
            type="number"
            step={0.01}
            min={0.5}
            max={0.99}
            value={qualityTarget}
            onChange={(e) => setQualityTarget(Number(e.target.value))}
          />
        </div>
        <div className="field">
          <label>Priority</label>
          <input type="number" min={1} max={5} value={priority} onChange={(e) => setPriority(Number(e.target.value))} />
        </div>
      </div>
      <button className="button button-primary" onClick={createTask} disabled={busy}>
        {busy ? "Dispatching..." : "Launch Task"}
      </button>
      {latestTask?.planGraph && (
        <div className="plan-preview">
          <h3>Plan Graph</h3>
          <ol>
            {latestTask.planGraph.nodes.map((node) => (
              <li key={node.id}>{node.title}</li>
            ))}
          </ol>
          {riskFlags.length > 0 && <p className="hint">Risk Flags: {riskFlags.join(", ")}</p>}
        </div>
      )}
    </section>
  );
}
