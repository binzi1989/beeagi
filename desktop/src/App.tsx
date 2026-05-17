import { useEffect, useMemo, useState } from "react";
import {
  autoFeedback,
  createSkillCandidate,
  createTask,
  evaluateShadowReplay,
  getCanaryStatus,
  getHardeningReport,
  listCandidateAudits,
  listEvolutionEvents,
  listScoutPheromones,
  listSkills,
  promoteCandidate,
  rollbackSkill,
  runAutoPromote,
  runScoutPatrol,
  submitFeedback
} from "./api/client";
import {
  AutoFeedbackResponse,
  CandidateStatusAuditView,
  ConversationTurn,
  EvolutionEventView,
  HardeningReportResponse,
  ScoutPheromoneView,
  SkillCard,
  TaskDetail,
  TaskSpec
} from "./types";
import LlmConsolePage from "./components/LlmConsolePage";

type Locale = "zh" | "en";
type ScenarioId = "coding" | "office" | "research" | "debug" | "data" | "product";
type ChatRole = "user" | "swarm" | "deliverable" | "system";
type ViewMode = "workspace" | "llm";
type SideTab = "feedback" | "evolution" | "system";

type ScenarioTemplate = {
  id: ScenarioId;
  title: { zh: string; en: string };
  subtitle: { zh: string; en: string };
  flow: { zh: [string, string, string]; en: [string, string, string] };
  labels: {
    zh: { goal: string; context: string; constraints: string };
    en: { goal: string; context: string; constraints: string };
  };
  defaults: {
    goal: string;
    contextRefs: string;
    constraints: Record<string, unknown>;
    qualityTarget: number;
    priority: number;
    feedback: {
      explicitScore: number;
      corrections: string;
      retryCount: number;
      editDistance: number;
      adoptionRate: number;
      errorRateRise: number;
    };
  };
};

type ChatMessage = {
  id: string;
  role: ChatRole;
  title: string;
  text: string;
  time: string;
  taskId?: string;
};

const SCENARIOS: ScenarioTemplate[] = [
  {
    id: "coding",
    title: { zh: "编程场景", en: "Coding" },
    subtitle: { zh: "需求 / 代码上下文 / 验收标准", en: "Requirement / Code Context / Acceptance" },
    flow: { zh: ["实现", "评审", "修复"], en: ["Implement", "Review", "Fix"] },
    labels: {
      zh: {
        goal: "需求描述",
        context: "代码上下文（仓库路径、模块、接口）",
        constraints: "验收标准（JSON）"
      },
      en: {
        goal: "Requirement",
        context: "Code Context (repo/module/API)",
        constraints: "Acceptance Criteria (JSON)"
      }
    },
    defaults: {
      goal: "为用户管理页新增状态筛选与分页能力，并补齐单元测试。",
      contextRefs: "repo://frontend/src/pages/users,repo://backend/app/api/routes/users.py",
      constraints: {
        doneWhen: ["all tests pass", "lint clean", "api backward compatible"],
        output: "checklist",
        language: "zh-CN"
      },
      qualityTarget: 0.92,
      priority: 1,
      feedback: {
        explicitScore: 0.9,
        corrections: "请补充边界条件测试，并说明兼容性影响。",
        retryCount: 0,
        editDistance: 0.08,
        adoptionRate: 0.91,
        errorRateRise: 0
      }
    }
  },
  {
    id: "office",
    title: { zh: "办公场景", en: "Office" },
    subtitle: { zh: "目标 / 材料 / 输出格式", en: "Goal / Materials / Output" },
    flow: { zh: ["整理", "生成", "修订"], en: ["Organize", "Generate", "Revise"] },
    labels: {
      zh: {
        goal: "工作目标",
        context: "资料来源（文档、会议纪要、表格）",
        constraints: "输出格式要求（JSON）"
      },
      en: {
        goal: "Work Goal",
        context: "Materials (docs/notes/sheets)",
        constraints: "Output Format (JSON)"
      }
    },
    defaults: {
      goal: "整理本周项目进展并输出管理层简报。",
      contextRefs: "doc://weekly-notes,doc://meeting-minutes,sheet://progress-kpi",
      constraints: { output: "one-page brief", style: "executive", language: "zh-CN" },
      qualityTarget: 0.88,
      priority: 2,
      feedback: {
        explicitScore: 0.9,
        corrections: "请将风险和下周动作单独成段并排序。",
        retryCount: 0,
        editDistance: 0.1,
        adoptionRate: 0.9,
        errorRateRise: 0
      }
    }
  },
  {
    id: "research",
    title: { zh: "研究分析", en: "Research" },
    subtitle: { zh: "问题 / 数据源 / 结论格式", en: "Question / Data Source / Conclusion" },
    flow: { zh: ["检索", "分析", "结论"], en: ["Retrieve", "Analyze", "Conclude"] },
    labels: {
      zh: {
        goal: "研究问题",
        context: "数据来源（报告、数据库、访谈）",
        constraints: "结论输出格式（JSON）"
      },
      en: {
        goal: "Research Question",
        context: "Data Sources",
        constraints: "Conclusion Format (JSON)"
      }
    },
    defaults: {
      goal: "分析过去 3 个月活跃用户下滑的主要原因，并给出可执行假设。",
      contextRefs: "db://active-users,doc://churn-interviews,sheet://feature-usage",
      constraints: { include: ["hypothesis", "evidence", "confidence"], language: "zh-CN" },
      qualityTarget: 0.9,
      priority: 2,
      feedback: {
        explicitScore: 0.89,
        corrections: "请把证据链对应到每条假设，并补充置信度理由。",
        retryCount: 1,
        editDistance: 0.14,
        adoptionRate: 0.87,
        errorRateRise: 0
      }
    }
  },
  {
    id: "debug",
    title: { zh: "故障排查", en: "Debug" },
    subtitle: { zh: "现象 / 日志 / 验收", en: "Symptom / Logs / Acceptance" },
    flow: { zh: ["复现", "定位", "修复"], en: ["Reproduce", "Diagnose", "Fix"] },
    labels: {
      zh: {
        goal: "故障现象",
        context: "日志与调用链上下文",
        constraints: "修复验收标准（JSON）"
      },
      en: {
        goal: "Issue Symptom",
        context: "Logs and Trace Context",
        constraints: "Fix Acceptance (JSON)"
      }
    },
    defaults: {
      goal: "支付接口偶发超时，导致订单状态不一致。",
      contextRefs: "log://payment-service,trace://checkout-flow,repo://backend/payment",
      constraints: { doneWhen: ["timeout rate < 0.5%", "idempotency verified"], language: "zh-CN" },
      qualityTarget: 0.93,
      priority: 1,
      feedback: {
        explicitScore: 0.88,
        corrections: "请补充根因分析和回归检查清单。",
        retryCount: 1,
        editDistance: 0.2,
        adoptionRate: 0.84,
        errorRateRise: 0
      }
    }
  },
  {
    id: "data",
    title: { zh: "数据流程", en: "Data Workflow" },
    subtitle: { zh: "指标目标 / 数据口径 / 交付格式", en: "KPI / Data Spec / Delivery" },
    flow: { zh: ["清洗", "分析", "洞察"], en: ["Clean", "Analyze", "Insight"] },
    labels: {
      zh: {
        goal: "指标目标",
        context: "数据口径与表来源",
        constraints: "交付格式（JSON）"
      },
      en: {
        goal: "Metric Goal",
        context: "Data Sources",
        constraints: "Delivery Format (JSON)"
      }
    },
    defaults: {
      goal: "建立渠道转化漏斗并识别异常流失环节。",
      contextRefs: "db://traffic-events,db://order-events,sheet://channel-map",
      constraints: { output: "funnel+anomaly", granularity: "daily", language: "zh-CN" },
      qualityTarget: 0.9,
      priority: 2,
      feedback: {
        explicitScore: 0.9,
        corrections: "请增加异常阈值说明和可视化建议。",
        retryCount: 0,
        editDistance: 0.1,
        adoptionRate: 0.9,
        errorRateRise: 0
      }
    }
  },
  {
    id: "product",
    title: { zh: "产品方案", en: "Product Design" },
    subtitle: { zh: "背景 / 痛点 / 成功指标", en: "Background / Pain / Success Metrics" },
    flow: { zh: ["梳理", "设计", "拆解"], en: ["Clarify", "Design", "Breakdown"] },
    labels: {
      zh: {
        goal: "产品目标",
        context: "用户与业务背景",
        constraints: "验收指标（JSON）"
      },
      en: {
        goal: "Product Goal",
        context: "User and Business Context",
        constraints: "Success Metrics (JSON)"
      }
    },
    defaults: {
      goal: "优化新用户注册转化，降低首日流失。",
      contextRefs: "doc://user-research,db://signup-funnel,doc://competitor-notes",
      constraints: { include: ["milestones", "risk", "owners"], language: "zh-CN" },
      qualityTarget: 0.89,
      priority: 2,
      feedback: {
        explicitScore: 0.88,
        corrections: "请补充资源评估和上线依赖。",
        retryCount: 0,
        editDistance: 0.12,
        adoptionRate: 0.88,
        errorRateRise: 0
      }
    }
  }
];

const UI = {
  zh: {
    title: "BeeAGI 任务工作台",
    subtitle: "像聊天一样规划任务，稳定交付结果，再把反馈转成自动进化。",
    language: "语言",
    workspace: "工作台",
    llmPage: "模型与 Token",
    scenario: "场景",
    flow: "流程",
    taskInput: "任务输入",
    runTask: "执行当前轮",
    runFlow: "一键跑完整流程",
    running: "执行中...",
    applyTemplate: "应用模板",
    clearInput: "清空输入",
    qualityTarget: "质量目标",
    priority: "优先级",
    invalidJson: "JSON 格式错误，请先修正。",
    latestTask: "最近任务",
    noTask: "暂无任务",
    chatTimeline: "对话式时间线",
    emptyChat: "先执行一次任务，这里会生成完整过程记录。",
    deliverable: "交付产物",
    deliverableEmpty: "任务完成后，这里会展示可直接使用的结果。",
    llmSummary: "模型补充说明",
    copy: "复制结果",
    copied: "已复制到剪贴板",
    quickAccept: "直接采纳",
    quickRefine: "需要优化",
    quickRefineDefault: "请聚焦关键风险并给出可执行顺序。",
    rightFeedback: "反馈",
    autoFeedback: "自动感知反馈（推荐）",
    autoFeedbackHint: "用户忘记手动反馈时，可从对话推断反馈并触发进化。",
    runAutoFeedback: "立即自动反馈",
    autoFeedbackState: "自动反馈状态",
    submitFeedback: "提交手动反馈",
    explicitScore: "显式评分",
    corrections: "修正建议",
    retryCount: "重试次数",
    editDistance: "编辑幅度",
    adoptionRate: "采纳率",
    errorRateRise: "错误率上升",
    sideTabFeedback: "反馈",
    sideTabEvolution: "进化",
    sideTabSystem: "系统",
    swarm: "蜂群表现",
    roleAction: "最近动作",
    roleAt: "时间",
    pheromones: "Scout 信息素",
    runPatrol: "运行巡检",
    patrolling: "巡检中...",
    noPheromone: "暂无活跃信息素",
    rightControl: "进化控制",
    skill: "技能",
    candidateId: "候选 ID",
    createCandidate: "创建候选",
    shadowReplay: "影子回放",
    canaryStatus: "灰度状态",
    promote: "晋升候选",
    rollbackReason: "回滚原因",
    rollback: "回滚技能",
    rightHealth: "系统体检",
    refresh: "刷新",
    runHealth: "运行体检",
    healthChecking: "体检中...",
    runAutoPromote: "自动晋升",
    noHealth: "尚未运行体检",
    events: "最近事件",
    audits: "最近审计",
    workflowLog: "流程日志",
    noWorkflowLog: "暂无日志",
    autoFeedbackDone: "已自动生成反馈并推进技能进化。",
    autoFeedbackSkipped: "已存在反馈，自动反馈本轮跳过。",
    advanced: "高级设置"
  },
  en: {
    title: "BeeAGI Task Studio",
    subtitle: "Plan in chat style, ship clear deliverables, and evolve from real feedback.",
    language: "Language",
    workspace: "Workspace",
    llmPage: "LLM & Tokens",
    scenario: "Scenario",
    flow: "Flow",
    taskInput: "Task Input",
    runTask: "Run This Round",
    runFlow: "Run Full Workflow",
    running: "Running...",
    applyTemplate: "Apply Template",
    clearInput: "Clear Input",
    qualityTarget: "Quality Target",
    priority: "Priority",
    invalidJson: "Invalid JSON. Please fix it first.",
    latestTask: "Latest Task",
    noTask: "No task yet",
    chatTimeline: "Chat Timeline",
    emptyChat: "Run one task to generate a full timeline.",
    deliverable: "Deliverable",
    deliverableEmpty: "Final output appears here after execution.",
    llmSummary: "Model Notes",
    copy: "Copy",
    copied: "Copied to clipboard",
    quickAccept: "Accept",
    quickRefine: "Needs Refinement",
    quickRefineDefault: "Please focus on key risks and provide an actionable order.",
    rightFeedback: "Feedback",
    autoFeedback: "Auto infer feedback (Recommended)",
    autoFeedbackHint: "If users skip feedback, infer it from conversation and evolve automatically.",
    runAutoFeedback: "Run Auto Feedback",
    autoFeedbackState: "Auto Feedback Status",
    submitFeedback: "Submit Manual Feedback",
    explicitScore: "Explicit Score",
    corrections: "Corrections",
    retryCount: "Retry Count",
    editDistance: "Edit Distance",
    adoptionRate: "Adoption Rate",
    errorRateRise: "Error Rate Rise",
    sideTabFeedback: "Feedback",
    sideTabEvolution: "Evolution",
    sideTabSystem: "System",
    swarm: "Swarm Performance",
    roleAction: "Latest action",
    roleAt: "Time",
    pheromones: "Scout Pheromones",
    runPatrol: "Run Patrol",
    patrolling: "Patrolling...",
    noPheromone: "No active pheromones",
    rightControl: "Evolution Control",
    skill: "Skill",
    candidateId: "Candidate ID",
    createCandidate: "Create Candidate",
    shadowReplay: "Shadow Replay",
    canaryStatus: "Canary Status",
    promote: "Promote",
    rollbackReason: "Rollback Reason",
    rollback: "Rollback",
    rightHealth: "System Health",
    refresh: "Refresh",
    runHealth: "Run Health Check",
    healthChecking: "Checking...",
    runAutoPromote: "Auto Promote",
    noHealth: "No health report yet",
    events: "Recent Events",
    audits: "Recent Audits",
    workflowLog: "Workflow Logs",
    noWorkflowLog: "No logs yet",
    autoFeedbackDone: "Auto feedback submitted and evolution candidate generated.",
    autoFeedbackSkipped: "Feedback already exists. Auto feedback skipped.",
    advanced: "Advanced Settings"
  }
} as const;

const ROLE_CONFIG = [
  { key: "scout", topic: "scout.reported", name: { zh: "Scout（侦察）", en: "Scout" } },
  { key: "worker-plan", topic: "worker.planned", name: { zh: "Worker（规划）", en: "Worker Plan" } },
  { key: "worker-exec", topic: "worker.completed", name: { zh: "Worker（执行）", en: "Worker Exec" } },
  { key: "worm", topic: "worm.proposed", name: { zh: "Worm（进化提案）", en: "Worm" } },
  { key: "queen", topic: "queen.promoted", name: { zh: "Queen（治理）", en: "Queen" } }
] as const;

function errorText(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function toTimeLabel(isoTime: string): string {
  return new Date(isoTime).toLocaleTimeString();
}

function actionLabel(topic: string, locale: Locale): string {
  const zhMap: Record<string, string> = {
    "scout.reported": "完成侦察",
    "worker.planned": "完成计划图",
    "worker.completed": "完成执行",
    "feedback.received": "收到反馈",
    "feedback.auto_inferred": "自动推断反馈",
    "worm.proposed": "生成进化候选",
    "shadow.evaluated": "影子回放完成",
    "canary.assigned": "进入灰度流量",
    "canary.observed": "记录灰度反馈",
    "queen.promoted": "候选晋升",
    "queen.rolled_back": "触发回滚",
    "scout.pheromone_deposited": "信息素沉积",
    "scout.pheromone_evaporated": "信息素蒸发",
    "scout.patrolled": "完成巡检"
  };
  const enMap: Record<string, string> = {
    "scout.reported": "Recon complete",
    "worker.planned": "Plan generated",
    "worker.completed": "Execution complete",
    "feedback.received": "Feedback received",
    "feedback.auto_inferred": "Feedback auto-inferred",
    "worm.proposed": "Candidate proposed",
    "shadow.evaluated": "Shadow replay complete",
    "canary.assigned": "Canary assigned",
    "canary.observed": "Canary observed",
    "queen.promoted": "Candidate promoted",
    "queen.rolled_back": "Rollback triggered",
    "scout.pheromone_deposited": "Pheromone deposited",
    "scout.pheromone_evaporated": "Pheromone evaporated",
    "scout.patrolled": "Scout patrol complete"
  };
  return locale === "zh" ? zhMap[topic] ?? topic : enMap[topic] ?? topic;
}

function App() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [view, setView] = useState<ViewMode>("workspace");
  const [sideTab, setSideTab] = useState<SideTab>("feedback");
  const ui = UI[locale];

  const [scenarioId, setScenarioId] = useState<ScenarioId>("coding");
  const [goal, setGoal] = useState("");
  const [contextRefs, setContextRefs] = useState("");
  const [constraintsText, setConstraintsText] = useState("{}");
  const [constraintsError, setConstraintsError] = useState("");
  const [qualityTarget, setQualityTarget] = useState(0.9);
  const [priority, setPriority] = useState(2);

  const [explicitScore, setExplicitScore] = useState(0.9);
  const [corrections, setCorrections] = useState("");
  const [retryCount, setRetryCount] = useState(0);
  const [editDistance, setEditDistance] = useState(0.1);
  const [adoptionRate, setAdoptionRate] = useState(0.9);
  const [errorRateRise, setErrorRateRise] = useState(0);
  const [autoInferFeedbackEnabled, setAutoInferFeedbackEnabled] = useState(true);
  const [autoFeedbackState, setAutoFeedbackState] = useState("");

  const [skills, setSkills] = useState<SkillCard[]>([]);
  const [events, setEvents] = useState<EvolutionEventView[]>([]);
  const [audits, setAudits] = useState<CandidateStatusAuditView[]>([]);
  const [pheromones, setPheromones] = useState<ScoutPheromoneView[]>([]);
  const [hardeningReport, setHardeningReport] = useState<HardeningReportResponse>();
  const [latestTask, setLatestTask] = useState<TaskDetail>();
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);

  const [selectedSkillId, setSelectedSkillId] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [rollbackReason, setRollbackReason] = useState("manual rollback for risk control");

  const [toast, setToast] = useState("");
  const [busy, setBusy] = useState(false);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [healthBusy, setHealthBusy] = useState(false);
  const [patrolBusy, setPatrolBusy] = useState(false);
  const [workflowLogs, setWorkflowLogs] = useState<string[]>([]);

  const scenario = useMemo(() => SCENARIOS.find((item) => item.id === scenarioId) ?? SCENARIOS[0], [scenarioId]);
  const labels = scenario.labels[locale];
  const flow = scenario.flow[locale];

  const selectedSkill = useMemo(() => {
    if (skills.length === 0) {
      return undefined;
    }
    return skills.find((item) => item.id === selectedSkillId) ?? skills[0];
  }, [skills, selectedSkillId]);

  const outputSummary = useMemo(() => {
    const payload = latestTask?.resultPayload;
    if (!payload) {
      return "";
    }
    const text = payload.summary;
    return typeof text === "string" ? text : "";
  }, [latestTask]);

  const llmSummary = useMemo(() => {
    const payload = latestTask?.resultPayload;
    if (!payload) {
      return "";
    }
    const text = payload.llmSummary;
    return typeof text === "string" ? text : "";
  }, [latestTask]);

  const roleStats = useMemo(
    () =>
      ROLE_CONFIG.map((role) => {
        const latest = events.find((event) => event.topic === role.topic);
        const count = events.filter((event) => event.topic === role.topic).length;
        return { role, latest, count };
      }),
    [events]
  );

  const applyTemplate = (scene: ScenarioTemplate) => {
    setGoal(scene.defaults.goal);
    setContextRefs(scene.defaults.contextRefs);
    setConstraintsText(JSON.stringify(scene.defaults.constraints, null, 2));
    setQualityTarget(scene.defaults.qualityTarget);
    setPriority(scene.defaults.priority);
    setExplicitScore(scene.defaults.feedback.explicitScore);
    setCorrections(scene.defaults.feedback.corrections);
    setRetryCount(scene.defaults.feedback.retryCount);
    setEditDistance(scene.defaults.feedback.editDistance);
    setAdoptionRate(scene.defaults.feedback.adoptionRate);
    setErrorRateRise(scene.defaults.feedback.errorRateRise);
    setConstraintsError("");
  };

  const clearTaskInput = () => {
    setGoal("");
    setContextRefs("");
    setConstraintsText("{}");
    setConstraintsError("");
  };

  const refreshData = async () => {
    const [skillsData, eventsData, auditsData, pheromoneData] = await Promise.all([
      listSkills(),
      listEvolutionEvents(),
      listCandidateAudits(40),
      listScoutPheromones(30, true)
    ]);
    setSkills(skillsData);
    setEvents(eventsData);
    setAudits(auditsData);
    setPheromones(pheromoneData);
  };

  useEffect(() => {
    refreshData().catch((error) => setToast(errorText(error)));
    applyTemplate(scenario);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedSkillId && skills.length > 0) {
      setSelectedSkillId(skills[0].id);
    }
  }, [skills, selectedSkillId]);

  const parseConstraints = (): Record<string, unknown> | null => {
    try {
      const parsed = JSON.parse(constraintsText || "{}") as Record<string, unknown>;
      setConstraintsError("");
      return parsed;
    } catch {
      setConstraintsError(ui.invalidJson);
      return null;
    }
  };

  const buildContextRefs = () =>
    contextRefs
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

  const appendWorkflowLog = (message: string) => {
    setWorkflowLogs((prev) => [message, ...prev].slice(0, 80));
  };

  const appendChat = (payload: Omit<ChatMessage, "id">) => {
    setChatMessages((prev) => [
      ...prev,
      {
        ...payload,
        id: `${payload.role}-${Date.now()}-${Math.random().toString(16).slice(2)}`
      }
    ]);
  };

  const buildDeliverableText = (task: TaskDetail): string => {
    const lines: string[] = [];
    const summary = typeof task.resultPayload?.summary === "string" ? task.resultPayload.summary : "";
    if (summary) {
      lines.push(summary);
    }
    const llm = typeof task.resultPayload?.llmSummary === "string" ? task.resultPayload.llmSummary : "";
    if (llm) {
      lines.push(llm);
    }
    const nodes = task.planGraph?.nodes ?? [];
    if (nodes.length > 0) {
      lines.push(nodes.map((node) => `- ${node.title}`).join("\n"));
    }
    if (lines.length === 0) {
      lines.push(task.goal);
    }
    return lines.join("\n\n");
  };

  const buildTurnsForAutoFeedback = (task: TaskDetail): ConversationTurn[] => {
    const taskMessages = chatMessages.filter((item) => item.taskId === task.id);
    const turns: ConversationTurn[] = taskMessages.map((item) => ({
      role: item.role === "user" ? "user" : "assistant",
      content: `${item.title}\n${item.text}`.trim()
    }));
    if (turns.length === 0) {
      turns.push({ role: "user", content: task.goal });
      turns.push({ role: "assistant", content: buildDeliverableText(task) });
    }
    return turns.slice(-16);
  };

  const applyAutoFeedback = async (task: TaskDetail, source: string, overrideTurns?: ConversationTurn[]) => {
    const turns = overrideTurns && overrideTurns.length > 0 ? overrideTurns : buildTurnsForAutoFeedback(task);
    const result: AutoFeedbackResponse = await autoFeedback(task.id, turns, true, source);
    setAutoFeedbackState(result.status);

    if (result.status === "submitted") {
      if (result.candidateId) {
        setCandidateId(result.candidateId);
      }
      appendWorkflowLog("auto-feedback: submitted");
      appendChat({
        role: "system",
        title: "Feedback",
        text: ui.autoFeedbackDone,
        time: new Date().toISOString(),
        taskId: task.id
      });
      setToast(ui.autoFeedbackDone);
      return;
    }

    appendWorkflowLog(`auto-feedback: ${result.reason ?? "skipped"}`);
    appendChat({
      role: "system",
      title: "Feedback",
      text: ui.autoFeedbackSkipped,
      time: new Date().toISOString(),
      taskId: task.id
    });
    setToast(ui.autoFeedbackSkipped);
  };

  const runTaskRound = async () => {
    const constraints = parseConstraints();
    if (!constraints) {
      return;
    }

    appendChat({
      role: "user",
      title: scenario.title[locale],
      text: `${labels.goal}: ${goal}\n${labels.context}: ${contextRefs}`,
      time: new Date().toISOString()
    });

    try {
      setBusy(true);
      const spec: TaskSpec = {
        goal,
        constraints,
        contextRefs: buildContextRefs(),
        qualityTarget,
        priority
      };
      const task = await createTask(spec, false);
      setLatestTask(task);
      appendChat({
        role: "swarm",
        title: flow[0],
        text: typeof task.resultPayload?.summary === "string" ? task.resultPayload.summary : task.goal,
        time: task.createdAt,
        taskId: task.id
      });
      appendChat({
        role: "deliverable",
        title: ui.deliverable,
        text: buildDeliverableText(task),
        time: task.updatedAt,
        taskId: task.id
      });

      if (autoInferFeedbackEnabled) {
        const autoTurns: ConversationTurn[] = [
          { role: "user", content: `${labels.goal}: ${goal}\n${labels.context}: ${contextRefs}` },
          { role: "assistant", content: typeof task.resultPayload?.summary === "string" ? task.resultPayload.summary : task.goal },
          { role: "assistant", content: buildDeliverableText(task) }
        ];
        await applyAutoFeedback(task, "task-round", autoTurns);
      }

      await refreshData();
      appendWorkflowLog(`task: ${task.id}`);
      setToast(`OK: ${task.id}`);
    } catch (error) {
      setToast(errorText(error));
      appendWorkflowLog(`error: ${errorText(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const runScenarioFlow = async () => {
    const constraints = parseConstraints();
    if (!constraints) {
      return;
    }

    appendWorkflowLog(`start: ${scenario.title[locale]} | ${flow.join(" -> ")}`);
    appendChat({
      role: "user",
      title: scenario.title[locale],
      text: goal,
      time: new Date().toISOString()
    });

    try {
      setWorkflowBusy(true);
      let previousTask: TaskDetail | undefined;
      const flowTurns: ConversationTurn[] = [{ role: "user", content: goal }];

      for (let i = 0; i < flow.length; i += 1) {
        const step = flow[i];
        appendWorkflowLog(`step ${i + 1}/${flow.length}: ${step}`);

        const mergedConstraints = {
          ...constraints,
          scenarioId: scenario.id,
          scenarioStep: step,
          scenarioStepIndex: i + 1
        };

        const refs = buildContextRefs();
        if (previousTask) {
          refs.push(`task://${previousTask.id}`);
        }

        const task = await createTask(
          {
            goal: `${step}: ${goal}`,
            constraints: mergedConstraints,
            contextRefs: refs,
            qualityTarget,
            priority
          },
          false
        );

        previousTask = task;
        setLatestTask(task);
        appendChat({
          role: "swarm",
          title: step,
          text: typeof task.resultPayload?.summary === "string" ? task.resultPayload.summary : task.goal,
          time: task.updatedAt,
          taskId: task.id
        });
        flowTurns.push({
          role: "assistant",
          content: typeof task.resultPayload?.summary === "string" ? task.resultPayload.summary : task.goal
        });
        appendWorkflowLog(`done: ${step} | ${task.id}`);
      }

      if (previousTask) {
        appendChat({
          role: "deliverable",
          title: ui.deliverable,
          text: buildDeliverableText(previousTask),
          time: previousTask.updatedAt,
          taskId: previousTask.id
        });

        if (autoInferFeedbackEnabled) {
          flowTurns.push({ role: "assistant", content: buildDeliverableText(previousTask) });
          await applyAutoFeedback(previousTask, "scenario-flow", flowTurns);
        }
      }

      await refreshData();
      setToast(locale === "zh" ? "流程执行完成" : "Workflow completed");
    } catch (error) {
      setToast(errorText(error));
      appendWorkflowLog(`error: ${errorText(error)}`);
    } finally {
      setWorkflowBusy(false);
    }
  };

  const sendFeedback = async () => {
    if (!latestTask) {
      setToast(ui.noTask);
      return;
    }
    try {
      await submitFeedback(latestTask.id, {
        explicitScore,
        corrections,
        implicitSignals: { retryCount, editDistance, adoptionRate, errorRateRise }
      });
      setAutoFeedbackState("manual-submitted");
      await refreshData();
      appendWorkflowLog("manual feedback submitted");
      setToast(locale === "zh" ? "反馈已提交" : "Feedback submitted");
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const runAutoFeedbackNow = async () => {
    if (!latestTask) {
      setToast(ui.noTask);
      return;
    }
    try {
      await applyAutoFeedback(latestTask, "manual-trigger");
      await refreshData();
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const createCandidate = async () => {
    if (!selectedSkill) {
      return;
    }
    try {
      const candidate = await createSkillCandidate(selectedSkill.id, {
        targetSkill: selectedSkill.id,
        changeType: `${scenario.id}_manual`,
        patch: {
          promptTweaks: { scene: scenario.id, format: "structured-deliverable" },
          toolPolicy: { maxRetries: 2, preferLowRiskTools: true }
        },
        evidence: { source: "manual", scenarioId: scenario.id, ts: new Date().toISOString() }
      });
      setCandidateId(candidate.id);
      await refreshData();
      setToast(`candidate: ${candidate.id}`);
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const runReplay = async () => {
    if (!selectedSkill || !candidateId) {
      return;
    }
    try {
      const replay = await evaluateShadowReplay(selectedSkill.id, candidateId, 40);
      await refreshData();
      setToast(`replay ratio=${replay.improvementRatio.toFixed(3)}`);
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const checkCanary = async () => {
    if (!selectedSkill || !candidateId) {
      return;
    }
    try {
      const canary = await getCanaryStatus(selectedSkill.id, candidateId);
      setToast(`canary score=${(canary.canaryScore ?? 0).toFixed(3)}`);
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const promote = async () => {
    if (!selectedSkill || !candidateId) {
      return;
    }
    try {
      const result = await promoteCandidate(selectedSkill.id, candidateId);
      await refreshData();
      setToast(result.decision);
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const rollback = async () => {
    if (!selectedSkill) {
      return;
    }
    try {
      await rollbackSkill(selectedSkill.id, rollbackReason);
      await refreshData();
      setToast(locale === "zh" ? "回滚完成" : "Rollback completed");
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const patrolScout = async () => {
    try {
      setPatrolBusy(true);
      const result = await runScoutPatrol(30);
      appendWorkflowLog(`scout patrol sampled=${result.sampledTasks}, deposited=${result.deposited}`);
      await refreshData();
      setToast(locale === "zh" ? "巡检完成" : "Patrol completed");
    } catch (error) {
      setToast(errorText(error));
    } finally {
      setPatrolBusy(false);
    }
  };

  const runHealth = async () => {
    try {
      setHealthBusy(true);
      const report = await getHardeningReport();
      setHardeningReport(report);
      setToast(locale === "zh" ? "体检已更新" : "Health updated");
    } catch (error) {
      setToast(errorText(error));
    } finally {
      setHealthBusy(false);
    }
  };

  const autoPromote = async () => {
    try {
      const result = await runAutoPromote(30);
      await refreshData();
      setToast(`promoted=${result.promoted}, skipped=${result.skipped}`);
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const copyDeliverable = async () => {
    if (!latestTask) {
      return;
    }
    const text = buildDeliverableText(latestTask);
    if (!text) {
      return;
    }
    await navigator.clipboard.writeText(text);
    setToast(ui.copied);
  };

  const quickAcceptDeliverable = async () => {
    if (!latestTask) {
      setToast(ui.noTask);
      return;
    }
    try {
      await submitFeedback(latestTask.id, {
        explicitScore: 0.94,
        corrections: locale === "zh" ? "结果已采纳，保持当前风格。" : "Accepted. Keep this style.",
        implicitSignals: {
          retryCount: 0,
          editDistance: 0.06,
          adoptionRate: 0.96,
          errorRateRise: 0
        }
      });
      setAutoFeedbackState("manual-accepted");
      await refreshData();
      appendWorkflowLog("quick accept feedback submitted");
      setToast(locale === "zh" ? "已采纳并反馈" : "Accepted and feedback submitted");
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const quickRequestRefine = async () => {
    if (!latestTask) {
      setToast(ui.noTask);
      return;
    }
    try {
      await submitFeedback(latestTask.id, {
        explicitScore: 0.72,
        corrections: ui.quickRefineDefault,
        implicitSignals: {
          retryCount: 1,
          editDistance: 0.24,
          adoptionRate: 0.62,
          errorRateRise: 0.01
        }
      });
      setAutoFeedbackState("manual-refine-requested");
      await refreshData();
      appendWorkflowLog("quick refine feedback submitted");
      setToast(locale === "zh" ? "已提交优化请求" : "Refinement request submitted");
    } catch (error) {
      setToast(errorText(error));
    }
  };

  return (
    <div className="page">
      <header className="studio-header">
        <div className="studio-brand">
          <p className="brand">BeeAGI x Codex</p>
          <h1>{ui.title}</h1>
          <p className="subtitle">{ui.subtitle}</p>
        </div>
        <div className="studio-actions">
          <div className="switch-group">
            <button className={`switch ${view === "workspace" ? "switch-active" : ""}`} onClick={() => setView("workspace")}>
              {ui.workspace}
            </button>
            <button className={`switch ${view === "llm" ? "switch-active" : ""}`} onClick={() => setView("llm")}>
              {ui.llmPage}
            </button>
          </div>
          <div className="switch-group">
            <span>{ui.language}</span>
            <button className={`switch ${locale === "zh" ? "switch-active" : ""}`} onClick={() => setLocale("zh")}>
              中文
            </button>
            <button className={`switch ${locale === "en" ? "switch-active" : ""}`} onClick={() => setLocale("en")}>
              EN
            </button>
          </div>
        </div>
      </header>

      {toast && <div className="toast">{toast}</div>}

      {view === "workspace" ? (
        <div className="studio-layout">
          <aside className="scene-rail card">
            <div className="rail-head">
              <h2>{ui.scenario}</h2>
            </div>
            <div className="scene-list">
              {SCENARIOS.map((item) => (
                <button
                  key={item.id}
                  className={`scene-item ${item.id === scenarioId ? "scene-item-active" : ""}`}
                  onClick={() => {
                    setScenarioId(item.id);
                    applyTemplate(item);
                  }}
                >
                  <strong>{item.title[locale]}</strong>
                  <span>{item.subtitle[locale]}</span>
                  <small>
                    {ui.flow}: {item.flow[locale].join(" -> ")}
                  </small>
                </button>
              ))}
            </div>
            <div className="rail-divider" />
            <h3>{ui.swarm}</h3>
            <ul className="compact-list">
              {roleStats.map((item) => (
                <li key={item.role.key}>
                  {item.role.name[locale]}: {item.count}
                </li>
              ))}
            </ul>
          </aside>

          <main className="main-stage">
            <section className="card deliverable-hero">
              <div className="hero-head">
                <h2>{ui.deliverable}</h2>
                <span className="badge">
                  {ui.latestTask}: {latestTask ? latestTask.status : ui.noTask}
                </span>
              </div>

              {!latestTask ? (
                <p className="hint">{ui.deliverableEmpty}</p>
              ) : (
                <>
                  <p className="hint">ID: {latestTask.id}</p>
                  <p className="result-text">{outputSummary || latestTask.goal}</p>
                  {llmSummary && (
                    <p className="hint">
                      <strong>{ui.llmSummary}:</strong> {llmSummary}
                    </p>
                  )}
                  <div className="inline-actions">
                    <button className="button" onClick={copyDeliverable}>
                      {ui.copy}
                    </button>
                    <button className="button button-primary" onClick={quickAcceptDeliverable}>
                      {ui.quickAccept}
                    </button>
                    <button className="button" onClick={quickRequestRefine}>
                      {ui.quickRefine}
                    </button>
                  </div>
                </>
              )}
            </section>

            <section className="card timeline-card">
              <div className="hero-head">
                <h2>{ui.chatTimeline}</h2>
              </div>
              <div className="chat-timeline">
                {chatMessages.length === 0 && <p className="hint">{ui.emptyChat}</p>}
                {chatMessages.map((item) => (
                  <article key={item.id} className={`chat-row chat-row-${item.role}`}>
                    <div className={`bubble bubble-${item.role}`}>
                      <div className="bubble-head">
                        <strong>{item.title}</strong>
                        <span>{toTimeLabel(item.time)}</span>
                      </div>
                      <p>{item.text}</p>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="card composer-card">
              <div className="hero-head">
                <h2>{ui.taskInput}</h2>
                <div className="inline-actions">
                  <button className="button" onClick={() => applyTemplate(scenario)}>
                    {ui.applyTemplate}
                  </button>
                  <button className="button" onClick={clearTaskInput}>
                    {ui.clearInput}
                  </button>
                </div>
              </div>

              <label>{labels.goal}</label>
              <textarea rows={5} value={goal} onChange={(event) => setGoal(event.target.value)} placeholder={labels.goal} />

              <details className="advanced-box">
                <summary>{ui.advanced}</summary>
                <label>{labels.context}</label>
                <input value={contextRefs} onChange={(event) => setContextRefs(event.target.value)} placeholder="repo://...,doc://..." />

                <label>{labels.constraints}</label>
                <textarea
                  rows={5}
                  value={constraintsText}
                  onChange={(event) => {
                    setConstraintsText(event.target.value);
                    if (constraintsError) {
                      setConstraintsError("");
                    }
                  }}
                />
                {constraintsError && <p className="error">{constraintsError}</p>}

                <div className="row">
                  <div>
                    <label>{ui.qualityTarget}</label>
                    <input
                      type="number"
                      min={0.5}
                      max={0.99}
                      step={0.01}
                      value={qualityTarget}
                      onChange={(event) => setQualityTarget(Number(event.target.value))}
                    />
                  </div>
                  <div>
                    <label>{ui.priority}</label>
                    <input type="number" min={1} max={5} value={priority} onChange={(event) => setPriority(Number(event.target.value))} />
                  </div>
                </div>
              </details>

              <div className="composer-actions">
                <button className="button" onClick={runTaskRound} disabled={busy}>
                  {busy ? ui.running : ui.runTask}
                </button>
                <button className="button button-primary" onClick={runScenarioFlow} disabled={workflowBusy}>
                  {workflowBusy ? ui.running : ui.runFlow}
                </button>
              </div>
            </section>
          </main>

          <aside className="control-rail">
            <section className="card side-card">
              <div className="side-tab-row">
                <button className={`switch ${sideTab === "feedback" ? "switch-active" : ""}`} onClick={() => setSideTab("feedback")}>
                  {ui.sideTabFeedback}
                </button>
                <button className={`switch ${sideTab === "evolution" ? "switch-active" : ""}`} onClick={() => setSideTab("evolution")}>
                  {ui.sideTabEvolution}
                </button>
                <button className={`switch ${sideTab === "system" ? "switch-active" : ""}`} onClick={() => setSideTab("system")}>
                  {ui.sideTabSystem}
                </button>
              </div>
            </section>

            {sideTab === "feedback" && (
              <section className="card side-card">
                <h2>{ui.rightFeedback}</h2>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={autoInferFeedbackEnabled}
                    onChange={(event) => setAutoInferFeedbackEnabled(event.target.checked)}
                  />
                  <span>{ui.autoFeedback}</span>
                </label>
                <p className="hint">{ui.autoFeedbackHint}</p>
                <button className="button button-primary" onClick={runAutoFeedbackNow} disabled={!latestTask}>
                  {ui.runAutoFeedback}
                </button>
                <p className="hint">
                  {ui.autoFeedbackState}: {autoFeedbackState || "-"}
                </p>

                <details className="manual-feedback">
                  <summary>{ui.submitFeedback}</summary>
                  <label>{ui.explicitScore}</label>
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={explicitScore}
                    onChange={(event) => setExplicitScore(Number(event.target.value))}
                  />
                  <label>{ui.corrections}</label>
                  <textarea rows={3} value={corrections} onChange={(event) => setCorrections(event.target.value)} />
                  <label>{ui.retryCount}</label>
                  <input type="number" min={0} value={retryCount} onChange={(event) => setRetryCount(Number(event.target.value))} />
                  <label>{ui.editDistance}</label>
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={editDistance}
                    onChange={(event) => setEditDistance(Number(event.target.value))}
                  />
                  <label>{ui.adoptionRate}</label>
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={adoptionRate}
                    onChange={(event) => setAdoptionRate(Number(event.target.value))}
                  />
                  <label>{ui.errorRateRise}</label>
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={errorRateRise}
                    onChange={(event) => setErrorRateRise(Number(event.target.value))}
                  />
                  <button className="button" onClick={sendFeedback} disabled={!latestTask}>
                    {ui.submitFeedback}
                  </button>
                </details>
              </section>
            )}

            {sideTab === "evolution" && (
              <>
                <section className="card side-card">
                  <h2>{ui.swarm}</h2>
                  <ul className="compact-list">
                    {roleStats.map((item) => (
                      <li key={item.role.key}>
                        {item.role.name[locale]} · {item.count}
                        {item.latest && (
                          <span className="hint-block">
                            {ui.roleAction}: {actionLabel(item.latest.topic, locale)} · {ui.roleAt}: {toTimeLabel(item.latest.createdAt)}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>

                <section className="card side-card">
                  <h2>{ui.pheromones}</h2>
                  <button className="button" onClick={patrolScout} disabled={patrolBusy}>
                    {patrolBusy ? ui.patrolling : ui.runPatrol}
                  </button>
                  {pheromones.length === 0 ? (
                    <p className="hint">{ui.noPheromone}</p>
                  ) : (
                    <ul className="compact-list">
                      {pheromones.slice(0, 6).map((item) => (
                        <li key={item.id}>
                          {item.intentCluster} | {item.source} | s={item.strength.toFixed(2)} | use={item.usageCount}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                <section className="card side-card">
                  <h2>{ui.rightControl}</h2>
                  <label>{ui.skill}</label>
                  <select value={selectedSkill?.id ?? ""} onChange={(event) => setSelectedSkillId(event.target.value)}>
                    {skills.map((skill) => (
                      <option key={skill.id} value={skill.id}>
                        {skill.id} (v{skill.version})
                      </option>
                    ))}
                  </select>
                  <button className="button" onClick={createCandidate} disabled={!selectedSkill}>
                    {ui.createCandidate}
                  </button>
                  <label>{ui.candidateId}</label>
                  <input value={candidateId} onChange={(event) => setCandidateId(event.target.value)} />
                  <button className="button" onClick={runReplay} disabled={!selectedSkill || !candidateId}>
                    {ui.shadowReplay}
                  </button>
                  <button className="button" onClick={checkCanary} disabled={!selectedSkill || !candidateId}>
                    {ui.canaryStatus}
                  </button>
                  <button className="button" onClick={promote} disabled={!selectedSkill || !candidateId}>
                    {ui.promote}
                  </button>
                  <label>{ui.rollbackReason}</label>
                  <input value={rollbackReason} onChange={(event) => setRollbackReason(event.target.value)} />
                  <button className="button button-warning" onClick={rollback} disabled={!selectedSkill}>
                    {ui.rollback}
                  </button>
                </section>
              </>
            )}

            {sideTab === "system" && (
              <section className="card side-card">
                <h2>{ui.rightHealth}</h2>
                <div className="inline-actions">
                  <button className="button" onClick={() => refreshData().catch((error) => setToast(errorText(error)))}>
                    {ui.refresh}
                  </button>
                  <button className="button" onClick={autoPromote}>
                    {ui.runAutoPromote}
                  </button>
                  <button className="button button-primary" onClick={runHealth} disabled={healthBusy}>
                    {healthBusy ? ui.healthChecking : ui.runHealth}
                  </button>
                </div>
                <div className="report-box">
                  {hardeningReport ? (
                    <ul className="compact-list">
                      {hardeningReport.checks.slice(0, 5).map((check) => (
                        <li key={check.id}>
                          [{check.level.toUpperCase()}] {check.message}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="hint">{ui.noHealth}</p>
                  )}
                </div>

                <h3>{ui.workflowLog}</h3>
                {workflowLogs.length === 0 ? (
                  <p className="hint">{ui.noWorkflowLog}</p>
                ) : (
                  <ul className="compact-list">
                    {workflowLogs.slice(0, 8).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                )}

                <h3>{ui.events}</h3>
                <ul className="compact-list">
                  {events.slice(0, 6).map((event) => (
                    <li key={event.id}>
                      {toTimeLabel(event.createdAt)} | {actionLabel(event.topic, locale)}
                    </li>
                  ))}
                </ul>

                <h3>{ui.audits}</h3>
                <ul className="compact-list">
                  {audits.slice(0, 6).map((item) => (
                    <li key={item.id}>
                      {item.fromStatus ?? "-"} -&gt; {item.toStatus}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </aside>
        </div>
      ) : (
        <LlmConsolePage locale={locale} onToast={setToast} />
      )}
    </div>
  );
}

export default App;
