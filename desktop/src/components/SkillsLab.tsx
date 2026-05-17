import { useMemo, useState } from "react";
import { SkillCard } from "../types";

interface SkillsLabProps {
  skills: SkillCard[];
  onCreateCandidate: (skillId: string) => Promise<void>;
  onPromoteCandidate: (skillId: string, candidateId: string) => Promise<void>;
  onShadowReplay: (skillId: string, candidateId: string) => Promise<void>;
  onCanaryStatus: (skillId: string, candidateId: string) => Promise<void>;
  onRollback: (skillId: string, reason: string) => Promise<void>;
}

export function SkillsLab({
  skills,
  onCreateCandidate,
  onPromoteCandidate,
  onShadowReplay,
  onCanaryStatus,
  onRollback
}: SkillsLabProps) {
  const [selectedSkillId, setSelectedSkillId] = useState<string>("");
  const [candidateId, setCandidateId] = useState("");
  const [reason, setReason] = useState("manual rollback for risk control");

  const selectedSkill = useMemo(
    () => skills.find((skill) => skill.id === selectedSkillId) ?? skills[0],
    [selectedSkillId, skills]
  );

  return (
    <section className="panel">
      <header className="panel-title-row">
        <h2>Skills Lab</h2>
        <span className="badge">{skills.length} skills</span>
      </header>
      <div className="field">
        <label>Skill</label>
        <select value={selectedSkill?.id ?? ""} onChange={(e) => setSelectedSkillId(e.target.value)}>
          {skills.map((skill) => (
            <option key={skill.id} value={skill.id}>
              {skill.id} (v{skill.version})
            </option>
          ))}
        </select>
      </div>
      {selectedSkill && (
        <div className="hint">
          <strong>{selectedSkill.name}</strong> - {selectedSkill.description}
        </div>
      )}
      <div className="row">
        <button className="button" onClick={() => selectedSkill && onCreateCandidate(selectedSkill.id)} disabled={!selectedSkill}>
          Create Candidate
        </button>
        <button
          className="button"
          onClick={() => selectedSkill && onPromoteCandidate(selectedSkill.id, candidateId)}
          disabled={!selectedSkill || !candidateId}
        >
          Promote Candidate
        </button>
      </div>
      <div className="row">
        <button
          className="button"
          onClick={() => selectedSkill && onShadowReplay(selectedSkill.id, candidateId)}
          disabled={!selectedSkill || !candidateId}
        >
          Shadow Replay
        </button>
        <button
          className="button"
          onClick={() => selectedSkill && onCanaryStatus(selectedSkill.id, candidateId)}
          disabled={!selectedSkill || !candidateId}
        >
          Canary Status
        </button>
      </div>
      <div className="field">
        <label>Candidate ID</label>
        <input value={candidateId} onChange={(e) => setCandidateId(e.target.value)} placeholder="paste candidate id" />
      </div>
      <div className="field">
        <label>Rollback Reason</label>
        <input value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <button className="button button-warning" onClick={() => selectedSkill && onRollback(selectedSkill.id, reason)} disabled={!selectedSkill}>
        Rollback Skill
      </button>
    </section>
  );
}


