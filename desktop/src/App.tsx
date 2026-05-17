import { useEffect, useMemo, useRef, useState } from "react";
import {
  autoFeedback,
  createSkillCandidate,
  createSkillFromFactory,
  createTask,
  downloadDeliverableArchive,
  downloadDeliverableFile,
  ensureEvolution,
  getAutonomousLifeReports,
  evaluateShadowReplay,
  getAutonomousLifeStatus,
  getEvolutionTelemetry,
  getLlmTokenStats,
  getCanaryStatus,
  getHardeningReport,
  listCandidateAudits,
  listEvolutionEvents,
  listScoutPheromones,
  listSkills,
  openDeliverable,
  promoteCandidate,
  rollbackSkill,
  runAutoPromote,
  runAutonomousLifeCycle,
  runScoutPatrol,
  submitFeedback,
  touchAutonomousLife
} from "./api/client";
import {
  AutoFeedbackResponse,
  AutonomousLifeReport,
  AutonomousLifeStatus,
  CandidateStatusAuditView,
  ConversationTurn,
  EvolutionEventView,
  EvolutionTelemetryResponse,
  HardeningReportResponse,
  LlmTokenStatsResponse,
  ScoutPheromoneView,
  SkillCard,
  TaskDetail,
  TaskSpec
} from "./types";
import LlmConsolePage from "./components/LlmConsolePage";

type Locale = "zh" | "en";
type ScenarioId = "coding" | "office" | "research" | "debug" | "data" | "product" | "skills_factory" | "video_creator";
type ChatRole = "user" | "swarm" | "deliverable" | "system" | "life";
type ViewMode = "workspace" | "llm";
type SideTab = "feedback" | "evolution" | "system";
type RuntimeStage = "idle" | "planning" | "executing" | "feedback" | "evolving" | "completed" | "error";
type RuntimeStepStatus = "pending" | "running" | "completed" | "failed";

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

type RuntimeStep = {
  id: string;
  title: string;
  detail: string;
  status: RuntimeStepStatus;
  at?: string;
  taskId?: string;
};

type StreamingState = {
  title: string;
  text: string;
  taskId?: string;
  startedAt: string;
};

type SkillTemplate = {
  id: string;
  category: "code" | "video" | "research" | "ops";
  title: { zh: string; en: string };
  description: { zh: string; en: string };
  suggestedScenario: ScenarioId;
  strategy: string;
  connectors: string[];
  ioSchema: Record<string, unknown>;
  permissions: Record<string, unknown>;
  costBudget: Record<string, unknown>;
  deltaPatch: Record<string, unknown>;
};

type DeliverableFile = {
  path: string;
  absolutePath?: string;
  kind?: string;
  description?: string;
  bytes?: number;
};

type DeliverableView = {
  status: string;
  scene: string;
  title: string;
  workspacePath: string;
  source: string;
  allowWrite: boolean;
  allowExecute: boolean;
  fileCount: number;
  files: DeliverableFile[];
  plannedFiles: DeliverableFile[];
  primaryArtifact?: string;
  error?: string;
  reason?: string;
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
      goal: "为用户管理页面新增状态筛选与分页能力，并补齐单元测试。",
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
        context: "资料来源（文档、纪要、表格）",
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
  },
  {
    id: "skills_factory",
    title: { zh: "Skills 工厂", en: "Skills Factory" },
    subtitle: { zh: "技能目标 / MCP 接入 / 发布标准", en: "Skill Goal / MCP Connectors / Release Criteria" },
    flow: { zh: ["设计", "组装", "验证"], en: ["Design", "Assemble", "Validate"] },
    labels: {
      zh: {
        goal: "技能目标",
        context: "可用资料与工具边界",
        constraints: "技能验收标准（JSON）"
      },
      en: {
        goal: "Skill Goal",
        context: "Available assets and tool boundaries",
        constraints: "Skill acceptance (JSON)"
      }
    },
    defaults: {
      goal: "构建一个可复用的技能，用于多轮任务中的自动改写与风险排序。",
      contextRefs: "repo://skills,doc://playbook,mcp://github,mcp://filesystem",
      constraints: {
        output: "skill-card",
        evolution: "guarded",
        language: "zh-CN"
      },
      qualityTarget: 0.92,
      priority: 1,
      feedback: {
        explicitScore: 0.9,
        corrections: "请补充技能输入输出 schema 与失败回退策略。",
        retryCount: 0,
        editDistance: 0.1,
        adoptionRate: 0.9,
        errorRateRise: 0
      }
    }
  },
  {
    id: "video_creator",
    title: { zh: "短视频制作", en: "Short Video Studio" },
    subtitle: { zh: "脚本 / 素材 / 输出镜头结构", en: "Script / Assets / Shot Structure" },
    flow: { zh: ["策划", "分镜", "成片"], en: ["Plan", "Storyboard", "Deliver"] },
    labels: {
      zh: {
        goal: "视频目标",
        context: "素材库与参考链接",
        constraints: "视频交付标准（JSON）"
      },
      en: {
        goal: "Video Goal",
        context: "Asset sources and references",
        constraints: "Video acceptance (JSON)"
      }
    },
    defaults: {
      goal: "生成 60 秒产品介绍短视频脚本与分镜，突出核心卖点与行动号召。",
      contextRefs: "doc://brand-voice,doc://product-points,mcp://canva,mcp://figma,mcp://drive",
      constraints: {
        output: "script+storyboard",
        style: "future-tech",
        durationSec: 60,
        language: "zh-CN"
      },
      qualityTarget: 0.9,
      priority: 2,
      feedback: {
        explicitScore: 0.88,
        corrections: "请增加开场 3 秒抓钩和结尾 CTA 强度。",
        retryCount: 1,
        editDistance: 0.14,
        adoptionRate: 0.86,
        errorRateRise: 0
      }
    }
  }
];

const SKILL_TEMPLATE_MARKET: SkillTemplate[] = [
  {
    id: "tpl_code_review_repair",
    category: "code",
    title: { zh: "代码评审修复循环", en: "Code Review-Repair Loop" },
    description: {
      zh: "面向编码场景，强化实现-评审-修复闭环，并自动沉淀可复用规则。",
      en: "For coding tasks with strong implement-review-fix loops and reusable rule extraction."
    },
    suggestedScenario: "coding",
    strategy: "review_repair_loop",
    connectors: ["github", "filesystem", "linear", "slack"],
    ioSchema: { input: ["requirement", "repoContext", "acceptance"], output: ["patch", "review", "riskChecklist"] },
    permissions: { network: true, filesystem: "read_write" },
    costBudget: { maxTokens: 18000 },
    deltaPatch: {
      promptTweaks: { mode: "strict_review", output: "patch+review+test-plan" },
      toolPolicy: { maxRetries: 3, preferLowRiskTools: true }
    }
  },
  {
    id: "tpl_video_storyboard",
    category: "video",
    title: { zh: "短视频脚本分镜器", en: "Short Video Storyboarder" },
    description: {
      zh: "快速生成 30-90 秒短视频脚本、分镜和 CTA 变体。",
      en: "Generates 30-90s script, storyboard and CTA variants quickly."
    },
    suggestedScenario: "video_creator",
    strategy: "tree_of_thought",
    connectors: ["canva", "figma", "google-drive", "filesystem"],
    ioSchema: { input: ["goal", "assets", "brand"], output: ["script", "shots", "editingPlan"] },
    permissions: { network: true, filesystem: "read_write" },
    costBudget: { maxTokens: 16000 },
    deltaPatch: {
      promptTweaks: { style: "high-retention-video", format: "script+storyboard" },
      toolPolicy: { maxRetries: 2, preferLowRiskTools: false }
    }
  },
  {
    id: "tpl_research_synthesizer",
    category: "research",
    title: { zh: "研究证据综合器", en: "Research Evidence Synthesizer" },
    description: {
      zh: "聚合检索、分析和结论，输出证据链与置信度。",
      en: "Combines retrieval, analysis and conclusion with evidence-chain confidence."
    },
    suggestedScenario: "research",
    strategy: "tool_first",
    connectors: ["notion", "google-drive", "github", "filesystem"],
    ioSchema: { input: ["question", "dataSources"], output: ["hypothesis", "evidence", "confidence"] },
    permissions: { network: true, filesystem: "read" },
    costBudget: { maxTokens: 15000 },
    deltaPatch: {
      promptTweaks: { format: "hypothesis-evidence-confidence", style: "analytical" },
      toolPolicy: { maxRetries: 2, preferLowRiskTools: true }
    }
  },
  {
    id: "tpl_ops_command_center",
    category: "ops",
    title: { zh: "运营指挥中心技能", en: "Ops Command Center" },
    description: {
      zh: "统一任务分发、反馈聚合、风险排序与执行建议。",
      en: "Unifies task dispatch, feedback aggregation, risk ranking and action suggestions."
    },
    suggestedScenario: "office",
    strategy: "tool_first",
    connectors: ["slack", "notion", "google-calendar", "filesystem"],
    ioSchema: { input: ["objective", "materials"], output: ["brief", "actions", "riskBoard"] },
    permissions: { network: true, filesystem: "read_write" },
    costBudget: { maxTokens: 14000 },
    deltaPatch: {
      promptTweaks: { output: "brief+action-list+risk-order", tone: "executive-clear" },
      toolPolicy: { maxRetries: 2, preferLowRiskTools: true }
    }
  }
];

const UI = {
  zh: {
    title: "BeeAGI 任务工作台",
    subtitle: "像聊天一样规划任务，稳定交付成果，再把反馈转成自动进化。",
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
    emptyChat: "先执行一个任务，这里会生成完整过程记录。",
    deliverable: "交付产物",
    deliverableEmpty: "任务完成后，这里会展示可直接使用的结果。",
    llmSummary: "模型补充说明",
    copy: "复制结果",
    copied: "已复制到剪贴板",
    openFolder: "打开目录",
    openFile: "打开文件",
    downloadFile: "下载文件",
    downloadZip: "下载ZIP",
    downloadDone: "下载已开始",
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
    autoFeedbackSkipped: "已存在反馈，本轮自动反馈跳过。",
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
    openFolder: "Open Folder",
    openFile: "Open File",
    downloadFile: "Download File",
    downloadZip: "Download ZIP",
    downloadDone: "Download started",
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

function toDayKey(isoTime: string): string {
  const date = new Date(isoTime);
  const y = date.getFullYear();
  const m = `${date.getMonth() + 1}`.padStart(2, "0");
  const d = `${date.getDate()}`.padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function dayGroupLabel(dayKey: string, locale: Locale): string {
  const now = new Date();
  const localKey = (date: Date) => {
    const y = date.getFullYear();
    const m = `${date.getMonth() + 1}`.padStart(2, "0");
    const d = `${date.getDate()}`.padStart(2, "0");
    return `${y}-${m}-${d}`;
  };
  const today = localKey(now);
  const yesterdayDate = new Date(now);
  yesterdayDate.setDate(yesterdayDate.getDate() - 1);
  const yesterday = localKey(yesterdayDate);
  if (dayKey === today) {
    return locale === "zh" ? "今天" : "Today";
  }
  if (dayKey === yesterday) {
    return locale === "zh" ? "昨天" : "Yesterday";
  }
  const [y, m, d] = dayKey.split("-");
  return locale === "zh" ? `${y}年${m}月${d}日` : `${y}-${m}-${d}`;
}

function runtimeStageLabel(stage: RuntimeStage, locale: Locale): string {
  const zh: Record<RuntimeStage, string> = {
    idle: "待命",
    planning: "计划中",
    executing: "执行中",
    feedback: "反馈吸收",
    evolving: "自进化",
    completed: "已完成",
    error: "异常"
  };
  const en: Record<RuntimeStage, string> = {
    idle: "Idle",
    planning: "Planning",
    executing: "Executing",
    feedback: "Feedback",
    evolving: "Self-Evolving",
    completed: "Completed",
    error: "Error"
  };
  return locale === "zh" ? zh[stage] : en[stage];
}

function runtimeStepStatusLabel(status: RuntimeStepStatus, locale: Locale): string {
  const zh: Record<RuntimeStepStatus, string> = {
    pending: "等待",
    running: "进行中",
    completed: "完成",
    failed: "失败"
  };
  const en: Record<RuntimeStepStatus, string> = {
    pending: "Pending",
    running: "Running",
    completed: "Done",
    failed: "Failed"
  };
  return locale === "zh" ? zh[status] : en[status];
}

function actionLabel(topic: string, locale: Locale): string {
  if (topic === "worker.deliverable_written") {
    return locale === "zh" ? "产物已落盘" : "Artifacts written";
  }
  if (topic === "feedback.self_evolution_guarded") {
    return locale === "zh" ? "自进化保障" : "Self-evolution guarded";
  }
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

function lifeVitalityLabel(vitality: string, locale: Locale): string {
  const level = vitality.toLowerCase();
  if (level === "high") {
    return locale === "zh" ? "高活性" : "High";
  }
  if (level === "medium") {
    return locale === "zh" ? "中活性" : "Medium";
  }
  if (level === "low") {
    return locale === "zh" ? "低活性" : "Low";
  }
  return vitality;
}

function lifeReportTitle(locale: Locale): string {
  return locale === "zh" ? "生命体自述" : "Life Self-Report";
}

function lifeReportNarrative(report: AutonomousLifeReport, locale: Locale): { learned: string; next: string } {
  const signals = report.signals ?? {};
  const ensuredSubmitted = Number(signals.ensuredSubmitted ?? 0);
  const ensuredFailed = Number(signals.ensuredFailed ?? 0);
  const patrolDeposited = Number(signals.patrolDeposited ?? 0);
  const patrolSampledTasks = Number(signals.patrolSampledTasks ?? 0);
  const promoted = Number(signals.promoted ?? 0);
  const validated = Number(signals.validated ?? 0);
  const rejected = Number(signals.rejected ?? 0);
  const rolledBack = Number(signals.rolledBack ?? 0);

  const learnedParts: string[] = [];
  if (locale === "zh") {
    if (ensuredSubmitted > 0) {
      learnedParts.push(`本轮吸收了 ${ensuredSubmitted} 个无人反馈任务信号并转成进化候选`);
    }
    if (patrolDeposited > 0) {
      learnedParts.push(`斥候从 ${patrolSampledTasks} 个样本任务沉积了 ${patrolDeposited} 条信息素路径`);
    }
    if (promoted > 0) {
      learnedParts.push(`蜂王晋升了 ${promoted} 个候选技能版本`);
    }
    if (validated > 0) {
      learnedParts.push(`有 ${validated} 个候选进入待灰度确认阶段`);
    }
    if (ensuredFailed > 0) {
      learnedParts.push(`发现 ${ensuredFailed} 次反馈吸收失败，需继续观察`);
    }
    if (learnedParts.length === 0) {
      learnedParts.push("本轮整体稳定，尚未出现新的显著增量信号");
    }

    let next = "继续保持低成本巡航，并等待新的任务信号";
    if (rolledBack > 0 || rejected > 0) {
      next = "下一轮将收紧风险阈值，优先修复低表现候选后再发布";
    } else if (validated > 0 && promoted === 0) {
      next = "下一轮将优先收集灰度反馈，决定晋升或回滚";
    } else if (ensuredSubmitted > 0) {
      next = "下一轮将优先影子回放这些新候选，并准备小流量灰度";
    } else if (patrolDeposited > 0) {
      next = "下一轮将继续扩展侦察覆盖，联动反馈吸收链路";
    }
    return { learned: learnedParts.join("；"), next };
  }

  if (ensuredSubmitted > 0) {
    learnedParts.push(`absorbed ${ensuredSubmitted} unattended-task feedback signal(s) into evolution candidates`);
  }
  if (patrolDeposited > 0) {
    learnedParts.push(`scouts deposited ${patrolDeposited} pheromone route(s) from ${patrolSampledTasks} sampled task(s)`);
  }
  if (promoted > 0) {
    learnedParts.push(`queen promoted ${promoted} candidate skill(s)`);
  }
  if (validated > 0) {
    learnedParts.push(`${validated} candidate(s) entered waiting-for-canary state`);
  }
  if (ensuredFailed > 0) {
    learnedParts.push(`${ensuredFailed} feedback-absorption failure(s) observed`);
  }
  if (learnedParts.length === 0) {
    learnedParts.push("this cycle stayed stable with no significant delta yet");
  }

  let next = "keep low-cost cruising and wait for fresh task signals";
  if (rolledBack > 0 || rejected > 0) {
    next = "tighten risk thresholds and repair low-performing candidates before promotion";
  } else if (validated > 0 && promoted === 0) {
    next = "collect more canary feedback and decide promote vs rollback";
  } else if (ensuredSubmitted > 0) {
    next = "replay newly inferred candidates in shadow mode and prepare canary exposure";
  } else if (patrolDeposited > 0) {
    next = "expand scout coverage and keep feedback absorption linked";
  }
  return { learned: learnedParts.join("; "), next };
}

function lifeReportSignature(report: AutonomousLifeReport): string {
  const signals = report.signals ?? {};
  return [
    report.status,
    report.idle ? "1" : "0",
    String(signals.ensuredSubmitted ?? 0),
    String(signals.patrolDeposited ?? 0),
    String(signals.patrolSampledTasks ?? 0),
    String(signals.promoted ?? 0),
    String(signals.validated ?? 0),
    String(signals.rejected ?? 0),
    String(signals.rolledBack ?? 0),
    report.vitality
  ].join("|");
}

function lifeReportText(report: AutonomousLifeReport, locale: Locale, streak = 1): string {
  const confidencePct = `${Math.round(report.confidence * 100)}%`;
  const vitality = lifeVitalityLabel(report.vitality, locale);
  const narrative = lifeReportNarrative(report, locale);
  const learned = String(report.learned ?? "").trim() || narrative.learned;
  const next = String(report.nextFocus ?? "").trim() || narrative.next;

  if (locale === "zh") {
    const lines = [
      `我刚学到：${learned}`,
      `下一轮准备：${next}`,
      `活性：${vitality} | 置信度：${confidencePct}`,
    ];
    if (streak > 1) {
      lines.push(`连续观察：同类模式已持续 ${streak} 轮`);
    }
    return lines.join("\n");
  }

  const lines = [
    `I just learned: ${learned}`,
    `Next cycle I will: ${next}`,
    `Vitality: ${vitality} | Confidence: ${confidencePct}`,
  ];
  if (streak > 1) {
    lines.push(`Continuous observation: same pattern persisted for ${streak} cycles`);
  }
  return lines.join("\n");
}
function estimateTokenCostUsd(stats: LlmTokenStatsResponse | null): number {
  if (!stats || stats.byModel.length === 0) {
    return 0;
  }
  const rateByProvider: Record<string, { promptPerK: number; completionPerK: number }> = {
    deepseek: { promptPerK: 0.0004, completionPerK: 0.0012 },
    openai: { promptPerK: 0.001, completionPerK: 0.003 },
    openai_compatible: { promptPerK: 0.0008, completionPerK: 0.0024 },
    enterprise: { promptPerK: 0.0012, completionPerK: 0.0035 },
    ollama: { promptPerK: 0, completionPerK: 0 },
    mock: { promptPerK: 0, completionPerK: 0 },
    error: { promptPerK: 0, completionPerK: 0 },
    unknown: { promptPerK: 0.0007, completionPerK: 0.002 }
  };

  let total = 0;
  for (const row of stats.byModel) {
    const provider = String(row.provider || "unknown").toLowerCase();
    const rate = rateByProvider[provider] ?? rateByProvider.unknown;
    total += (row.promptTokens / 1000) * rate.promptPerK;
    total += (row.completionTokens / 1000) * rate.completionPerK;
  }
  return Number(total.toFixed(4));
}

function swimlaneOfTopic(topic: string): "scout" | "worker" | "worm" | "queen" | "feedback" | "system" {
  if (topic.startsWith("scout.")) {
    return "scout";
  }
  if (topic.startsWith("worker.") || topic.startsWith("shadow.") || topic.startsWith("canary.")) {
    return "worker";
  }
  if (topic.startsWith("worm.") || topic.startsWith("skill.")) {
    return "worm";
  }
  if (topic.startsWith("queen.")) {
    return "queen";
  }
  if (topic.startsWith("feedback.")) {
    return "feedback";
  }
  return "system";
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
  const [workerCount, setWorkerCount] = useState(4);
  const [scoutCount, setScoutCount] = useState(3);
  const [mcpConnectorsText, setMcpConnectorsText] = useState("filesystem,github,notion,slack");
  const [workspaceTargetDir, setWorkspaceTargetDir] = useState("D:\\Bee2\\artifacts\\deliverables");
  const [workspaceAllowWrite, setWorkspaceAllowWrite] = useState(true);
  const [workspaceAllowExecute, setWorkspaceAllowExecute] = useState(false);

  const [factorySkillId, setFactorySkillId] = useState("skill_future_assistant");
  const [factorySkillName, setFactorySkillName] = useState("Future Assistant Skill");
  const [factorySkillDescription, setFactorySkillDescription] = useState("Auto-evolving skill for multi-turn delivery and review.");
  const [factoryStrategy, setFactoryStrategy] = useState("tool_first");
  const [selectedTemplateId, setSelectedTemplateId] = useState(SKILL_TEMPLATE_MARKET[0]?.id ?? "");
  const [templateReleaseBusy, setTemplateReleaseBusy] = useState(false);

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
  const [evolutionTelemetry, setEvolutionTelemetry] = useState<EvolutionTelemetryResponse | null>(null);
  const [lifeStatus, setLifeStatus] = useState<AutonomousLifeStatus | null>(null);
  const [lifeReports, setLifeReports] = useState<AutonomousLifeReport[]>([]);
  const [latestTask, setLatestTask] = useState<TaskDetail>();
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const seenLifeReportIds = useRef<Set<string>>(new Set());
  const lastLifeDigestRef = useRef<{ signature: string; messageId: string; streak: number } | null>(null);

  const [selectedSkillId, setSelectedSkillId] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [rollbackReason, setRollbackReason] = useState("manual rollback for risk control");

  const [toast, setToast] = useState("");
  const [busy, setBusy] = useState(false);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [healthBusy, setHealthBusy] = useState(false);
  const [patrolBusy, setPatrolBusy] = useState(false);
  const [workflowLogs, setWorkflowLogs] = useState<string[]>([]);
  const [runtimeStage, setRuntimeStage] = useState<RuntimeStage>("idle");
  const [runtimeSteps, setRuntimeSteps] = useState<RuntimeStep[]>([]);
  const [streamingState, setStreamingState] = useState<StreamingState | null>(null);
  const [tokenStats, setTokenStats] = useState<LlmTokenStatsResponse | null>(null);

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

  const deliverableView = useMemo<DeliverableView | null>(() => {
    const payload = latestTask?.resultPayload;
    if (!payload || typeof payload !== "object") {
      return null;
    }
    const raw = payload.deliverables as Record<string, unknown> | undefined;
    if (!raw || typeof raw !== "object") {
      return null;
    }

    const rawFiles = raw.files;
    const rawPlannedFiles = raw.plannedFiles;
    const files = Array.isArray(rawFiles)
      ? rawFiles
          .filter((item: unknown): item is Record<string, unknown> => !!item && typeof item === "object")
          .map((item: Record<string, unknown>) => ({
            path: typeof item.path === "string" ? item.path : "",
            absolutePath: typeof item.absolutePath === "string" ? item.absolutePath : undefined,
            kind: typeof item.kind === "string" ? item.kind : undefined,
            description: typeof item.description === "string" ? item.description : undefined,
            bytes: typeof item.bytes === "number" ? item.bytes : undefined
          }))
      : [];

    const plannedFiles = Array.isArray(rawPlannedFiles)
      ? rawPlannedFiles
          .filter((item: unknown): item is Record<string, unknown> => !!item && typeof item === "object")
          .map((item: Record<string, unknown>) => ({
            path: typeof item.path === "string" ? item.path : "",
            absolutePath: typeof item.absolutePath === "string" ? item.absolutePath : undefined,
            kind: typeof item.kind === "string" ? item.kind : undefined,
            description: typeof item.description === "string" ? item.description : undefined
          }))
      : [];

    return {
      status: typeof raw.status === "string" ? raw.status : "unknown",
      scene: typeof raw.scene === "string" ? raw.scene : "unknown",
      title: typeof raw.title === "string" ? raw.title : "Deliverable",
      workspacePath: typeof raw.workspacePath === "string" ? raw.workspacePath : "",
      source: typeof raw.source === "string" ? raw.source : "none",
      allowWrite: raw.allowWrite === true,
      allowExecute: raw.allowExecute === true,
      fileCount: typeof raw.fileCount === "number" ? raw.fileCount : files.length,
      files,
      plannedFiles,
      primaryArtifact: typeof raw.primaryArtifact === "string" ? raw.primaryArtifact : undefined,
      error: typeof raw.error === "string" ? raw.error : undefined,
      reason: typeof raw.reason === "string" ? raw.reason : undefined
    };
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

  const timelineGroups = useMemo(() => {
    const sorted = [...chatMessages].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
    const grouped = new Map<string, ChatMessage[]>();
    for (const message of sorted) {
      const key = toDayKey(message.time);
      const list = grouped.get(key) ?? [];
      list.push(message);
      grouped.set(key, list);
    }
    return Array.from(grouped.entries()).map(([key, items]) => ({ key, label: dayGroupLabel(key, locale), items }));
  }, [chatMessages, locale]);

  const runtimeProgress = useMemo(() => {
    if (runtimeSteps.length === 0) {
      return 0;
    }
    const score = runtimeSteps.reduce((acc, step) => {
      if (step.status === "completed") {
        return acc + 1;
      }
      if (step.status === "running") {
        return acc + 0.5;
      }
      return acc;
    }, 0);
    return Math.round((score / runtimeSteps.length) * 100);
  }, [runtimeSteps]);

  const selectedTemplate = useMemo(
    () => SKILL_TEMPLATE_MARKET.find((item) => item.id === selectedTemplateId) ?? SKILL_TEMPLATE_MARKET[0],
    [selectedTemplateId]
  );

  const liveParallelism = useMemo(() => {
    const runningSteps = runtimeSteps.filter((item) => item.status === "running").length;
    if (runtimeStage === "executing" || runtimeStage === "planning" || runtimeStage === "evolving") {
      return Math.max(runningSteps, workerCount + scoutCount);
    }
    return runningSteps;
  }, [runtimeSteps, runtimeStage, workerCount, scoutCount]);

  const estimatedCostUsd = useMemo(() => estimateTokenCostUsd(tokenStats), [tokenStats]);
  const evolutionProgressScore = evolutionTelemetry?.speed.progressScore ?? 0;
  const evolutionVelocityScore = evolutionTelemetry?.speed.velocityScore ?? 0;

  const evolutionTimelineBars = useMemo(() => {
    const points = evolutionTelemetry?.timeline ?? [];
    const maxEvents = Math.max(1, ...points.map((item) => item.events));
    return points.slice(-18).map((item) => ({
      ...item,
      heightPct: Math.max(8, Math.round((item.events / maxEvents) * 100)),
    }));
  }, [evolutionTelemetry]);

  const swarmSkewHint = useMemo(() => {
    if (!evolutionTelemetry) {
      return "";
    }
    const roles = evolutionTelemetry.roles;
    const scout = roles.scoutEvents60M;
    const others = roles.workerEvents60M + roles.wormEvents60M + roles.queenEvents60M + roles.feedbackEvents60M;
    if (scout >= 200 && others <= Math.max(2, Math.floor(scout * 0.02))) {
      return locale === "zh"
        ? "当前主要在自动巡航采样，执行角色还未被任务激活。提交任务后会拉起 Worker/Worm/Queen。"
        : "System is mainly in autonomous scout cruising. Submit tasks to activate Worker/Worm/Queen.";
    }
    return "";
  }, [evolutionTelemetry, locale]);

  const swimlanes = useMemo(() => {
    const laneOrder: Array<{ key: ReturnType<typeof swimlaneOfTopic>; labelZh: string; labelEn: string }> = [
      { key: "scout", labelZh: "Scout 侦察线", labelEn: "Scout Lane" },
      { key: "worker", labelZh: "Worker 执行线", labelEn: "Worker Lane" },
      { key: "worm", labelZh: "Worm 进化线", labelEn: "Worm Lane" },
      { key: "queen", labelZh: "Queen 治理线", labelEn: "Queen Lane" },
      { key: "feedback", labelZh: "反馈线", labelEn: "Feedback Lane" },
      { key: "system", labelZh: "系统线", labelEn: "System Lane" },
    ];
    const recentEvents = [...events].sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()).slice(-30);
    return laneOrder.map((lane) => ({
      ...lane,
      items: recentEvents.filter((evt) => swimlaneOfTopic(evt.topic) === lane.key)
    }));
  }, [events]);

  const buildRuntimeSteps = (executionSteps: string[]): RuntimeStep[] => {
    const execution = executionSteps.length > 0 ? executionSteps : [locale === "zh" ? "执行" : "Execute"];
    return [
      {
        id: "plan",
        title: locale === "zh" ? "计划图生成" : "Plan Graph",
        detail: locale === "zh" ? "基于目标和上下文生成执行计划" : "Generate execution graph from goal and context.",
        status: "pending"
      },
      ...execution.map((step, index) => ({
        id: `exec-${index}`,
        title: step,
        detail: locale === "zh" ? "执行该步骤并产出阶段结果" : "Execute this step and produce intermediate output.",
        status: "pending" as const
      })),
      {
        id: "deliverable",
        title: locale === "zh" ? "交付整合" : "Deliverable",
        detail: locale === "zh" ? "汇总最终产物与关键说明" : "Compile final deliverable with key notes.",
        status: "pending"
      },
      {
        id: "feedback",
        title: locale === "zh" ? "反馈吸收" : "Feedback Loop",
        detail: locale === "zh" ? "吸收显式/隐式反馈信号" : "Capture explicit and implicit feedback signals.",
        status: "pending"
      },
      {
        id: "evolution",
        title: locale === "zh" ? "自进化保障" : "Self-Evolution Guard",
        detail: locale === "zh" ? "确保反馈缺失时仍触发技能进化" : "Guarantee skill evolution even if feedback is missing.",
        status: "pending"
      }
    ];
  };

  const patchRuntimeStep = (id: string, status: RuntimeStepStatus, detail?: string, taskId?: string) => {
    setRuntimeSteps((prev) =>
      prev.map((step) =>
        step.id === id
          ? {
              ...step,
              status,
              detail: detail ?? step.detail,
              at: new Date().toISOString(),
              taskId: taskId ?? step.taskId
            }
          : step
      )
    );
  };

  const markRuntimeFailure = (stepId: string, message: string) => {
    patchRuntimeStep(stepId, "failed", message);
    setRuntimeStage("error");
    setStreamingState({
      title: locale === "zh" ? "运行异常" : "Run Error",
      text: message,
      startedAt: new Date().toISOString()
    });
  };

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
    setWorkspaceTargetDir(`D:\\Bee2\\artifacts\\deliverables\\${scene.id}`);
    setWorkspaceAllowWrite(true);
    setWorkspaceAllowExecute(false);

    if (scene.id === "skills_factory") {
      setWorkerCount(6);
      setScoutCount(5);
      setMcpConnectorsText("filesystem,github,notion,slack,openai-developers");
      setFactorySkillId("skill_factory_designer");
      setFactorySkillName("Skill Factory Designer");
      setFactorySkillDescription("Designs, validates and promotes reusable enterprise skills.");
      setFactoryStrategy("tool_first");
      return;
    }

    if (scene.id === "video_creator") {
      setWorkerCount(5);
      setScoutCount(4);
      setMcpConnectorsText("canva,figma,google-drive,slack,filesystem");
      setFactorySkillId("skill_video_storyline");
      setFactorySkillName("Video Storyline Composer");
      setFactorySkillDescription("Builds short-video scripts, storyboard blocks and CTA variants.");
      setFactoryStrategy("tree_of_thought");
      return;
    }

    setWorkerCount(4);
    setScoutCount(3);
    setMcpConnectorsText("filesystem,github,notion,slack");
    setFactorySkillId("skill_future_assistant");
    setFactorySkillName("Future Assistant Skill");
    setFactorySkillDescription("Auto-evolving skill for multi-turn delivery and review.");
    setFactoryStrategy("tool_first");
  };

  const clearTaskInput = () => {
    setGoal("");
    setContextRefs("");
    setConstraintsText("{}");
    setConstraintsError("");
  };

  const refreshData = async () => {
    const [skillsData, eventsData, auditsData, pheromoneData, pulse, life, reports] = await Promise.all([
      listSkills(),
      listEvolutionEvents(),
      listCandidateAudits(40),
      listScoutPheromones(30, true),
      getEvolutionTelemetry(180),
      getAutonomousLifeStatus(),
      getAutonomousLifeReports(40)
    ]);
    setSkills(skillsData);
    setEvents(eventsData);
    setAudits(auditsData);
    setPheromones(pheromoneData);
    setEvolutionTelemetry(pulse);
    setLifeStatus(life);
    setLifeReports(reports);
  };

  const refreshTokenTelemetry = async () => {
    const stats = await getLlmTokenStats(200);
    setTokenStats(stats);
  };

  const refreshEvolutionTelemetry = async () => {
    const [pulse, life, reports] = await Promise.all([getEvolutionTelemetry(180), getAutonomousLifeStatus(), getAutonomousLifeReports(24)]);
    setEvolutionTelemetry(pulse);
    setLifeStatus(life);
    setLifeReports(reports);
  };

  const nudgeAutonomousLife = (reason: string) => {
    touchAutonomousLife(reason)
      .then((status) => setLifeStatus(status))
      .catch(() => undefined);
  };

  useEffect(() => {
    Promise.all([refreshData(), refreshTokenTelemetry()]).catch((error) => setToast(errorText(error)));
    applyTemplate(scenario);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      Promise.all([refreshTokenTelemetry(), refreshEvolutionTelemetry()]).catch(() => undefined);
    }, 8000);
    return () => window.clearInterval(timer);
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

  const buildMcpConnectors = () =>
    mcpConnectorsText
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 20);

  const mergeExecutionConstraints = (base: Record<string, unknown>) => ({
    ...base,
    scenarioId,
    swarmConfig: {
      workerCount,
      scoutCount,
      ensembleMode: "weighted-vote"
    },
    mcpConnectors: buildMcpConnectors(),
    workspaceBinding: {
      targetDir: workspaceTargetDir.trim(),
      allowWrite: workspaceAllowWrite,
      allowExecute: workspaceAllowExecute
    },
    skillFactoryHints: {
      preferredStrategy: factoryStrategy,
      targetSkillId: factorySkillId
    }
  });

  const buildContextRefs = () =>
    contextRefs
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

  const appendWorkflowLog = (message: string) => {
    setWorkflowLogs((prev) => [message, ...prev].slice(0, 80));
  };

  const appendChat = (payload: Omit<ChatMessage, "id">): string => {
    const id = `${payload.role}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setChatMessages((prev) => [
      ...prev,
      {
        ...payload,
        id
      }
    ]);
    return id;
  };

  useEffect(() => {
    if (lifeReports.length === 0) {
      return;
    }
    const rows = [...lifeReports].sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
    for (const report of rows) {
      if (!report.id || seenLifeReportIds.current.has(report.id)) {
        continue;
      }
      seenLifeReportIds.current.add(report.id);
      const signature = lifeReportSignature(report);
      const latest = lastLifeDigestRef.current;
      if (latest && latest.signature === signature) {
        const nextStreak = latest.streak + 1;
        lastLifeDigestRef.current = { ...latest, streak: nextStreak };
        setChatMessages((prev) =>
          prev.map((item) =>
            item.id === latest.messageId
              ? {
                  ...item,
                  title: `${lifeReportTitle(locale)} x${nextStreak}`,
                  text: lifeReportText(report, locale, nextStreak),
                  time: report.createdAt
                }
              : item
          )
        );
        continue;
      }
      const messageId = appendChat({
        role: "life",
        title: lifeReportTitle(locale),
        text: lifeReportText(report, locale, 1),
        time: report.createdAt
      });
      lastLifeDigestRef.current = {
        signature,
        messageId,
        streak: 1
      };
    }
  }, [lifeReports, locale]);

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
    const payload = task.resultPayload as Record<string, unknown> | undefined;
    const rawDeliverables = payload?.deliverables as Record<string, unknown> | undefined;
    if (rawDeliverables && typeof rawDeliverables === "object") {
      const workspacePath = typeof rawDeliverables.workspacePath === "string" ? rawDeliverables.workspacePath : "";
      const files = Array.isArray(rawDeliverables.files)
        ? rawDeliverables.files.filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
        : [];
      if (workspacePath) {
        lines.push(`Workspace: ${workspacePath}`);
      }
      if (files.length > 0) {
        lines.push(
          "Files:\n" +
            files
              .map((item) => `- ${String(item.path ?? "")}${item.absolutePath ? ` -> ${String(item.absolutePath)}` : ""}`)
              .join("\n")
        );
      }
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

  const runSelfEvolutionGuard = async (task: TaskDetail, source: string) => {
    const guard = await ensureEvolution(task.id, true, source);
    setAutoFeedbackState(`guard:${guard.status}`);
    if (guard.candidateId) {
      setCandidateId(guard.candidateId);
    }
    appendWorkflowLog(`self-evolution: ${guard.status}${guard.reason ? `(${guard.reason})` : ""}`);
    appendChat({
      role: "system",
      title: locale === "zh" ? "自进化保障" : "Self-Evolution Guard",
      text:
        guard.status === "submitted"
          ? locale === "zh"
            ? "已自动补齐反馈并推动技能候选更新。"
            : "Feedback auto-filled and skill candidate evolution was triggered."
          : locale === "zh"
            ? `已检查保障链路，本轮无需追加进化（${guard.reason ?? "已有反馈"}）。`
            : `Guard checked. No extra evolution needed this round (${guard.reason ?? "feedback already exists"}).`,
      time: new Date().toISOString(),
      taskId: task.id
    });
    return guard;
  };

  const runTaskRound = async () => {
    nudgeAutonomousLife("ui.run-task-round");
    const constraints = parseConstraints();
    if (!constraints) {
      return;
    }

    setRuntimeSteps(buildRuntimeSteps([flow[0]]));
    setRuntimeStage("planning");
    patchRuntimeStep("plan", "running", locale === "zh" ? "正在生成计划图..." : "Building plan graph...");
    setStreamingState({
      title: locale === "zh" ? "蜂群执行中" : "Swarm Running",
      text: locale === "zh" ? "正在进行计划与执行准备..." : "Preparing plan and execution...",
      startedAt: new Date().toISOString()
    });

    appendChat({
      role: "user",
      title: scenario.title[locale],
      text: `${labels.goal}: ${goal}\n${labels.context}: ${contextRefs}`,
      time: new Date().toISOString()
    });

    let activeStepId = "plan";
    try {
      setBusy(true);
      setRuntimeStage("executing");
      patchRuntimeStep("exec-0", "running", locale === "zh" ? "正在执行步骤..." : "Executing step...");
      activeStepId = "exec-0";
      setStreamingState({
        title: locale === "zh" ? "蜂群执行中" : "Swarm Running",
        text: `${flow[0]}...`,
        startedAt: new Date().toISOString()
      });

      const spec: TaskSpec = {
        goal,
        constraints: mergeExecutionConstraints(constraints),
        contextRefs: buildContextRefs(),
        qualityTarget,
        priority
      };
      const task = await createTask(spec, false);
      setLatestTask(task);

      const planSize = task.planGraph?.nodes?.length ?? 0;
      patchRuntimeStep(
        "plan",
        "completed",
        locale === "zh" ? `计划图已生成（${planSize} 个节点）` : `Plan graph generated (${planSize} nodes).`,
        task.id
      );

      const summaryText = typeof task.resultPayload?.summary === "string" ? task.resultPayload.summary : task.goal;
      patchRuntimeStep("exec-0", "completed", summaryText, task.id);
      appendChat({ role: "swarm", title: flow[0], text: summaryText, time: task.createdAt, taskId: task.id });
      appendChat({
        role: "deliverable",
        title: ui.deliverable,
        text: buildDeliverableText(task),
        time: task.updatedAt,
        taskId: task.id
      });
      patchRuntimeStep("deliverable", "completed", locale === "zh" ? "已输出可交付产物" : "Deliverable generated.", task.id);

      setRuntimeStage("feedback");
      patchRuntimeStep("feedback", "running", locale === "zh" ? "正在吸收反馈信号..." : "Absorbing feedback signals...");
      activeStepId = "feedback";
      if (autoInferFeedbackEnabled) {
        const autoTurns: ConversationTurn[] = [
          { role: "user", content: `${labels.goal}: ${goal}\n${labels.context}: ${contextRefs}` },
          { role: "assistant", content: summaryText },
          { role: "assistant", content: buildDeliverableText(task) }
        ];
        try {
          await applyAutoFeedback(task, "task-round", autoTurns);
          patchRuntimeStep("feedback", "completed", locale === "zh" ? "自动反馈已提交" : "Auto feedback submitted.", task.id);
        } catch (autoError) {
          appendWorkflowLog(`auto-feedback error: ${errorText(autoError)}`);
          patchRuntimeStep(
            "feedback",
            "failed",
            locale === "zh" ? "自动反馈失败，改走自进化保障兜底" : "Auto feedback failed. Fallback to self-evolution guard.",
            task.id
          );
        }
      } else {
        patchRuntimeStep(
          "feedback",
          "completed",
          locale === "zh" ? "自动反馈关闭，等待手动反馈" : "Auto feedback disabled. Waiting for manual feedback.",
          task.id
        );
      }

      setRuntimeStage("evolving");
      patchRuntimeStep("evolution", "running", locale === "zh" ? "正在执行自进化保障..." : "Running self-evolution guard...");
      activeStepId = "evolution";
      setStreamingState({
        title: locale === "zh" ? "蜂群进化中" : "Swarm Evolving",
        text: locale === "zh" ? "正在确保技能持续进化..." : "Ensuring skills evolve continuously...",
        taskId: task.id,
        startedAt: new Date().toISOString()
      });
      const guard = await runSelfEvolutionGuard(task, "task-round-guard");
      patchRuntimeStep(
        "evolution",
        "completed",
        guard.status === "submitted"
          ? locale === "zh"
            ? "已触发技能进化候选"
            : "Evolution candidate triggered."
          : locale === "zh"
            ? "保障检查通过（无需新增候选）"
            : "Guard check passed (no new candidate needed).",
        task.id
      );

      await refreshData();
      appendWorkflowLog(`task: ${task.id}`);
      setRuntimeStage("completed");
      setStreamingState({
        title: locale === "zh" ? "执行完成" : "Run Completed",
        text: locale === "zh" ? "任务、反馈与自进化保障已完成。" : "Task, feedback, and self-evolution guard are complete.",
        taskId: task.id,
        startedAt: new Date().toISOString()
      });
      setToast(`OK: ${task.id}`);
    } catch (error) {
      const message = errorText(error);
      setToast(message);
      appendWorkflowLog(`error: ${message}`);
      markRuntimeFailure(activeStepId, message);
    } finally {
      setBusy(false);
      window.setTimeout(() => setStreamingState(null), 1400);
    }
  };

  const runScenarioFlow = async () => {
    nudgeAutonomousLife("ui.run-scenario-flow");
    const constraints = parseConstraints();
    if (!constraints) {
      return;
    }

    setRuntimeSteps(buildRuntimeSteps(flow));
    setRuntimeStage("planning");
    patchRuntimeStep("plan", "running", locale === "zh" ? "正在准备场景流程计划..." : "Preparing scenario plan...");
    setStreamingState({
      title: locale === "zh" ? "蜂群执行中" : "Swarm Running",
      text: locale === "zh" ? "正在进入多步骤流程..." : "Entering multi-step workflow...",
      startedAt: new Date().toISOString()
    });

    appendWorkflowLog(`start: ${scenario.title[locale]} | ${flow.join(" -> ")}`);
    appendChat({ role: "user", title: scenario.title[locale], text: goal, time: new Date().toISOString() });

    let activeStepId = "plan";
    try {
      setWorkflowBusy(true);
      let previousTask: TaskDetail | undefined;
      const flowTurns: ConversationTurn[] = [{ role: "user", content: goal }];

      for (let i = 0; i < flow.length; i += 1) {
        const step = flow[i];
        const stepId = `exec-${i}`;
        setRuntimeStage("executing");
        patchRuntimeStep(stepId, "running", locale === "zh" ? `正在执行：${step}` : `Running: ${step}`);
        setStreamingState({
          title: locale === "zh" ? "蜂群执行中" : "Swarm Running",
          text: locale === "zh" ? `步骤 ${i + 1}/${flow.length}: ${step}` : `Step ${i + 1}/${flow.length}: ${step}`,
          startedAt: new Date().toISOString()
        });
        activeStepId = stepId;
        appendWorkflowLog(`step ${i + 1}/${flow.length}: ${step}`);

        const mergedConstraints = {
          ...mergeExecutionConstraints(constraints),
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

        if (i === 0) {
          const planSize = task.planGraph?.nodes?.length ?? 0;
          patchRuntimeStep(
            "plan",
            "completed",
            locale === "zh" ? `计划图已准备（${planSize} 个节点）` : `Plan graph prepared (${planSize} nodes).`,
            task.id
          );
        }

        previousTask = task;
        setLatestTask(task);
        const summaryText = typeof task.resultPayload?.summary === "string" ? task.resultPayload.summary : task.goal;
        patchRuntimeStep(stepId, "completed", summaryText, task.id);
        appendChat({ role: "swarm", title: step, text: summaryText, time: task.updatedAt, taskId: task.id });
        flowTurns.push({ role: "assistant", content: summaryText });
        appendWorkflowLog(`done: ${step} | ${task.id}`);
      }

      if (previousTask) {
        patchRuntimeStep("deliverable", "running", locale === "zh" ? "正在合成交付产物..." : "Compiling deliverable...");
        appendChat({
          role: "deliverable",
          title: ui.deliverable,
          text: buildDeliverableText(previousTask),
          time: previousTask.updatedAt,
          taskId: previousTask.id
        });
        patchRuntimeStep("deliverable", "completed", locale === "zh" ? "最终交付已生成" : "Final deliverable generated.", previousTask.id);

        setRuntimeStage("feedback");
        patchRuntimeStep("feedback", "running", locale === "zh" ? "正在吸收反馈信号..." : "Absorbing feedback signals...");
        activeStepId = "feedback";
        if (autoInferFeedbackEnabled) {
          flowTurns.push({ role: "assistant", content: buildDeliverableText(previousTask) });
          try {
            await applyAutoFeedback(previousTask, "scenario-flow", flowTurns);
            patchRuntimeStep("feedback", "completed", locale === "zh" ? "自动反馈已提交" : "Auto feedback submitted.", previousTask.id);
          } catch (autoError) {
            appendWorkflowLog(`auto-feedback error: ${errorText(autoError)}`);
            patchRuntimeStep(
              "feedback",
              "failed",
              locale === "zh" ? "自动反馈失败，改走自进化保障兜底" : "Auto feedback failed. Fallback to self-evolution guard.",
              previousTask.id
            );
          }
        } else {
          patchRuntimeStep(
            "feedback",
            "completed",
            locale === "zh" ? "自动反馈关闭，等待手动反馈" : "Auto feedback disabled. Waiting for manual feedback.",
            previousTask.id
          );
        }

        setRuntimeStage("evolving");
        patchRuntimeStep("evolution", "running", locale === "zh" ? "正在执行自进化保障..." : "Running self-evolution guard...");
        activeStepId = "evolution";
        setStreamingState({
          title: locale === "zh" ? "蜂群进化中" : "Swarm Evolving",
          text: locale === "zh" ? "正在确保技能持续进化..." : "Ensuring skills evolve continuously...",
          taskId: previousTask.id,
          startedAt: new Date().toISOString()
        });
        const guard = await runSelfEvolutionGuard(previousTask, "scenario-flow-guard");
        patchRuntimeStep(
          "evolution",
          "completed",
          guard.status === "submitted"
            ? locale === "zh"
              ? "已触发技能进化候选"
              : "Evolution candidate triggered."
            : locale === "zh"
              ? "保障检查通过（无需新增候选）"
              : "Guard check passed (no new candidate needed).",
          previousTask.id
        );
      }

      await refreshData();
      setRuntimeStage("completed");
      setStreamingState({
        title: locale === "zh" ? "流程完成" : "Workflow Completed",
        text: locale === "zh" ? "多步骤流程、反馈与进化保障已完成。" : "Workflow, feedback, and evolution guard are complete.",
        startedAt: new Date().toISOString()
      });
      setToast(locale === "zh" ? "流程执行完成" : "Workflow completed");
    } catch (error) {
      const message = errorText(error);
      setToast(message);
      appendWorkflowLog(`error: ${message}`);
      markRuntimeFailure(activeStepId, message);
    } finally {
      setWorkflowBusy(false);
      window.setTimeout(() => setStreamingState(null), 1400);
    }
  };

  const sendFeedback = async () => {
    nudgeAutonomousLife("ui.submit-feedback");
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
    } catch (error) {
      appendWorkflowLog(`auto-feedback error: ${errorText(error)}`);
    }
    try {
      await runSelfEvolutionGuard(latestTask, "manual-trigger-guard");
      await refreshData();
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const applySkillTemplate = (template: SkillTemplate) => {
    const matchedScenario = SCENARIOS.find((item) => item.id === template.suggestedScenario);
    if (matchedScenario) {
      setScenarioId(template.suggestedScenario);
      applyTemplate(matchedScenario);
    }
    setSelectedTemplateId(template.id);
    setFactorySkillId(`skill_${template.category}_${template.id.replace(/^tpl_/, "")}`.slice(0, 64));
    setFactorySkillName(template.title.en);
    setFactorySkillDescription(template.description.en);
    setFactoryStrategy(template.strategy);
    setMcpConnectorsText(template.connectors.join(","));
  };

  const releaseTemplateToCanary = async () => {
    if (!selectedTemplate) {
      return;
    }

    try {
      setTemplateReleaseBusy(true);
      const skillId = factorySkillId.trim().toLowerCase().replace(/\s+/g, "_");
      let resolvedSkillId = skillId;

      try {
        const created = await createSkillFromFactory({
          skillId,
          name: factorySkillName,
          description: factorySkillDescription,
          baseStrategy: factoryStrategy,
          mcpConnectors: buildMcpConnectors(),
          ioSchema: selectedTemplate.ioSchema,
          permissions: selectedTemplate.permissions,
          costBudget: selectedTemplate.costBudget
        });
        resolvedSkillId = created.id;
        appendWorkflowLog(`factory created: ${created.id}`);
      } catch (error) {
        const msg = errorText(error).toLowerCase();
        if (!msg.includes("already exists")) {
          throw error;
        }
        appendWorkflowLog(`factory reuse existing: ${skillId}`);
      }

      const candidate = await createSkillCandidate(resolvedSkillId, {
        targetSkill: resolvedSkillId,
        changeType: `template_${selectedTemplate.id}`,
        patch: selectedTemplate.deltaPatch,
        evidence: {
          source: "template-market",
          templateId: selectedTemplate.id,
          category: selectedTemplate.category,
          at: new Date().toISOString()
        }
      });
      setCandidateId(candidate.id);
      appendWorkflowLog(`template candidate: ${candidate.id}`);

      const replay = await evaluateShadowReplay(resolvedSkillId, candidate.id, 60);
      appendWorkflowLog(`template replay ratio=${replay.improvementRatio.toFixed(3)}`);

      const decision = await promoteCandidate(resolvedSkillId, candidate.id);
      appendWorkflowLog(`template canary decision=${decision.decision}`);

      setSelectedSkillId(resolvedSkillId);
      await refreshData();
      setToast(
        locale === "zh"
          ? `模板已进入灰度链路：${decision.decision}（ratio=${replay.improvementRatio.toFixed(3)}）`
          : `Template canary flow done: ${decision.decision} (ratio=${replay.improvementRatio.toFixed(3)})`
      );
    } catch (error) {
      setToast(errorText(error));
    } finally {
      setTemplateReleaseBusy(false);
    }
  };

  const createSkillByFactory = async () => {
    try {
      const skill = await createSkillFromFactory({
        skillId: factorySkillId,
        name: factorySkillName,
        description: factorySkillDescription,
        baseStrategy: factoryStrategy,
        mcpConnectors: buildMcpConnectors(),
        ioSchema: {
          input: ["goal", "constraints", "contextRefs"],
          output: ["summary", "planGraph", "deliverable"]
        },
        permissions: { network: true, filesystem: "read_write" },
        costBudget: { maxTokens: 14000 }
      });
      await refreshData();
      setSelectedSkillId(skill.id);
      setToast(locale === "zh" ? `Skills工厂已创建: ${skill.id}` : `Skill created by factory: ${skill.id}`);
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

  const runLifeCycleNow = async () => {
    try {
      const status = await runAutonomousLifeCycle("ui-manual-cycle");
      setLifeStatus(status);
      await refreshEvolutionTelemetry();
      setToast(locale === "zh" ? "生命引擎已执行一轮" : "Autonomous life cycle executed");
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

  const triggerDownload = (blob: Blob, fileName: string) => {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1200);
  };

  const openDeliverableFolderNow = async () => {
    if (!latestTask) {
      setToast(ui.noTask);
      return;
    }
    try {
      await openDeliverable(latestTask.id, "folder");
      setToast(locale === "zh" ? "已打开目录" : "Folder opened");
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const openDeliverableFileNow = async (artifactPath?: string) => {
    if (!latestTask) {
      setToast(ui.noTask);
      return;
    }
    try {
      await openDeliverable(latestTask.id, "file", artifactPath);
      setToast(locale === "zh" ? "已打开文件" : "File opened");
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const downloadDeliverableFileNow = async (artifactPath?: string) => {
    if (!latestTask) {
      setToast(ui.noTask);
      return;
    }
    try {
      const { blob, fileName } = await downloadDeliverableFile(latestTask.id, artifactPath);
      triggerDownload(blob, fileName);
      setToast(ui.downloadDone);
    } catch (error) {
      setToast(errorText(error));
    }
  };

  const downloadDeliverableArchiveNow = async () => {
    if (!latestTask) {
      setToast(ui.noTask);
      return;
    }
    try {
      const { blob, fileName } = await downloadDeliverableArchive(latestTask.id);
      triggerDownload(blob, fileName);
      setToast(ui.downloadDone);
    } catch (error) {
      setToast(errorText(error));
    }
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

      {view === "workspace" && (
        <div className="floating-telemetry">
          <div className="telemetry-pill">
            <span>{locale === "zh" ? "实时 Token" : "Live Tokens"}</span>
            <strong>{tokenStats?.totalTokens ?? 0}</strong>
          </div>
          <div className="telemetry-pill">
            <span>{locale === "zh" ? "估算成本(USD)" : "Est. Cost (USD)"}</span>
            <strong>${estimatedCostUsd.toFixed(4)}</strong>
          </div>
          <div className="telemetry-pill">
            <span>{locale === "zh" ? "并行度" : "Parallelism"}</span>
            <strong>{liveParallelism}</strong>
          </div>
          <div className="telemetry-pill">
            <span>{locale === "zh" ? "模型路数" : "Model Routes"}</span>
            <strong>{tokenStats?.byModel.length ?? 0}</strong>
          </div>
          <div className="telemetry-pill">
            <span>{locale === "zh" ? "生命体状态" : "Life Status"}</span>
            <strong>
              {lifeStatus
                ? lifeStatus.running
                  ? lifeStatus.status === "idle"
                    ? locale === "zh"
                      ? "巡航"
                      : "Cruise"
                    : locale === "zh"
                      ? "活跃"
                      : "Active"
                  : locale === "zh"
                    ? "停止"
                    : "Stopped"
                : "-"}
            </strong>
          </div>
          <div className="telemetry-pill">
            <span>{locale === "zh" ? "生命迭代轮次" : "Life Cycles"}</span>
            <strong>{lifeStatus?.cycles ?? 0}</strong>
          </div>
          <div className="telemetry-pill">
            <span>{locale === "zh" ? "进化进度" : "Evolution Progress"}</span>
            <strong>{evolutionProgressScore.toFixed(1)}%</strong>
          </div>
          <div className="telemetry-pill">
            <span>{locale === "zh" ? "进化速度" : "Evolution Velocity"}</span>
            <strong>{evolutionVelocityScore.toFixed(1)}%</strong>
          </div>
        </div>
      )}

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
            <section className="card runtime-card">
              <div className="hero-head">
                <h2>{locale === "zh" ? "任务运行状态" : "Task Run Status"}</h2>
                <span className={`badge runtime-stage runtime-stage-${runtimeStage}`}>{runtimeStageLabel(runtimeStage, locale)}</span>
              </div>
              <div className="runtime-track">
                {runtimeSteps.length === 0 ? (
                  <div className="runtime-track-empty">{locale === "zh" ? "等待任务启动" : "Waiting for run to start"}</div>
                ) : (
                  runtimeSteps.map((step) => <div key={step.id} className={`runtime-segment runtime-segment-${step.status}`} title={step.title} />)
                )}
              </div>
              <p className="hint">{runtimeProgress}%</p>
              <details className="runtime-details" open>
                <summary>{locale === "zh" ? "可折叠步骤详情" : "Collapsible Step Details"}</summary>
                {runtimeSteps.length === 0 ? (
                  <p className="hint">{locale === "zh" ? "开始任务后展示详细步骤。" : "Detailed steps appear after a run starts."}</p>
                ) : (
                  <ul className="runtime-step-list">
                    {runtimeSteps.map((step) => (
                      <li key={step.id} className="runtime-step-item">
                        <div className="runtime-step-row">
                          <strong>{step.title}</strong>
                          <span className={`badge step-badge step-badge-${step.status}`}>{runtimeStepStatusLabel(step.status, locale)}</span>
                        </div>
                        <p>{step.detail}</p>
                        {step.at && <small>{toTimeLabel(step.at)}</small>}
                      </li>
                    ))}
                  </ul>
                )}
              </details>
            </section>

            <section className="card swimlane-card">
              <div className="hero-head">
                <h2>{locale === "zh" ? "蜂群并行线程泳道" : "Swarm Parallel Swimlanes"}</h2>
                <span className="badge">
                  {locale === "zh" ? "并行线程" : "Threads"}: {liveParallelism}
                </span>
              </div>
              <div className="swimlane-wrap">
                {swimlanes.map((lane) => (
                  <div key={lane.key} className="swimlane-row">
                    <div className="swimlane-label">{locale === "zh" ? lane.labelZh : lane.labelEn}</div>
                    <div className="swimlane-track">
                      {lane.items.length === 0 ? (
                        <span className="swimlane-empty">{locale === "zh" ? "暂无事件" : "No events"}</span>
                      ) : (
                        lane.items.map((evt) => (
                          <span key={evt.id} className={`swimlane-event swimlane-event-${lane.key}`} title={actionLabel(evt.topic, locale)}>
                            {actionLabel(evt.topic, locale)}
                          </span>
                        ))
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>

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
                  {deliverableView && (
                    <div className="deliverable-meta">
                      <p className="hint">
                        {locale === "zh" ? "场景" : "Scene"}: <strong>{deliverableView.scene}</strong> |{" "}
                        {locale === "zh" ? "状态" : "Status"}: <strong>{deliverableView.status}</strong>
                      </p>
                      {deliverableView.workspacePath && (
                        <p className="hint">
                          {locale === "zh" ? "交付目录" : "Workspace"}: <code>{deliverableView.workspacePath}</code>
                        </p>
                      )}
                      <div className="inline-actions">
                        <button className="button" onClick={openDeliverableFolderNow}>
                          {ui.openFolder}
                        </button>
                        <button className="button" onClick={downloadDeliverableArchiveNow}>
                          {ui.downloadZip}
                        </button>
                        <button className="button" onClick={() => openDeliverableFileNow()}>
                          {ui.openFile}
                        </button>
                        <button className="button" onClick={() => downloadDeliverableFileNow()}>
                          {ui.downloadFile}
                        </button>
                      </div>
                      {deliverableView.primaryArtifact && (
                        <p className="hint">
                          {locale === "zh" ? "主产物" : "Primary Artifact"}: <code>{deliverableView.primaryArtifact}</code>
                        </p>
                      )}
                      {deliverableView.error && <p className="error">{deliverableView.error}</p>}
                      {deliverableView.reason && <p className="hint">{deliverableView.reason}</p>}
                      {deliverableView.files.length > 0 ? (
                        <ul className="artifact-list">
                          {deliverableView.files.map((file) => (
                            <li key={`${file.path}-${file.absolutePath ?? ""}`}>
                              <div className="artifact-title">
                                <code>{file.path}</code>
                                {file.kind && <span className="badge">{file.kind}</span>}
                              </div>
                              {file.absolutePath && <div className="hint">{file.absolutePath}</div>}
                              <div className="inline-actions artifact-actions">
                                <button className="button" onClick={() => openDeliverableFileNow(file.absolutePath ?? file.path)}>
                                  {ui.openFile}
                                </button>
                                <button className="button" onClick={() => downloadDeliverableFileNow(file.absolutePath ?? file.path)}>
                                  {ui.downloadFile}
                                </button>
                              </div>
                            </li>
                          ))}
                        </ul>
                      ) : deliverableView.plannedFiles.length > 0 ? (
                        <ul className="artifact-list artifact-list-planned">
                          {deliverableView.plannedFiles.map((file) => (
                            <li key={`planned-${file.path}`}>
                              <code>{file.path}</code>
                              <span className="hint">
                                {locale === "zh" ? "计划产物（尚未写入）" : "Planned (not written)"}
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  )}
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
                {timelineGroups.length === 0 && <p className="hint">{ui.emptyChat}</p>}
                {timelineGroups.map((group) => (
                  <div key={group.key} className="timeline-group">
                    <div className="timeline-day">{group.label}</div>
                    {group.items.map((item) => (
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
                ))}
                {streamingState && (
                  <article className="chat-row chat-row-swarm">
                    <div className="bubble bubble-swarm bubble-streaming">
                      <div className="bubble-head">
                        <strong>{streamingState.title}</strong>
                        <span>{toTimeLabel(streamingState.startedAt)}</span>
                      </div>
                      <p>
                        {streamingState.text}
                        <span className="streaming-dots" aria-hidden="true">
                          <span>.</span>
                          <span>.</span>
                          <span>.</span>
                        </span>
                      </p>
                    </div>
                  </article>
                )}
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

                <div className="row">
                  <div>
                    <label>{locale === "zh" ? "工蜂数量" : "Worker Count"}</label>
                    <input type="number" min={1} max={12} value={workerCount} onChange={(event) => setWorkerCount(Number(event.target.value))} />
                  </div>
                  <div>
                    <label>{locale === "zh" ? "斥候数量" : "Scout Count"}</label>
                    <input type="number" min={1} max={12} value={scoutCount} onChange={(event) => setScoutCount(Number(event.target.value))} />
                  </div>
                </div>
                <label>{locale === "zh" ? "MCP连接器（逗号分隔）" : "MCP Connectors (comma separated)"}</label>
                <input value={mcpConnectorsText} onChange={(event) => setMcpConnectorsText(event.target.value)} placeholder="filesystem,github,notion,slack" />

                <label>{locale === "zh" ? "绑定本地交付目录" : "Bound Local Delivery Folder"}</label>
                <input
                  value={workspaceTargetDir}
                  onChange={(event) => setWorkspaceTargetDir(event.target.value)}
                  placeholder={locale === "zh" ? "例如: D:\\Bee2\\deliverables" : "Example: D:\\Bee2\\deliverables"}
                />

                <div className="row">
                  <label className="toggle">
                    <input type="checkbox" checked={workspaceAllowWrite} onChange={(event) => setWorkspaceAllowWrite(event.target.checked)} />
                    <span>{locale === "zh" ? "允许写入实物文件" : "Allow Writing Artifacts"}</span>
                  </label>
                  <label className="toggle">
                    <input type="checkbox" checked={workspaceAllowExecute} onChange={(event) => setWorkspaceAllowExecute(event.target.checked)} />
                    <span>{locale === "zh" ? "允许后续执行" : "Allow Execute Permission"}</span>
                  </label>
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
                  <input type="checkbox" checked={autoInferFeedbackEnabled} onChange={(event) => setAutoInferFeedbackEnabled(event.target.checked)} />
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
                  <input type="number" min={0} max={1} step={0.01} value={explicitScore} onChange={(event) => setExplicitScore(Number(event.target.value))} />
                  <label>{ui.corrections}</label>
                  <textarea rows={3} value={corrections} onChange={(event) => setCorrections(event.target.value)} />
                  <label>{ui.retryCount}</label>
                  <input type="number" min={0} value={retryCount} onChange={(event) => setRetryCount(Number(event.target.value))} />
                  <label>{ui.editDistance}</label>
                  <input type="number" min={0} max={1} step={0.01} value={editDistance} onChange={(event) => setEditDistance(Number(event.target.value))} />
                  <label>{ui.adoptionRate}</label>
                  <input type="number" min={0} max={1} step={0.01} value={adoptionRate} onChange={(event) => setAdoptionRate(Number(event.target.value))} />
                  <label>{ui.errorRateRise}</label>
                  <input type="number" min={0} max={1} step={0.01} value={errorRateRise} onChange={(event) => setErrorRateRise(Number(event.target.value))} />
                  <button className="button" onClick={sendFeedback} disabled={!latestTask}>
                    {ui.submitFeedback}
                  </button>
                </details>
              </section>
            )}

            {sideTab === "evolution" && (
              <>
                <section className="card side-card">
                  <h2>{locale === "zh" ? "进化脉搏" : "Evolution Pulse"}</h2>
                  {lifeStatus && (
                    <>
                      <p className="hint">
                        {locale === "zh" ? "生命体状态" : "Life Status"}:{" "}
                        <strong>
                          {lifeStatus.running
                            ? lifeStatus.status === "idle"
                              ? locale === "zh"
                                ? "空闲巡航"
                                : "Idle Cruise"
                              : locale === "zh"
                                ? "活跃代谢"
                                : "Active Metabolism"
                            : locale === "zh"
                              ? "未运行"
                              : "Stopped"}
                        </strong>
                      </p>
                      <p className="hint">
                        {locale === "zh" ? "循环次数" : "Cycles"}: {lifeStatus.cycles} |{" "}
                        {locale === "zh" ? "最近一轮耗时" : "Last Cycle"}: {lifeStatus.lastCycleSeconds.toFixed(2)}s
                        {lifeStatus.lastCycleAgeSeconds !== null && lifeStatus.lastCycleAgeSeconds !== undefined
                          ? ` | ${locale === "zh" ? "距今" : "Age"}: ${lifeStatus.lastCycleAgeSeconds.toFixed(1)}s`
                          : ""}
                      </p>
                      {lifeStatus.lastReport && (
                        <div className="life-report-card">
                          <p className="hint">
                            <strong>{locale === "zh" ? "我刚学到" : "I just learned"}</strong>:{" "}
                            {lifeReportNarrative(lifeStatus.lastReport, locale).learned}
                          </p>
                          <p className="hint">
                            <strong>{locale === "zh" ? "下一轮准备" : "Next cycle"}</strong>:{" "}
                            {lifeReportNarrative(lifeStatus.lastReport, locale).next}
                          </p>
                        </div>
                      )}
                      <div className="inline-actions">
                        <button className="button" onClick={() => nudgeAutonomousLife("ui-touch-life")}>
                          {locale === "zh" ? "唤醒生命体" : "Nudge Life"}
                        </button>
                        <button className="button button-primary" onClick={runLifeCycleNow}>
                          {locale === "zh" ? "立即迭代一轮" : "Run Cycle Now"}
                        </button>
                      </div>
                    </>
                  )}
                  {evolutionTelemetry ? (
                    <>
                      <p className="hint">
                        {locale === "zh" ? "窗口" : "Window"}: {evolutionTelemetry.windowMinutes}m |{" "}
                        {locale === "zh" ? "活跃信息素" : "Active Pheromones"}: {evolutionTelemetry.activePheromones}
                      </p>
                      <div className="pulse-metric">
                        <div className="pulse-row">
                          <strong>{locale === "zh" ? "进度分" : "Progress Score"}</strong>
                          <span>{evolutionTelemetry.speed.progressScore.toFixed(1)}%</span>
                        </div>
                        <div className="pulse-bar">
                          <span style={{ width: `${Math.max(2, evolutionTelemetry.speed.progressScore)}%` }} />
                        </div>
                      </div>
                      <div className="pulse-metric">
                        <div className="pulse-row">
                          <strong>{locale === "zh" ? "速度分" : "Velocity Score"}</strong>
                          <span>{evolutionTelemetry.speed.velocityScore.toFixed(1)}%</span>
                        </div>
                        <div className="pulse-bar pulse-bar-velocity">
                          <span style={{ width: `${Math.max(2, evolutionTelemetry.speed.velocityScore)}%` }} />
                        </div>
                      </div>
                      <ul className="compact-list">
                        <li>
                          {locale === "zh" ? "近5分钟事件/分钟" : "Events/min (5m)"}: {evolutionTelemetry.speed.eventsPerMinute5M.toFixed(2)}
                        </li>
                        <li>
                          {locale === "zh" ? "近60分钟 提案/晋升" : "Proposals/Promotions (60m)"}:{" "}
                          {evolutionTelemetry.speed.proposalsLast60M}/{evolutionTelemetry.speed.promotionsLast60M}
                        </li>
                        <li>
                          {locale === "zh" ? "24h 成功率" : "24h Success Rate"}: {(evolutionTelemetry.tasks.successRate24H * 100).toFixed(1)}%
                        </li>
                        <li>
                          {locale === "zh" ? "24h 平均决策时长(分钟)" : "Avg Decision Minutes (24h)"}:{" "}
                          {evolutionTelemetry.speed.avgDecisionMinutes24H.toFixed(1)}
                        </li>
                      </ul>
                      <p className="hint">{locale === "zh" ? "角色吞吐(60m)" : "Role Throughput (60m)"}</p>
                      <div className="role-throughput-grid">
                        <span>Scout {evolutionTelemetry.roles.scoutEvents60M}</span>
                        <span>Worker {evolutionTelemetry.roles.workerEvents60M}</span>
                        <span>Worm {evolutionTelemetry.roles.wormEvents60M}</span>
                        <span>Queen {evolutionTelemetry.roles.queenEvents60M}</span>
                      </div>
                      {swarmSkewHint && <p className="hint">{swarmSkewHint}</p>}
                      <p className="hint">{locale === "zh" ? "进化趋势" : "Evolution Trend"}</p>
                      <div className="pulse-timeline">
                        {evolutionTimelineBars.map((item) => (
                          <div key={item.bucket} className="pulse-timeline-col" title={`${toTimeLabel(item.bucket)} | ${item.events}`}>
                            <span style={{ height: `${item.heightPct}%` }} />
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p className="hint">{locale === "zh" ? "正在加载进化脉搏..." : "Loading evolution pulse..."}</p>
                  )}
                </section>

                <section className="card side-card">
                  <h2>{ui.swarm}</h2>
                  <p className="hint">
                    {locale === "zh"
                      ? `当前编队：工蜂 ${workerCount} / 斥候 ${scoutCount}`
                      : `Current squad: workers ${workerCount} / scouts ${scoutCount}`}
                  </p>
                  <ul className="compact-list">
                    {roleStats.map((item) => (
                      <li key={item.role.key}>
                        {item.role.name[locale]} | {item.count}
                        {item.latest && (
                          <span className="hint-block">
                            {ui.roleAction}: {actionLabel(item.latest.topic, locale)} | {ui.roleAt}: {toTimeLabel(item.latest.createdAt)}
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
                  <h2>{locale === "zh" ? "Skills 工厂" : "Skills Factory"}</h2>
                  <p className="hint">
                    {locale === "zh"
                      ? "把 MCP 接入与技能模板直接铸造成新 Skill，并纳入自进化链路。"
                      : "Forge MCP connectors and templates into a new Skill and attach it to self-evolution."}
                  </p>
                  <label>{locale === "zh" ? "技能ID" : "Skill ID"}</label>
                  <input value={factorySkillId} onChange={(event) => setFactorySkillId(event.target.value)} />
                  <label>{locale === "zh" ? "技能名称" : "Skill Name"}</label>
                  <input value={factorySkillName} onChange={(event) => setFactorySkillName(event.target.value)} />
                  <label>{locale === "zh" ? "技能说明" : "Description"}</label>
                  <textarea rows={3} value={factorySkillDescription} onChange={(event) => setFactorySkillDescription(event.target.value)} />
                  <label>{locale === "zh" ? "策略" : "Strategy"}</label>
                  <select value={factoryStrategy} onChange={(event) => setFactoryStrategy(event.target.value)}>
                    <option value="tool_first">tool_first</option>
                    <option value="tree_of_thought">tree_of_thought</option>
                    <option value="review_repair_loop">review_repair_loop</option>
                  </select>
                  <button className="button button-primary" onClick={createSkillByFactory}>
                    {locale === "zh" ? "创建技能" : "Create Skill"}
                  </button>
                </section>

                <section className="card side-card">
                  <h2>{locale === "zh" ? "模板市场（灰度发布）" : "Template Market (Canary)"}</h2>
                  <label>{locale === "zh" ? "选择模板" : "Choose Template"}</label>
                  <select value={selectedTemplateId} onChange={(event) => setSelectedTemplateId(event.target.value)}>
                    {SKILL_TEMPLATE_MARKET.map((tpl) => (
                      <option key={tpl.id} value={tpl.id}>
                        {tpl.title[locale]} ({tpl.category})
                      </option>
                    ))}
                  </select>
                  {selectedTemplate && (
                    <div className="template-note">
                      <strong>{selectedTemplate.title[locale]}</strong>
                      <p>{selectedTemplate.description[locale]}</p>
                      <small>MCP: {selectedTemplate.connectors.join(", ")}</small>
                    </div>
                  )}
                  <div className="inline-actions">
                    <button className="button" onClick={() => selectedTemplate && applySkillTemplate(selectedTemplate)}>
                      {locale === "zh" ? "应用模板" : "Apply Template"}
                    </button>
                    <button className="button button-primary" onClick={releaseTemplateToCanary} disabled={templateReleaseBusy}>
                      {templateReleaseBusy ? (locale === "zh" ? "灰度中..." : "Canary...") : locale === "zh" ? "一键灰度发布" : "One-click Canary"}
                    </button>
                  </div>
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
