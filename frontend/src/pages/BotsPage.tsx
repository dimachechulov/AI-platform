import { useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { deleteBot, getWorkspacePlanLimits, listBots } from "../api";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";
import { Bot } from "../types";
import { useNavigate } from "react-router-dom";

export function BotsPage() {
  const { token } = useAuth();
  const { activeWorkspaceId, isOwner } = useWorkspaceContext();
  const navigate = useNavigate();

  const botsQuery = useQuery({
    queryKey: ["bots", activeWorkspaceId],
    queryFn: () => listBots(token || "", activeWorkspaceId),
    enabled: !!token,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      if (!token) throw new Error("Нет токена");
      return deleteBot(token, id);
    },
    onSuccess: () => void botsQuery.refetch(),
  });
  const limitsQuery = useQuery({
    queryKey: ["workspacePlanLimits", activeWorkspaceId],
    queryFn: () => getWorkspacePlanLimits(token || "", activeWorkspaceId || 0),
    enabled: !!token && !!activeWorkspaceId,
  });

  const handleEdit = (bot: Bot) => {
    navigate(`/app/bots/${bot.id}`);
  };

  const stats = useMemo(
    () => ({
      total: botsQuery.data?.length || 0,
    }),
    [botsQuery.data]
  );

  return (
    <div className="grid gap-16">
      <div className="page-header">
        <h2 className="page-title">Боты</h2>
        <div className="actions flex gap-8" style={{ alignItems: "center" }}>
          <div className="muted">
            Пространство: {activeWorkspaceId ?? "—"} · Всего: {stats.total}
            {!isOwner && " · Режим просмотра"}
          </div>
          {isOwner && (
            <button
              className="btn"
              type="button"
              onClick={() => navigate("/app/bots/new")}
              disabled={!limitsQuery.data?.can_create_bots}
              title={
                !limitsQuery.data?.can_create_bots
                  ? limitsQuery.data?.reason || "Достигнут лимит плана на создание ботов"
                  : undefined
              }
            >
              Создать бота
            </button>
          )}
        </div>
      </div>
      {isOwner && !limitsQuery.data?.can_create_bots && (
        <div className="card">
          <div className="error">
            {limitsQuery.data?.reason ||
              `Достигнут лимит ботов: ${limitsQuery.data?.usage.bots}/${limitsQuery.data?.limits.max_bots ?? "∞"}`}
          </div>
        </div>
      )}

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>№</th>
              <th>Имя</th>
              <th>Пространство</th>
              <th>Создан</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {botsQuery.isLoading && (
              <tr>
                <td colSpan={5}>Загрузка...</td>
              </tr>
            )}
            {botsQuery.data?.map((bot) => (
              <tr key={bot.id}>
                <td>{bot.id}</td>
                <td>{bot.name}</td>
                <td>{bot.workspace_id}</td>
                <td>{bot.created_at}</td>
                <td className="flex gap-8">
                  {isOwner && (
                    <>
                      <button
                        className="btn ghost"
                        type="button"
                        onClick={() => handleEdit(bot)}
                      >
                        Редактировать
                      </button>
                      <button
                        className="btn ghost"
                        type="button"
                        onClick={() => deleteMutation.mutate(bot.id)}
                      >
                        Удалить
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
