import {
  AutoFeedbackResponse,
  CandidateStatusAuditView,
  CanaryStatusResponse,
  CandidateResponse,
  CreateSkillFactoryPayload,
  DeliverableOpenResponse,
  ConversationTurn,
  EvolutionEventView,
  FeedbackPacket,
  HardeningReportResponse,
  ScoutPatrolResponse,
  ScoutPheromoneView,
  LlmConfigPatch,
  LlmConfigView,
  LlmTokenStatsResponse,
  ShadowReplayResponse,
  SkillCard,
  SkillDelta,
  TaskDetail,
  TaskSpec
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const CONTROL_PLANE_API_KEY = import.meta.env.VITE_CONTROL_PLANE_API_KEY;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      "X-User": "desktop-user",
      ...(CONTROL_PLANE_API_KEY ? { "X-API-Key": CONTROL_PLANE_API_KEY } : {}),
      ...(init?.headers ?? {})
    },
    ...init
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as T;
}

export function createTask(spec: TaskSpec, runAsync = false): Promise<TaskDetail> {
  return request<TaskDetail>("/tasks", {
    method: "POST",
    body: JSON.stringify({
      spec,
      runAsync
    })
  });
}

export function getTask(taskId: string): Promise<TaskDetail> {
  return request<TaskDetail>(`/tasks/${taskId}`);
}

export function submitFeedback(taskId: string, feedback: FeedbackPacket): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/tasks/${taskId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ feedback })
  });
}

export function autoFeedback(
  taskId: string,
  turns: ConversationTurn[],
  onlyIfMissing = true,
  source = "ui-auto"
): Promise<AutoFeedbackResponse> {
  return request<AutoFeedbackResponse>(`/tasks/${taskId}/auto-feedback`, {
    method: "POST",
    body: JSON.stringify({
      turns,
      onlyIfMissing,
      source
    })
  });
}

export function ensureEvolution(
  taskId: string,
  onlyIfMissing = true,
  source = "self-evolution-guard"
): Promise<AutoFeedbackResponse> {
  return request<AutoFeedbackResponse>(`/tasks/${taskId}/ensure-evolution`, {
    method: "POST",
    body: JSON.stringify({
      onlyIfMissing,
      source
    })
  });
}

export function listSkills(): Promise<SkillCard[]> {
  return request<SkillCard[]>("/skills");
}

export function createSkillCandidate(
  skillId: string,
  delta: SkillDelta
): Promise<CandidateResponse> {
  return request<CandidateResponse>(`/skills/${skillId}/candidate`, {
    method: "POST",
    body: JSON.stringify({ delta })
  });
}

export function createSkillFromFactory(payload: CreateSkillFactoryPayload): Promise<SkillCard> {
  return request<SkillCard>("/skills/factory", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function promoteCandidate(
  skillId: string,
  candidateId: string
): Promise<{ candidateId: string; status: string; decision: string; reason: string }> {
  return request(`/skills/${skillId}/promote`, {
    method: "POST",
    body: JSON.stringify({ candidateId, approvedBy: "queen-desktop" })
  });
}

export function rollbackSkill(skillId: string, reason: string): Promise<SkillCard> {
  return request<SkillCard>(`/skills/${skillId}/rollback`, {
    method: "POST",
    body: JSON.stringify({ reason, requestedBy: "queen-desktop" })
  });
}

export function listEvolutionEvents(): Promise<EvolutionEventView[]> {
  return request<EvolutionEventView[]>("/evolution/events?limit=50");
}

export function listScoutPheromones(limit = 40, onlyActive = true): Promise<ScoutPheromoneView[]> {
  const query = `/evolution/pheromones?limit=${limit}&onlyActive=${onlyActive}`;
  return request<ScoutPheromoneView[]>(query);
}

export function runScoutPatrol(sampleSize = 30): Promise<ScoutPatrolResponse> {
  return request<ScoutPatrolResponse>("/evolution/scout-patrol", {
    method: "POST",
    body: JSON.stringify({ sampleSize })
  });
}

export function listCandidateAudits(limit = 50): Promise<CandidateStatusAuditView[]> {
  return request<CandidateStatusAuditView[]>(`/evolution/candidate-audits?limit=${limit}`);
}

export function getHardeningReport(): Promise<HardeningReportResponse> {
  return request<HardeningReportResponse>("/evolution/hardening-report");
}

export function runAutoPromote(limit = 20): Promise<{
  total: number;
  promoted: number;
  rolledBack: number;
  validated: number;
  rejected: number;
  skipped: number;
}> {
  return request("/evolution/auto-promote", {
    method: "POST",
    body: JSON.stringify({ limit, approvedBy: "queen-auto-desktop" })
  });
}

export function evaluateShadowReplay(
  skillId: string,
  candidateId: string,
  sampleSize = 50
): Promise<ShadowReplayResponse> {
  return request<ShadowReplayResponse>(`/skills/${skillId}/candidate/${candidateId}/shadow-replay`, {
    method: "POST",
    body: JSON.stringify({ sampleSize })
  });
}

export function getCanaryStatus(skillId: string, candidateId: string): Promise<CanaryStatusResponse> {
  return request<CanaryStatusResponse>(`/skills/${skillId}/candidate/${candidateId}/canary-status`);
}

export function getLlmConfig(): Promise<LlmConfigView> {
  return request<LlmConfigView>("/llm/config");
}

export function updateLlmConfig(patch: LlmConfigPatch): Promise<LlmConfigView> {
  return request<LlmConfigView>("/llm/config", {
    method: "PUT",
    body: JSON.stringify(patch)
  });
}

export function getLlmTokenStats(limit = 300): Promise<LlmTokenStatsResponse> {
  return request<LlmTokenStatsResponse>(`/llm/token-stats?limit=${limit}`);
}

export function openDeliverable(taskId: string, mode: "file" | "folder", artifactPath?: string): Promise<DeliverableOpenResponse> {
  return request<DeliverableOpenResponse>(`/tasks/${taskId}/deliverables/open`, {
    method: "POST",
    body: JSON.stringify({
      mode,
      artifactPath: artifactPath ?? null
    })
  });
}

export async function downloadDeliverableFile(taskId: string, artifactPath?: string): Promise<{ blob: Blob; fileName: string }> {
  const query = artifactPath ? `?artifactPath=${encodeURIComponent(artifactPath)}` : "";
  const response = await fetch(`${API_BASE}/tasks/${taskId}/deliverables/download${query}`, {
    headers: {
      "X-User": "desktop-user",
      ...(CONTROL_PLANE_API_KEY ? { "X-API-Key": CONTROL_PLANE_API_KEY } : {})
    }
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename=\"?([^\";]+)\"?/i);
  const fileName = match?.[1] ?? "deliverable.bin";
  return { blob, fileName };
}

export async function downloadDeliverableArchive(taskId: string): Promise<{ blob: Blob; fileName: string }> {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/deliverables/archive`, {
    headers: {
      "X-User": "desktop-user",
      ...(CONTROL_PLANE_API_KEY ? { "X-API-Key": CONTROL_PLANE_API_KEY } : {})
    }
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename=\"?([^\";]+)\"?/i);
  const fileName = match?.[1] ?? "deliverables.zip";
  return { blob, fileName };
}
