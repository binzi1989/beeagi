import { useEffect, useMemo, useState } from "react";
import { getLlmConfig, getLlmTokenStats, updateLlmConfig } from "../api/client";
import { LlmConfigView, LlmTokenStatsResponse } from "../types";

type Locale = "zh" | "en";

type Props = {
  locale: Locale;
  onToast: (message: string) => void;
};

function errorText(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

const UI = {
  zh: {
    title: "LLM 配置与 Token 统计",
    subtitle: "单独页面：模型路由配置 + 用量统计",
    save: "保存配置",
    refresh: "刷新统计",
    mode: "模型模式",
    model: "主模型名",
    deepseekModel: "DeepSeek 模型名",
    localEndpoint: "本地推理端点",
    enterpriseEndpoint: "企业网关端点",
    deepseekEndpoint: "DeepSeek 端点",
    timeout: "超时（秒）",
    llmApiKey: "通用 API Key（留空不改）",
    deepseekApiKey: "DeepSeek API Key（留空不改）",
    keyState: "密钥状态",
    llmConfigured: "通用 Key 已配置",
    llmMissing: "通用 Key 未配置",
    deepseekConfigured: "DeepSeek Key 已配置",
    deepseekMissing: "DeepSeek Key 未配置",
    runtimePath: "运行时配置文件",
    totalTasks: "任务数",
    totalTokens: "总 Token",
    promptTokens: "输入 Token",
    completionTokens: "输出 Token",
    avgTokens: "任务均值",
    byModel: "按模型统计",
    recent: "最近任务 Token",
    noData: "暂无统计数据",
    saved: "LLM 配置已保存"
  },
  en: {
    title: "LLM Config & Token Usage",
    subtitle: "Standalone page for model routing configuration and usage stats",
    save: "Save Config",
    refresh: "Refresh Stats",
    mode: "Mode",
    model: "Primary Model",
    deepseekModel: "DeepSeek Model",
    localEndpoint: "Local Endpoint",
    enterpriseEndpoint: "Enterprise Endpoint",
    deepseekEndpoint: "DeepSeek Endpoint",
    timeout: "Timeout (sec)",
    llmApiKey: "Shared API Key (blank = unchanged)",
    deepseekApiKey: "DeepSeek API Key (blank = unchanged)",
    keyState: "Key Status",
    llmConfigured: "Shared key configured",
    llmMissing: "Shared key missing",
    deepseekConfigured: "DeepSeek key configured",
    deepseekMissing: "DeepSeek key missing",
    runtimePath: "Runtime config path",
    totalTasks: "Tasks",
    totalTokens: "Total Tokens",
    promptTokens: "Prompt Tokens",
    completionTokens: "Completion Tokens",
    avgTokens: "Average / Task",
    byModel: "By Model",
    recent: "Recent Task Tokens",
    noData: "No stats yet",
    saved: "LLM config saved"
  }
} as const;

export default function LlmConsolePage({ locale, onToast }: Props) {
  const ui = UI[locale];
  const [config, setConfig] = useState<LlmConfigView | null>(null);
  const [stats, setStats] = useState<LlmTokenStatsResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [llmMode, setLlmMode] = useState("mock");
  const [llmModelName, setLlmModelName] = useState("");
  const [deepseekModelName, setDeepseekModelName] = useState("");
  const [localEndpoint, setLocalEndpoint] = useState("");
  const [enterpriseEndpoint, setEnterpriseEndpoint] = useState("");
  const [deepseekEndpoint, setDeepseekEndpoint] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState(20);
  const [llmApiKeyInput, setLlmApiKeyInput] = useState("");
  const [deepseekApiKeyInput, setDeepseekApiKeyInput] = useState("");

  const applyConfig = (next: LlmConfigView) => {
    setConfig(next);
    setLlmMode(next.llmMode);
    setLlmModelName(next.llmModelName);
    setDeepseekModelName(next.deepseekModelName);
    setLocalEndpoint(next.localModelEndpoint);
    setEnterpriseEndpoint(next.enterpriseModelEndpoint);
    setDeepseekEndpoint(next.deepseekEndpoint);
    setTimeoutSeconds(next.llmTimeoutSeconds);
    setLlmApiKeyInput("");
    setDeepseekApiKeyInput("");
  };

  const loadAll = async () => {
    const [conf, stat] = await Promise.all([getLlmConfig(), getLlmTokenStats(300)]);
    applyConfig(conf);
    setStats(stat);
  };

  useEffect(() => {
    loadAll().catch((error) => onToast(errorText(error)));
  }, []);

  const saveConfig = async () => {
    try {
      setBusy(true);
      const payload: {
        llmMode: string;
        llmModelName: string;
        deepseekModelName: string;
        localModelEndpoint: string;
        enterpriseModelEndpoint: string;
        deepseekEndpoint: string;
        llmTimeoutSeconds: number;
        llmApiKey?: string;
        deepseekApiKey?: string;
      } = {
        llmMode,
        llmModelName,
        deepseekModelName,
        localModelEndpoint: localEndpoint,
        enterpriseModelEndpoint: enterpriseEndpoint,
        deepseekEndpoint,
        llmTimeoutSeconds: timeoutSeconds
      };
      if (llmApiKeyInput.trim()) {
        payload.llmApiKey = llmApiKeyInput.trim();
      }
      if (deepseekApiKeyInput.trim()) {
        payload.deepseekApiKey = deepseekApiKeyInput.trim();
      }
      const updated = await updateLlmConfig(payload);
      applyConfig(updated);
      onToast(ui.saved);
    } catch (error) {
      onToast(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const refreshStats = async () => {
    try {
      setRefreshing(true);
      const stat = await getLlmTokenStats(300);
      setStats(stat);
    } catch (error) {
      onToast(errorText(error));
    } finally {
      setRefreshing(false);
    }
  };

  const summaryCards = useMemo(() => {
    if (!stats) {
      return [];
    }
    return [
      { label: ui.totalTasks, value: stats.totalTasks.toString() },
      { label: ui.totalTokens, value: stats.totalTokens.toString() },
      { label: ui.promptTokens, value: stats.promptTokens.toString() },
      { label: ui.completionTokens, value: stats.completionTokens.toString() },
      { label: ui.avgTokens, value: stats.averageTokensPerTask.toString() }
    ];
  }, [stats, ui]);

  return (
    <div className="llm-page">
      <section className="card">
        <div className="card-head">
          <h2>{ui.title}</h2>
          <button className="button" onClick={refreshStats} disabled={refreshing}>
            {ui.refresh}
          </button>
        </div>
        <p className="hint">{ui.subtitle}</p>
      </section>

      <section className="card">
        <h2>{ui.title}</h2>
        <label>{ui.mode}</label>
        <select value={llmMode} onChange={(event) => setLlmMode(event.target.value)}>
          <option value="mock">mock</option>
          <option value="ollama">ollama</option>
          <option value="openai_compatible">openai_compatible</option>
          <option value="deepseek">deepseek</option>
        </select>
        <label>{ui.model}</label>
        <input value={llmModelName} onChange={(event) => setLlmModelName(event.target.value)} />
        <label>{ui.deepseekModel}</label>
        <input value={deepseekModelName} onChange={(event) => setDeepseekModelName(event.target.value)} />
        <label>{ui.localEndpoint}</label>
        <input value={localEndpoint} onChange={(event) => setLocalEndpoint(event.target.value)} />
        <label>{ui.enterpriseEndpoint}</label>
        <input value={enterpriseEndpoint} onChange={(event) => setEnterpriseEndpoint(event.target.value)} />
        <label>{ui.deepseekEndpoint}</label>
        <input value={deepseekEndpoint} onChange={(event) => setDeepseekEndpoint(event.target.value)} />
        <label>{ui.timeout}</label>
        <input
          type="number"
          min={1}
          max={120}
          value={timeoutSeconds}
          onChange={(event) => setTimeoutSeconds(Number(event.target.value))}
        />
        <label>{ui.llmApiKey}</label>
        <input type="password" value={llmApiKeyInput} onChange={(event) => setLlmApiKeyInput(event.target.value)} />
        <label>{ui.deepseekApiKey}</label>
        <input
          type="password"
          value={deepseekApiKeyInput}
          onChange={(event) => setDeepseekApiKeyInput(event.target.value)}
        />
        <button className="button button-primary" onClick={saveConfig} disabled={busy}>
          {ui.save}
        </button>
        {config && (
          <div className="report-box">
            <p className="hint">
              {ui.keyState}: {config.llmApiKeyConfigured ? ui.llmConfigured : ui.llmMissing}
            </p>
            <p className="hint">
              {ui.keyState}: {config.deepseekApiKeyConfigured ? ui.deepseekConfigured : ui.deepseekMissing}
            </p>
            <p className="hint">
              {ui.runtimePath}: {config.runtimeConfigPath}
            </p>
          </div>
        )}
      </section>

      <section className="card">
        <h2>{ui.totalTokens}</h2>
        {summaryCards.length === 0 ? (
          <p className="hint">{ui.noData}</p>
        ) : (
          <div className="stats-grid">
            {summaryCards.map((item) => (
              <article key={item.label} className="swarm-card">
                <strong>{item.label}</strong>
                <p className="result-text">{item.value}</p>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <h2>{ui.byModel}</h2>
        {!stats || stats.byModel.length === 0 ? (
          <p className="hint">{ui.noData}</p>
        ) : (
          <div className="table-wrap">
            <table className="stats-table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Tasks</th>
                  <th>Total</th>
                  <th>Prompt</th>
                  <th>Completion</th>
                  <th>Avg</th>
                </tr>
              </thead>
              <tbody>
                {stats.byModel.map((item) => (
                  <tr key={`${item.provider}-${item.model}`}>
                    <td>{item.provider}</td>
                    <td>{item.model}</td>
                    <td>{item.taskCount}</td>
                    <td>{item.totalTokens}</td>
                    <td>{item.promptTokens}</td>
                    <td>{item.completionTokens}</td>
                    <td>{item.averageTokens}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>{ui.recent}</h2>
        {!stats || stats.recentTasks.length === 0 ? (
          <p className="hint">{ui.noData}</p>
        ) : (
          <div className="table-wrap">
            <table className="stats-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Total</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {stats.recentTasks.slice(0, 25).map((item) => (
                  <tr key={item.taskId}>
                    <td>{item.taskId.slice(0, 8)}</td>
                    <td>{item.provider}</td>
                    <td>{item.model}</td>
                    <td>{item.totalTokens}</td>
                    <td>{new Date(item.createdAt).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
