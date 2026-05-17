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
  listSkills,
  promoteCandidate,
  rollbackSkill,
  runAutoPromote,
  submitFeedback
} from "./api/client";
import {
  AutoFeedbackResponse,
  CandidateStatusAuditView,
  ConversationTurn,
  EvolutionEventView,
  HardeningReportResponse,
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
      zh: { goal: "需求描述", context: "代码上下文（仓库路径、模块、接口）", constraints: "验收标准（JSON）" },
      en: { goal: "Requirement", context: "Code Context (repo/module/API)", constraints: "Acceptance Criteria (JSON)" }
    },
    defaults: {
      goal: "为用户管理页面新增状态筛选与分页能力，并补齐单元测试。",
      contextRefs: "repo://frontend/src/pages/users,repo://backend/app/api/routes/users.py",
      constraints: {
        doneWhen: ["all tests pass", "lint clean", "api backward compatible"],
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
    title: { zh: "通用办公", en: "Office" },
    subtitle: { zh: "目标 / 资料 / 输出格式", en: "Goal / Material / Output Format" },
    flow: { zh: ["整理", "生成", "修订"], en: ["Organize", "Generate", "Revise"] },
    labels: {
      zh: { goal: "工作目标", context: "资料来源（文档、会议纪要、数据表）", constraints: "输出格式要求（JSON）" },
      en: { goal: "Work Goal", context: "Material Sources", constraints: "Output Format (JSON)" }
    },
    defaults: {
      goal: "整理本周项目进展并输出管理层简报。",
      contextRefs: "doc://weekly-notes,doc://meeting-minutes,sheet://progress-kpi",
      constraints: { output: "one-page brief", style: "executive", language: "zh-CN" },
      qualityTarget: 0.88,
      priority: 2,
      feedback: {
        explicitScore: 0.9,
        corrections: "请将风险与下周动作单独成段并排序。",
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
    subtitle: { zh: "问题 / 数据源 / 结论格式", en: "Question / Data Source / Conclusion Format" },
    flow: { zh: ["检索", "分析", "结论"], en: ["Retrieve", "Analyze", "Conclude"] },
    labels: {
      zh: { goal: "研究问题", context: "数据源（报告、数据库、访谈）", constraints: "结论输出格式（JSON）" },
      en: { goal: "Research Question", context: "Data Sources", constraints: "Conclusion Format (JSON)" }
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
    subtitle: { zh: "现象 / 日志上下文 / 修复验收", en: "Symptom / Logs / Acceptance" },
    flow: { zh: ["复现", "定位", "修复"], en: ["Reproduce", "Diagnose", "Fix"] },
    labels: {
      zh: { goal: "故障现象", context: "日志与调用链上下文", constraints: "修复验收标准（JSON）" },
      en: { goal: "Issue Symptom", context: "Logs & Trace Context", constraints: "Fix Acceptance (JSON)" }
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
    subtitle: { zh: "指标目标 / 数据口径 / 交付格式", en: "KPI / Data Spec / Delivery Format" },
    flow: { zh: ["清洗", "分析", "洞察"], en: ["Clean", "Analyze", "Insight"] },
    labels: {
      zh: { goal: "指标目标", context: "数据口径与表来源", constraints: "交付格式（JSON）" },
      en: { goal: "Metric Goal", context: "Data Sources", constraints: "Delivery Format (JSON)" }
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
    subtitle: { zh: "需求背景 / 用户痛点 / 验收指标", en: "Background / Pain Point / Success Metrics" },
    flow: { zh: ["需求梳理", "方案设计", "交付拆解"], en: ["Clarify", "Design", "Breakdown"] },
    labels: {
      zh: { goal: "产品目标", context: "用户与业务背景", constraints: "验收指标（JSON）" },
      en: { goal: "Product Goal", context: "User & Business Context", constraints: "Success Metrics (JSON)" }
    },
    defaults: {
      goal: "优化新用户注册转化，降低首日流失。",
      contextRefs: "doc://user-research,db://signup-funnel,doc://competitor-notes",
      constraints: { include: ["方案优先级", "风险", "里程碑"], language: "zh-CN" },
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
    title: "BeeAGI 交付工作台",
    subtitle: "先对话、再执行、看结果；反馈和控制放在右侧轻操作",
    language: "语言",
    scene: "场景",
    taskInput: "任务输入",
    flow: "流程",
    applyTemplate: "应用模板",
    runTask: "执行本轮任务",
    runFlow: "一键跑完整流程",
    running: "执行中...",
    latestTask: "最近任务",
    noTask: "暂无任务",
    qualityTarget: "质量目标",
    priority: "优先级",
    invalidJson: "JSON 格式有误，请先修正",
    chatTimeline: "对话式时间线",
    emptyChat: "先输入任务并执行，你将看到像聊天一样的过程记录",
    deliverable: "交付产物",
    deliverableEmpty: "任务完成后，这里会展示可直接使用的交付结果",
    summary: "结果摘要",
    llmSummary: "模型总结",
    planGraph: "执行清单",
    copy: "复制产物",
    copied: "已复制交付产物",
    quickGuide: "三步引导",
    guideStepInput: "1. 输入任务",
    guideStepRun: "2. 执行流程",
    guideStepDeliver: "3. 采纳或修订",
    quickUseDefault: "用默认示例",
    quickClear: "清空输入",
    quickAccept: "一键采纳",
    quickRefine: "需要修订",
    quickRefineDefault: "请再聚焦关键风险并给出可执行顺序。",
    swarm: "蜂群表现",
    roleIdle: "等待中",
    roleAction: "最近动作",
    roleAt: "时间",
    rightFeedback: "反馈（轻操作）",
    autoFeedback: "自动感知反馈（推荐）",
    autoFeedbackHint: "用户若未手动反馈，系统会从对话推断反馈并自动驱动进化",
    explicitScore: "显式评分",
    corrections: "修正建议",
    retryCount: "重试次数",
    editDistance: "编辑幅度",
    adoptionRate: "采纳率",
    errorRateRise: "错误率上升",
    submitFeedback: "提交人工反馈",
    runAutoFeedback: "立刻自动反馈",
    autoFeedbackState: "自动反馈状态",
    sideTabFeedback: "反馈",
    sideTabEvolution: "进化",
    sideTabSystem: "系统",
    rightControl: "进化控制",
    skill: "技能",
    candidateId: "候选 ID",
    createCandidate: "创建候选",
    shadowReplay: "影子回放",
    canaryStatus: "灰度状态",
    promote: "晋升候选",
    rollbackReason: "回滚原因",
    rollback: "回滚",
    rightHealth: "系统与审计",
    refresh: "刷新数据",
    runHealth: "运行体检",
    runAutoPromote: "自动晋升",
    healthChecking: "体检中...",
    noHealth: "尚未运行体检",
    events: "最近事件",
    audits: "最近审计",
    workflowLog: "流程日志",
    noWorkflowLog: "暂无流程日志",
    autoFeedbackDone: "已自动感知反馈并生成进化候选",
    autoFeedbackSkipped: "已存在人工反馈，本轮跳过自动反馈"
  },
  en: {
    title: "BeeAGI Delivery Workspace",
    subtitle: "Talk first, execute next, deliver clearly. Feedback/control stay lightweight on the right.",
    language: "Language",
    scene: "Scenario",
    taskInput: "Task Input",
    flow: "Flow",
    applyTemplate: "Apply Template",
    runTask: "Run This Round",
    runFlow: "Run Full Workflow",
    running: "Running...",
    latestTask: "Latest Task",
    noTask: "No task yet",
    qualityTarget: "Quality Target",
    priority: "Priority",
    invalidJson: "Invalid JSON. Please fix it first.",
    chatTimeline: "Chat Timeline",
    emptyChat: "Run a task first. You will see a chat-like timeline here.",
    deliverable: "Deliverable",
    deliverableEmpty: "The final output will be shown here after execution.",
    summary: "Summary",
    llmSummary: "Model Notes",
    planGraph: "Execution Checklist",
    copy: "Copy Output",
    copied: "Deliverable copied",
    quickGuide: "3-Step Guide",
    guideStepInput: "1. Input Task",
    guideStepRun: "2. Run Flow",
    guideStepDeliver: "3. Adopt or Revise",
    quickUseDefault: "Use Default Example",
    quickClear: "Clear Input",
    quickAccept: "Quick Accept",
    quickRefine: "Needs Refinement",
    quickRefineDefault: "Please focus on top risks and provide an actionable order.",
    swarm: "Swarm Performance",
    roleIdle: "Idle",
    roleAction: "Latest action",
    roleAt: "Time",
    rightFeedback: "Feedback (Lightweight)",
    autoFeedback: "Auto infer feedback (Recommended)",
    autoFeedbackHint: "If user forgets feedback, the system infers from conversation and evolves automatically.",
    explicitScore: "Explicit Score",
    corrections: "Corrections",
    retryCount: "Retry Count",
    editDistance: "Edit Distance",
    adoptionRate: "Adoption Rate",
    errorRateRise: "Error Rate Rise",
    submitFeedback: "Submit Manual Feedback",
    runAutoFeedback: "Run Auto Feedback Now",
    autoFeedbackState: "Auto Feedback State",
    sideTabFeedback: "Feedback",
    sideTabEvolution: "Evolution",
    sideTabSystem: "System",
    rightControl: "Evolution Control",
    skill: "Skill",
    candidateId: "Candidate ID",
    createCandidate: "Create Candidate",
    shadowReplay: "Shadow Replay",
    canaryStatus: "Canary Status",
    promote: "Promote",
    rollbackReason: "Rollback Reason",
    rollback: "Rollback",
    rightHealth: "System & Audit",
    refresh: "Refresh",
    runHealth: "Run Health Check",
    runAutoPromote: "Auto Promote",
    healthChecking: "Checking...",
    noHealth: "No health report yet",
    events: "Recent Events",
    audits: "Recent Audits",
    workflowLog: "Workflow Logs",
    noWorkflowLog: "No workflow logs yet",
    autoFeedbackDone: "Auto feedback inferred and evolution candidate generated",
    autoFeedbackSkipped: "Manual feedback already exists, auto-feedback skipped"
  }
} as const;

const ROLE_CONFIG = [
  { key: "scout", topic: "scout.reported", name: { zh: "斥候 Scout", en: "Scout" } },
  { key: "worker-plan", topic: "worker.planned", name: { zh: "工蜂 Worker（规划）", en: "Worker (Plan)" } },
  { key: "worker-exec", topic: "worker.completed", name: { zh: "工蜂 Worker（执行）", en: "Worker (Exec)" } },
  { key: "worm", topic: "worm.proposed", name: { zh: "蠕虫 Worm", en: "Worm" } },
  { key: "queen", topic: "queen.promoted", name: { zh: "蜂王 Queen", en: "Queen" } }
] as const;

function errorText(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function actionLabel(topic: string, locale: Locale): string {
  const zhMap: Record<string, string> = {
    "scout.reported": "完成信息侦察",
    "worker.planned": "生成任务计划",
    "worker.completed": "完成任务执行",
    "feedback.received": "收到反馈",
    "feedback.auto_inferred": "自动感知反馈",
    "worm.proposed": "生成技能候选",
    "shadow.evaluated": "完成影子回放",
    "canary.assigned": "进入灰度流量",
    "canary.observed": "记录灰度反馈",
    "queen.promoted": "候选晋升",
    "queen.rolled_back": "触发回滚"
  };
  const enMap: Record<string, string> = {
    "scout.reported": "Recon completed",
    "worker.planned": "Plan created",
    "worker.completed": "Execution completed",
    "feedback.received": "Feedback received",
    "feedback.auto_inferred": "Feedback auto-inferred",
    "worm.proposed": "Candidate proposed",
    "shadow.evaluated": "Shadow replay done",
    "canary.assigned": "Canary assigned",
    "canary.observed": "Canary feedback observed",
    "queen.promoted": "Candidate promoted",
    "queen.rolled_back": "Rollback triggered"
  };
  return locale === "zh" ? zhMap[topic] ?? topic : enMap[topic] ?? topic;
}

function toTimeLabel(isoTime: string): string {
  return new Date(isoTime).toLocaleTimeString();
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

  const planNodes = useMemo(() => latestTask?.planGraph?.nodes ?? [], [latestTask]);
  const appliedPatch = useMemo(() => {
    const patchData = latestTask?.resultPayload?.appliedPatchSummary;
    return typeof patchData === "object" && patchData ? patchData : null;
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

  const guideStep = useMemo(() => {
    if (!latestTask) {
      return 1;
    }
    if (latestTask.status === "completed") {
      return 3;
    }
    return 2;
  }, [latestTask]);

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

  const refreshData = async () => {
    const [skillsData, eventsData, auditsData] = await Promise.all([
      listSkills(),
      listEvolutionEvents(),
      listCandidateAudits(40)
    ]);
    setSkills(skillsData);
    setEvents(eventsData);
    setAudits(auditsData);
  };

  useEffect(() => {
    refreshData().catch((error) => setToast(errorText(error)));
    applyTemplate(scenario);
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
      const checklist = nodes.map((node) => `- ${node.title}`).join("\n");
      lines.push(checklist);
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
    } else {
      appendWorkflowLog(`auto-feedback: ${result.reason ?? "skipped"}`);
      appendChat({
        role: "system",
        title: "Feedback",
        text: ui.autoFeedbackSkipped,
        time: new Date().toISOString(),
        taskId: task.id
      });
      setToast(ui.autoFeedbackSkipped);
    }
  };

  const runTaskRound = async () => {
    const constraints = parseConstraints();
    if (!constraints) {
      return;
    }
    const startTime = new Date().toISOString();
    appendChat({
      role: "user",
      title: scenario.title[locale],
      text: `${labels.goal}: ${goal}\n${labels.context}: ${contextRefs}`,
      time: startTime
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
          {
            role: "user",
            content: `${labels.goal}: ${goal}\n${labels.context}: ${contextRefs}`
          },
          {
            role: "assistant",
            content: typeof task.resultPayload?.summary === "string" ? task.resultPayload.summary : task.goal
          },
          {
            role: "assistant",
            content: buildDeliverableText(task)
          }
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
      setToast("workflow done");
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
      setToast("feedback saved");
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
      setToast("rollback done");
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const runHealth = async () => {
    try {
      setHealthBusy(true);
      const report = await getHardeningReport();
      setHardeningReport(report);
      setToast("health updated");
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
      setToast(locale === "zh" ? "已采纳并提交反馈" : "Accepted and feedback submitted");
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
      setToast(locale === "zh" ? "已提交修订反馈" : "Refinement feedback submitted");
    } catch (error) {
      setToast(errorText(error));
    }
  };

  return (
    <div className="page">
      <header className="header">
        <div>
          <p className="brand">BeeAGI x Codex</p>
          <h1>{ui.title}</h1>
          <p className="subtitle">{ui.subtitle}</p>
          <div className="top-nav">
            <button className={`chip ${view === "workspace" ? "chip-active" : ""}`} onClick={() => setView("workspace")}>
              {locale === "zh" ? "工作台" : "Workspace"}
            </button>
            <button className={`chip ${view === "llm" ? "chip-active" : ""}`} onClick={() => setView("llm")}>
              {locale === "zh" ? "LLM 与 Token" : "LLM & Tokens"}
            </button>
          </div>
        </div>
        <div className="lang-switch">
          <span>{ui.language}</span>
          <button className={`chip ${locale === "zh" ? "chip-active" : ""}`} onClick={() => setLocale("zh")}>
            中文
          </button>
          <button className={`chip ${locale === "en" ? "chip-active" : ""}`} onClick={() => setLocale("en")}>
            English
          </button>
        </div>
      </header>

      {toast && <div className="toast">{toast}</div>}

      {view === "workspace" ? (
        <div className="workspace-layout">
        <main className="main-stage">
          <section className="card scene-card">
            <div className="card-head">
              <h2>{ui.scene}</h2>
              <span className="badge">{scenario.title[locale]}</span>
            </div>
            <div className="scenario-grid">
              {SCENARIOS.map((item) => (
                <button
                  key={item.id}
                  className={`scenario-card ${item.id === scenarioId ? "scenario-card-active" : ""}`}
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
          </section>

          <section className="card task-focus-card">
            <div className="card-head">
              <h2>{ui.taskInput}</h2>
              <span className="badge">
                {ui.latestTask}: {latestTask ? latestTask.status : ui.noTask}
              </span>
            </div>
            <div className="guide-row">
              <span className={`guide-chip ${guideStep >= 1 ? "guide-chip-active" : ""}`}>{ui.guideStepInput}</span>
              <span className={`guide-chip ${guideStep >= 2 ? "guide-chip-active" : ""}`}>{ui.guideStepRun}</span>
              <span className={`guide-chip ${guideStep >= 3 ? "guide-chip-active" : ""}`}>{ui.guideStepDeliver}</span>
            </div>
            <label>{labels.goal}</label>
            <textarea rows={4} value={goal} onChange={(e) => setGoal(e.target.value)} />
            <label>{labels.context}</label>
            <input value={contextRefs} onChange={(e) => setContextRefs(e.target.value)} />
            <label>{labels.constraints}</label>
            <textarea
              rows={5}
              value={constraintsText}
              onChange={(e) => {
                setConstraintsText(e.target.value);
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
                  onChange={(e) => setQualityTarget(Number(e.target.value))}
                />
              </div>
              <div>
                <label>{ui.priority}</label>
                <input type="number" min={1} max={5} value={priority} onChange={(e) => setPriority(Number(e.target.value))} />
              </div>
            </div>
            <div className="scenario-actions">
              <button className="button" onClick={() => setGoal(scenario.defaults.goal)}>
                {ui.quickUseDefault}
              </button>
              <button
                className="button"
                onClick={() => {
                  setGoal("");
                  setContextRefs("");
                  setConstraintsText("{}");
                }}
              >
                {ui.quickClear}
              </button>
              <button className="button" onClick={() => applyTemplate(scenario)}>
                {ui.applyTemplate}
              </button>
              <button className="button button-primary" onClick={runTaskRound} disabled={busy}>
                {busy ? ui.running : ui.runTask}
              </button>
              <button className="button button-primary" onClick={runScenarioFlow} disabled={workflowBusy}>
                {workflowBusy ? ui.running : ui.runFlow}
              </button>
            </div>
          </section>

          <section className="card">
            <h2>{ui.chatTimeline}</h2>
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

          <section className="card deliverable-card">
            <div className="card-head">
              <h2>{ui.deliverable}</h2>
              <div className="inline-actions">
                <button className="button" onClick={copyDeliverable} disabled={!latestTask}>
                  {ui.copy}
                </button>
                <button className="button button-primary" onClick={quickAcceptDeliverable} disabled={!latestTask}>
                  {ui.quickAccept}
                </button>
                <button className="button" onClick={quickRequestRefine} disabled={!latestTask}>
                  {ui.quickRefine}
                </button>
              </div>
            </div>
            {!latestTask && <p className="hint">{ui.deliverableEmpty}</p>}
            {latestTask && (
              <>
                <p className="hint">
                  {ui.latestTask}: {latestTask.id}
                </p>
                <h3>{ui.summary}</h3>
                <p className="result-text">{outputSummary || latestTask.goal}</p>
                {llmSummary && (
                  <>
                    <h3>{ui.llmSummary}</h3>
                    <p className="hint">{llmSummary}</p>
                  </>
                )}
                {planNodes.length > 0 && (
                  <>
                    <h3>{ui.planGraph}</h3>
                    <ol className="compact-list">
                      {planNodes.map((node) => (
                        <li key={node.id}>{node.title}</li>
                      ))}
                    </ol>
                  </>
                )}
                {appliedPatch && (
                  <>
                    <h3>{ui.swarm}</h3>
                    <pre className="json-preview">{JSON.stringify(appliedPatch, null, 2)}</pre>
                  </>
                )}
              </>
            )}
          </section>
        </main>

        <aside className="side-rail">
          <section className="card side-card">
            <div className="side-tab-row">
              <button
                className={`chip ${sideTab === "feedback" ? "chip-active" : ""}`}
                onClick={() => setSideTab("feedback")}
              >
                {ui.sideTabFeedback}
              </button>
              <button
                className={`chip ${sideTab === "evolution" ? "chip-active" : ""}`}
                onClick={() => setSideTab("evolution")}
              >
                {ui.sideTabEvolution}
              </button>
              <button
                className={`chip ${sideTab === "system" ? "chip-active" : ""}`}
                onClick={() => setSideTab("system")}
              >
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
                  onChange={(e) => setExplicitScore(Number(e.target.value))}
                />
                <label>{ui.corrections}</label>
                <textarea rows={3} value={corrections} onChange={(e) => setCorrections(e.target.value)} />
                <label>{ui.retryCount}</label>
                <input type="number" min={0} value={retryCount} onChange={(e) => setRetryCount(Number(e.target.value))} />
                <label>{ui.editDistance}</label>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={editDistance}
                  onChange={(e) => setEditDistance(Number(e.target.value))}
                />
                <label>{ui.adoptionRate}</label>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={adoptionRate}
                  onChange={(e) => setAdoptionRate(Number(e.target.value))}
                />
                <label>{ui.errorRateRise}</label>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={errorRateRise}
                  onChange={(e) => setErrorRateRise(Number(e.target.value))}
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
                <div className="swarm-grid">
                  {roleStats.map((item) => (
                    <article key={item.role.key} className="swarm-card">
                      <strong>{item.role.name[locale]}</strong>
                      <p className="hint">{item.count}</p>
                      {item.latest ? (
                        <>
                          <p className="hint">
                            {ui.roleAction}: {actionLabel(item.latest.topic, locale)}
                          </p>
                          <p className="hint">
                            {ui.roleAt}: {toTimeLabel(item.latest.createdAt)}
                          </p>
                        </>
                      ) : (
                        <p className="hint">{ui.roleIdle}</p>
                      )}
                    </article>
                  ))}
                </div>
              </section>

              <section className="card side-card">
                <h2>{ui.rightControl}</h2>
                <label>{ui.skill}</label>
                <select value={selectedSkill?.id ?? ""} onChange={(e) => setSelectedSkillId(e.target.value)}>
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
                <input value={candidateId} onChange={(e) => setCandidateId(e.target.value)} />
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
                <input value={rollbackReason} onChange={(e) => setRollbackReason(e.target.value)} />
                <button className="button button-warning" onClick={rollback} disabled={!selectedSkill}>
                  {ui.rollback}
                </button>
              </section>
            </>
          )}

          {sideTab === "system" && (
            <section className="card side-card">
              <h2>{ui.rightHealth}</h2>
              <button className="button" onClick={() => refreshData().catch((error) => setToast(errorText(error)))}>
                {ui.refresh}
              </button>
              <button className="button" onClick={autoPromote}>
                {ui.runAutoPromote}
              </button>
              <button className="button button-primary" onClick={runHealth} disabled={healthBusy}>
                {healthBusy ? ui.healthChecking : ui.runHealth}
              </button>
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
                  {workflowLogs.slice(0, 10).map((line) => (
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
