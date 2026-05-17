import { EvolutionEventView, TaskDetail } from "../types";

interface SwarmPanelProps {
  latestTask?: TaskDetail;
  events: EvolutionEventView[];
}

const roleMap: Array<{ role: string; topic: string; label: string }> = [
  { role: "Scout", topic: "scout.reported", label: "Recon complete" },
  { role: "Worker", topic: "worker.planned", label: "Plan graph generated" },
  { role: "Worker", topic: "worker.completed", label: "Execution completed" },
  { role: "Worm", topic: "worm.proposed", label: "Skill delta proposed" },
  { role: "Queen", topic: "queen.promoted", label: "Candidate promoted" }
];

export function SwarmPanel({ latestTask, events }: SwarmPanelProps) {
  const byTopic = new Set(events.map((e) => e.topic));

  return (
    <section className="panel">
      <header className="panel-title-row">
        <h2>Swarm Situational Panel</h2>
        <span className="badge">{events.length} events</span>
      </header>
      <div className="swarm-grid">
        {roleMap.map((item) => (
          <article key={`${item.role}-${item.topic}`} className={`agent-card ${byTopic.has(item.topic) ? "agent-live" : ""}`}>
            <p className="agent-role">{item.role}</p>
            <p className="agent-label">{item.label}</p>
            <p className="agent-topic">{item.topic}</p>
          </article>
        ))}
      </div>
      <p className="hint">Current task: {latestTask ? `${latestTask.id} (${latestTask.status})` : "none"}</p>
    </section>
  );
}
