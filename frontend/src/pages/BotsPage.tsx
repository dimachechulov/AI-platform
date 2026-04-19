import { useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { deleteBot, listBots } from "../api";
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
            Workspace: {activeWorkspaceId ?? "—"} · Всего: {stats.total}
            {!isOwner && " · Режим просмотра"}
          </div>
          {isOwner && (
            <button className="btn" type="button" onClick={() => navigate("/app/bots/new")}>
              Создать бота
            </button>
          )}
        </div>
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Имя</th>
              <th>Workspace</th>
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
