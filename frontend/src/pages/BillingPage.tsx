import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  createSubscriptionCheckout,
  createTopupCheckout,
  getBillingSummary,
  getSpendingUsage,
  listBillingTransactions,
  switchWorkspaceToTrial,
} from "../api";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";

const nfMoney = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

const BUCKET_OPTIONS = [10, 30, 60, 180, 360, 1440];

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

function toLocalDatetimeValue(d: Date) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function parseLocalDatetimeValue(v: string): Date {
  return new Date(v);
}

export function BillingPage() {
  const qc = useQueryClient();
  const { token } = useAuth();
  const { activeWorkspaceId, isOwner } = useWorkspaceContext();
  const [topupAmount, setTopupAmount] = useState("10");
  const [timeFrom, setTimeFrom] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return toLocalDatetimeValue(d);
  });
  const [timeTo, setTimeTo] = useState(() => toLocalDatetimeValue(new Date()));
  const [bucketMinutes, setBucketMinutes] = useState(60);

  const timeFromIso = useMemo(
    () => parseLocalDatetimeValue(timeFrom).toISOString(),
    [timeFrom]
  );
  const timeToIso = useMemo(
    () => parseLocalDatetimeValue(timeTo).toISOString(),
    [timeTo]
  );

  const summaryQuery = useQuery({
    queryKey: ["billingSummary", activeWorkspaceId],
    queryFn: () => getBillingSummary(token!, activeWorkspaceId!),
    enabled: !!token && !!activeWorkspaceId && isOwner,
  });

  const txQuery = useQuery({
    queryKey: ["billingTx", activeWorkspaceId],
    queryFn: () => listBillingTransactions(token!, activeWorkspaceId!),
    enabled: !!token && !!activeWorkspaceId && isOwner,
  });

  const spendingQuery = useQuery({
    queryKey: [
      "billingSpending",
      activeWorkspaceId,
      timeFromIso,
      timeToIso,
      bucketMinutes,
    ],
    queryFn: () =>
      getSpendingUsage(token!, {
        workspaceId: activeWorkspaceId!,
        timeFrom: timeFromIso,
        timeTo: timeToIso,
        bucketMinutes,
      }),
    enabled: !!token && !!activeWorkspaceId && isOwner,
  });
  const switchToTrialMutation = useMutation({
    mutationFn: async () => switchWorkspaceToTrial(token!, activeWorkspaceId!),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["billingSummary", activeWorkspaceId] });
      void qc.invalidateQueries({ queryKey: ["workspacePlanLimits", activeWorkspaceId] });
    },
  });

  const chartData = useMemo(
    () =>
      (spendingQuery.data?.buckets ?? []).map((b) => ({
        label: new Date(b.bucket_start).toLocaleDateString("ru-RU", { month: "short", day: "numeric" }),
        spent: Number(b.spent_usd),
      })),
    [spendingQuery.data]
  );

  const applyPreset = (hours: number) => {
    const end = new Date();
    const start = new Date(end.getTime() - hours * 3600 * 1000);
    setTimeFrom(toLocalDatetimeValue(start));
    setTimeTo(toLocalDatetimeValue(end));
  };

  if (!activeWorkspaceId) {
    return <div className="card muted">Выберите рабочее пространство для биллинга.</div>;
  }
  if (!isOwner) {
    return <div className="card muted">Раздел биллинга доступен только владельцу.</div>;
  }

  const redirectTo = async (urlPromise: Promise<{ url: string }>) => {
    const result = await urlPromise;
    window.location.href = result.url;
  };
  const currentPlan = summaryQuery.data?.plan;
  const subscriptionStatus = summaryQuery.data?.subscription_status ?? "";
  const isSubscriptionExpired =
    currentPlan !== "trial" &&
    !["active", "trialing"].includes(subscriptionStatus.toLowerCase());
  const confirmAndSwitchToTrial = () => {
    const ok = window.confirm(
      "Подтвердите переход на тариф Триал. Текущая платная подписка будет отменена."
    );
    if (ok) {
      switchToTrialMutation.mutate();
    }
  };

  return (
    <div className="grid gap-16">
      <div className="page-header">
        <h2 className="page-title">Биллинг</h2>
      </div>
      <div className="grid grid-2">
        <div className="card">
          <div className="muted">Тариф</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{summaryQuery.data?.plan ?? "..."}</div>
          <div className="muted">Статус: {summaryQuery.data?.subscription_status ?? "..."}</div>
          <div className="mt-12">
            {currentPlan === "trial" && (
              <>
                <button
                  className="btn"
                  type="button"
                  onClick={() =>
                    redirectTo(
                      createSubscriptionCheckout(token!, {
                        workspace_id: activeWorkspaceId,
                        plan: "lite",
                      })
                    )
                  }
                >
                  Купить Лайт ($10/мес)
                </button>
                <button
                  className="btn ghost mt-12"
                  type="button"
                  onClick={() =>
                    redirectTo(
                      createSubscriptionCheckout(token!, {
                        workspace_id: activeWorkspaceId,
                        plan: "full",
                      })
                    )
                  }
                >
                  Купить Фулл ($20/мес)
                </button>
              </>
            )}
            {currentPlan === "lite" && (
              <>
                {isSubscriptionExpired && (
                  <button
                    className="btn"
                    type="button"
                    onClick={confirmAndSwitchToTrial}
                    disabled={switchToTrialMutation.isPending}
                  >
                    {switchToTrialMutation.isPending
                      ? "Переключаем..."
                      : "Вернуться на Триал"}
                  </button>
                )}
                <button
                  className={`${isSubscriptionExpired ? "btn ghost mt-12" : "btn"}`}
                  type="button"
                  onClick={() =>
                    redirectTo(
                      createSubscriptionCheckout(token!, {
                        workspace_id: activeWorkspaceId,
                        plan: "full",
                      })
                    )
                  }
                >
                  Купить Фулл ($20/мес)
                </button>
              </>
            )}
            {currentPlan === "full" && (
              <>
                {isSubscriptionExpired && (
                  <button
                    className="btn"
                    type="button"
                    onClick={confirmAndSwitchToTrial}
                    disabled={switchToTrialMutation.isPending}
                  >
                    {switchToTrialMutation.isPending
                      ? "Переключаем..."
                      : "Вернуться на Триал"}
                  </button>
                )}
              </>
            )}
          </div>
        </div>
        <div className="card">
          <div className="muted">Баланс</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>
            {nfMoney.format(Number(summaryQuery.data?.balance_usd ?? 0))}
          </div>
          <div className="flex gap-8 mt-12">
            <input
              className="input"
              type="number"
              min="1"
              step="1"
              value={topupAmount}
              onChange={(e) => setTopupAmount(e.target.value)}
            />
            <button
              className="btn"
              type="button"
              onClick={() =>
                redirectTo(
                  createTopupCheckout(token!, {
                    workspace_id: activeWorkspaceId,
                    amount_usd: topupAmount,
                  })
                )
              }
            >
              Пополнить
            </button>
          </div>
        </div>
      </div>
      <div className="card">
        <div className="page-header">
          <h3 className="token-usage-title">Расход денег</h3>
          <div className="muted">Потрачено: {nfMoney.format(Number(spendingQuery.data?.spent_total_usd ?? 0))}</div>
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
          <div className="token-usage-presets">
            <span className="muted">Быстро:</span>
            <button type="button" className="btn ghost" onClick={() => applyPreset(24)}>
              24 ч
            </button>
            <button type="button" className="btn ghost" onClick={() => applyPreset(24 * 7)}>
              7 дн
            </button>
            <button type="button" className="btn ghost" onClick={() => applyPreset(24 * 30)}>
              30 дн
            </button>
          </div>
        </div>
        <div style={{ height: 300 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <XAxis dataKey="label" />
              <YAxis />
              <Tooltip formatter={(v: number | string) => nfMoney.format(Number(v))} />
              <Line dataKey="spent" stroke="#2563eb" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="card">
        <h3 className="token-usage-title">История платежей</h3>
        <table className="table mt-12">
          <thead>
            <tr>
              <th>Дата</th>
              <th>Тип</th>
              <th>Описание</th>
              <th>Сумма</th>
            </tr>
          </thead>
          <tbody>
            {(txQuery.data ?? []).map((tx) => (
              <tr key={tx.id}>
                <td>{new Date(tx.created_at).toLocaleString("ru-RU")}</td>
                <td>{tx.transaction_type}</td>
                <td>{tx.description || "-"}</td>
                <td>{nfMoney.format(Number(tx.amount_usd))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
