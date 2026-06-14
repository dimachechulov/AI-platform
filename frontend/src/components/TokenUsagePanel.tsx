import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getTokenUsage, listBots, listTokenUsageModels } from "../api";
import { Bot } from "../types";

const BUCKET_OPTIONS = [5, 10, 15, 30, 60];

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

/** Значение для `<input type="datetime-local" />` в локальной зоне */
function toLocalDatetimeValue(d: Date) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function parseLocalDatetimeValue(v: string): Date {
  return new Date(v);
}

const nf = new Intl.NumberFormat("ru-RU");

type Props = {
  token: string | null;
  workspaceId: number | null;
};

export function TokenUsagePanel({ token, workspaceId }: Props) {
  const [timeFrom, setTimeFrom] = useState(() => {
    const t = new Date();
    t.setHours(t.getHours() - 3);
    return toLocalDatetimeValue(t);
  });
  const [timeTo, setTimeTo] = useState(() => toLocalDatetimeValue(new Date()));
  const [bucketMinutes, setBucketMinutes] = useState(10);
  const [botId, setBotId] = useState<number | "">("");
  const [model, setModel] = useState("");

  const timeFromIso = useMemo(
    () => parseLocalDatetimeValue(timeFrom).toISOString(),
    [timeFrom]
  );
  const timeToIso = useMemo(
    () => parseLocalDatetimeValue(timeTo).toISOString(),
    [timeTo]
  );

  const botsQuery = useQuery({
    queryKey: ["bots", workspaceId],
    queryFn: () => listBots(token!, workspaceId!),
    enabled: !!token && workspaceId != null,
  });

  const modelsQuery = useQuery({
    queryKey: [
      "tokenUsageModels",
      workspaceId,
      timeFromIso,
      timeToIso,
      botId === "" ? null : botId,
    ],
    queryFn: () =>
      listTokenUsageModels(token!, {
        workspaceId: workspaceId!,
        timeFrom: timeFromIso,
        timeTo: timeToIso,
        botId: botId === "" ? undefined : botId,
      }),
    enabled: !!token && workspaceId != null,
  });

  const usageQuery = useQuery({
    queryKey: [
      "tokenUsage",
      workspaceId,
      timeFromIso,
      timeToIso,
      bucketMinutes,
      botId === "" ? null : botId,
      model || null,
    ],
    queryFn: () =>
      getTokenUsage(token!, {
        workspaceId: workspaceId!,
        timeFrom: timeFromIso,
        timeTo: timeToIso,
        bucketMinutes,
        botId: botId === "" ? undefined : botId,
        model: model || undefined,
      }),
    enabled: !!token && workspaceId != null,
  });

  useEffect(() => {
    setModel("");
  }, [botId, workspaceId]);

  const chartData = useMemo(() => {
    const rows = usageQuery.data?.buckets ?? [];
    return rows.map((b) => {
      const start = new Date(b.bucket_start);
      return {
        label: start.toLocaleString("ru-RU", {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        }),
        input: b.input_tokens,
        output: b.output_tokens,
      };
    });
  }, [usageQuery.data]);

  const applyPreset = (hours: number) => {
    const end = new Date();
    const start = new Date(end.getTime() - hours * 3600 * 1000);
    setTimeFrom(toLocalDatetimeValue(start));
    setTimeTo(toLocalDatetimeValue(end));
  };

  if (!workspaceId) {
    return (
      <div className="card">
        <div className="muted">Выберите workspace, чтобы видеть расход токенов.</div>
      </div>
    );
  }

  const totals = usageQuery.data?.totals;
  const bots = botsQuery.data ?? [];

  return (
    <div className="card token-usage-panel">
      <div className="page-header" style={{ marginBottom: 12 }}>
        <div>
          <h3 className="token-usage-title">Расход токенов (LLM)</h3>
          <div className="muted" style={{ fontSize: 13 }}>
            Интервалы на графике выровнены по часу (UTC): например, при шаге 10 минут —
            13:00–13:10, 13:10–13:20 и т.д.
          </div>
        </div>
      </div>

      <div className="token-usage-filters">
        <label className="token-usage-field">
          <span className="muted">С</span>
          <input
            className="input"
            type="datetime-local"
            value={timeFrom}
            onChange={(e) => setTimeFrom(e.target.value)}
          />
        </label>
        <label className="token-usage-field">
          <span className="muted">По</span>
          <input
            className="input"
            type="datetime-local"
            value={timeTo}
            onChange={(e) => setTimeTo(e.target.value)}
          />
        </label>
        <label className="token-usage-field">
          <span className="muted">Шаг, мин</span>
          <select
            className="select"
            value={bucketMinutes}
            onChange={(e) => setBucketMinutes(Number(e.target.value))}
          >
            {BUCKET_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className="token-usage-field">
          <span className="muted">Бот</span>
          <select
            className="select"
            value={botId === "" ? "" : String(botId)}
            onChange={(e) => {
              const v = e.target.value;
              setBotId(v === "" ? "" : Number(v));
            }}
          >
            <option value="">Все боты</option>
            {bots.map((b: Bot) => (
              <option key={b.id} value={b.id}>
                {b.name} (#{b.id})
              </option>
            ))}
          </select>
        </label>
        <label className="token-usage-field">
          <span className="muted">Модель</span>
          <select
            className="select"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            <option value="">Все модели</option>
            {(modelsQuery.data?.models ?? []).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <div className="token-usage-presets">
          <span className="muted">Быстро:</span>
          <button type="button" className="btn ghost" onClick={() => applyPreset(3)}>
            3 ч
          </button>
          <button type="button" className="btn ghost" onClick={() => applyPreset(24)}>
            24 ч
          </button>
          <button type="button" className="btn ghost" onClick={() => applyPreset(24 * 7)}>
            7 дн
          </button>
        </div>
      </div>

      {usageQuery.isError && (
        <div className="token-usage-error">
          {(usageQuery.error as Error)?.message || "Ошибка загрузки"}
        </div>
      )}

      <div className="token-usage-kpis">
        <div className="token-usage-kpi">
          <div className="muted">Input</div>
          <div className="token-usage-kpi-value token-in">
            {usageQuery.isLoading ? "…" : nf.format(totals?.input_tokens ?? 0)}
          </div>
        </div>
        <div className="token-usage-kpi">
          <div className="muted">Output</div>
          <div className="token-usage-kpi-value token-out">
            {usageQuery.isLoading ? "…" : nf.format(totals?.output_tokens ?? 0)}
          </div>
        </div>
        <div className="token-usage-kpi">
          <div className="muted">Всего</div>
          <div className="token-usage-kpi-value">
            {usageQuery.isLoading
              ? "…"
              : nf.format((totals?.input_tokens ?? 0) + (totals?.output_tokens ?? 0))}
          </div>
        </div>
      </div>

      <div className="token-usage-chart-wrap">
        {usageQuery.isLoading ? (
          <div className="muted">Загрузка графика…</div>
        ) : chartData.length === 0 ? (
          <div className="muted">Нет данных за выбранный период и фильтры.</div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11, fill: "#64748b" }}
                interval="preserveStartEnd"
                minTickGap={24}
              />
              <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
              <Tooltip
                contentStyle={{
                  borderRadius: 8,
                  border: "1px solid #e2e8f0",
                  fontSize: 13,
                }}
                formatter={(value: number | string, name: string) => [
                  nf.format(Number(value)),
                  name === "input" ? "Input" : "Output",
                ]}
              />
              <Legend formatter={(v) => (v === "input" ? "Input" : "Output")} />
              <Line
                type="monotone"
                dataKey="input"
                name="input"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="output"
                name="output"
                stroke="#059669"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
