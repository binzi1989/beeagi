export interface TaskSpec {
  goal: string;
  constraints: Record<string, unknown>;
  contextRefs: string[];
  qualityTarget: number;
  priority: number;
}

export interface TaskDetail {
  id: string;
  goal: string;
  status: string;
  priority: number;
  qualityTarget: number;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  scoutReport?: Record<string, unknown>;
  planGraph?: {
    nodes: Array<{ id: string; title: string; owner: string }>;
    edges: Array<{ from: string; to: string }>;
    riskFlags: string[];
  };
  resultPayload?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
}

export interface FeedbackPacket {
  explicitScore?: number;
  corrections?: string;
  implicitSignals: Record<string, unknown>;
}

export interface ConversationTurn {
  role: string;
  content: string;
}

export interface AutoFeedbackResponse {
  status: string;
  reason?: string;
  source: string;
  feedbackId?: string;
  candidateId?: string;
  skillId?: string;
  candidateStatus?: string;
  inferredFeedback?: FeedbackPacket;
}

export interface SkillCard {
  id: string;
  name: string;
  description: string;
  version: number;
  ioSchema: Record<string, unknown>;
  permissions: Record<string, unknown>;
  costBudget: Record<string, unknown>;
  config: Record<string, unknown>;
  status: string;
  updatedAt: string;
}

export interface SkillDelta {
  targetSkill: string;
  changeType: string;
  patch: Record<string, unknown>;
  evidence: Record<string, unknown>;
}

export interface CreateSkillFactoryPayload {
  skillId: string;
  name: string;
  description: string;
  baseStrategy?: string;
  mcpConnectors?: string[];
  ioSchema?: Record<string, unknown>;
  permissions?: Record<string, unknown>;
  costBudget?: Record<string, unknown>;
}

export interface CandidateResponse {
  id: string;
  skillId: string;
  status: string;
  shadowScore: number;
  canaryScore?: number;
  proposedDelta: Record<string, unknown>;
  evidence: Record<string, unknown>;
  createdAt: string;
}

export interface EvolutionEventView {
  id: string;
  topic: string;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface ScoutPheromoneView {
  id: string;
  intentCluster: string;
  source: string;
  route: string;
  novelty: number;
  reliability: number;
  cost: number;
  reward: number;
  strength: number;
  ttlSeconds: number;
  usageCount: number;
  successCount: number;
  failureCount: number;
  notes?: string;
  metadataJson: Record<string, unknown>;
  lastSeenAt: string;
  expiresAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface ScoutPatrolResponse {
  sampleSize: number;
  sampledTasks: number;
  touchedClusters: string[];
  deposited: number;
  evaporated: number;
  expired: number;
}

export interface CandidateStatusAuditView {
  id: string;
  candidateId: string;
  skillId: string;
  fromStatus?: string;
  toStatus: string;
  decision?: string;
  reason?: string;
  actor: string;
  context: Record<string, unknown>;
  createdAt: string;
}

export interface ShadowReplayResponse {
  candidateId: string;
  skillId: string;
  status: string;
  shadowScore: number;
  sampleSize: number;
  baselineAverage: number;
  candidateAverage: number;
  improvementRatio: number;
}

export interface CanaryStatusResponse {
  candidateId: string;
  skillId: string;
  status: string;
  canaryScore: number | null;
  feedbackCount: number;
  exposures: number;
  averageExplicitScore: number;
  averageErrorRateRise: number;
  averageAdoptionRate: number;
}

export interface HardeningCheck {
  id: string;
  level: string;
  message: string;
}

export interface HardeningSummary {
  skillCount: number;
  candidateCount: number;
  recentEventCount: number;
  recentAuditCount: number;
  waitingValidatedCandidates: number;
  eventBusBackend: string;
  apiKeyEnabled: boolean;
}

export interface HardeningReportResponse {
  generatedAt: string;
  overall: string;
  summary: HardeningSummary;
  checks: HardeningCheck[];
  missingTopics: string[];
}

export interface EvolutionTelemetryRoles {
  scoutEvents60M: number;
  workerEvents60M: number;
  wormEvents60M: number;
  queenEvents60M: number;
  feedbackEvents60M: number;
  systemEvents60M: number;
}

export interface EvolutionTelemetryFunnel {
  proposed: number;
  validated: number;
  promoted: number;
  rejected: number;
  rolledBack: number;
  totalCandidates: number;
  validationRatio: number;
  promotionRatio: number;
  rollbackRatio: number;
}

export interface EvolutionTelemetryTasks {
  total24H: number;
  completed24H: number;
  failed24H: number;
  successRate24H: number;
  avgDurationMs24H: number;
  tasksPerHour24H: number;
}

export interface EvolutionTelemetrySpeed {
  eventsLast5M: number;
  eventsPerMinute5M: number;
  proposalsLast60M: number;
  promotionsLast60M: number;
  rollbacksLast60M: number;
  patrolsLast60M: number;
  avgDecisionMinutes24H: number;
  progressScore: number;
  velocityScore: number;
}

export interface EvolutionTelemetryPoint {
  bucket: string;
  events: number;
  promotions: number;
  proposals: number;
}

export interface EvolutionTelemetryResponse {
  generatedAt: string;
  windowMinutes: number;
  activePheromones: number;
  roles: EvolutionTelemetryRoles;
  funnel: EvolutionTelemetryFunnel;
  tasks: EvolutionTelemetryTasks;
  speed: EvolutionTelemetrySpeed;
  timeline: EvolutionTelemetryPoint[];
}

export interface LlmConfigView {
  llmMode: string;
  llmModelName: string;
  localModelEndpoint: string;
  enterpriseModelEndpoint: string;
  deepseekEndpoint: string;
  deepseekModelName: string;
  llmTimeoutSeconds: number;
  llmApiKeyConfigured: boolean;
  deepseekApiKeyConfigured: boolean;
  runtimeConfigPath: string;
}

export interface LlmConfigPatch {
  llmMode?: string;
  llmModelName?: string;
  localModelEndpoint?: string;
  enterpriseModelEndpoint?: string;
  deepseekEndpoint?: string;
  deepseekModelName?: string;
  llmTimeoutSeconds?: number;
  llmApiKey?: string;
  deepseekApiKey?: string;
}

export interface LlmTokenModelStat {
  provider: string;
  model: string;
  taskCount: number;
  totalTokens: number;
  promptTokens: number;
  completionTokens: number;
  averageTokens: number;
}

export interface LlmTokenTaskStat {
  taskId: string;
  goal: string;
  provider: string;
  model: string;
  totalTokens: number;
  promptTokens: number;
  completionTokens: number;
  createdAt: string;
}

export interface LlmTokenStatsResponse {
  sampleSize: number;
  totalTasks: number;
  totalTokens: number;
  promptTokens: number;
  completionTokens: number;
  averageTokensPerTask: number;
  byModel: LlmTokenModelStat[];
  recentTasks: LlmTokenTaskStat[];
}

export interface DeliverableOpenResponse {
  taskId: string;
  mode: "file" | "folder";
  openedPath: string;
}
