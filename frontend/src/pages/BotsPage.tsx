import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { createBot, deleteBot, listBots } from "../api";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";
import { Bot, BotGraphConfig } from "../types";
import { useNavigate } from "react-router-dom";

const DEFAULT_GRAPH = `{
  "entry_node_id": "main",
  "nodes": [
    {
      "id": "main",
      "name": "General",
      "system_prompt": "Ты дружелюбный ассистент.",
      "use_rag": true,
      "api_tool_ids": [],
      "allowed_document_ids": [],
      "transitions": []
    }
  ]
}`;

export function BotsPage() {
  const { token } = useAuth();
  const { activeWorkspaceId, isOwner } = useWorkspaceContext();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    system_prompt: "",
    temperature: "0.7",
    max_tokens: 2048,
    graph: DEFAULT_GRAPH,
  });
  const [error, setError] = useState<string | null>(null);

  const botsQuery = useQuery({
    queryKey: ["bots", activeWorkspaceId],
    queryFn: () => listBots(token || "", activeWorkspaceId),
    enabled: !!token,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!token || !activeWorkspaceId) throw new Error("Нет workspace");
      let graph: BotGraphConfig;
      try {
        graph = JSON.parse(form.graph);
      } catch (err) {
        throw new Error("Граф должен быть валидным JSON");
      }
      return createBot(token, {
        name: form.name,
        workspace_id: activeWorkspaceId,
        system_prompt: form.system_prompt,
        graph,
        temperature: form.temperature,
        max_tokens: Number(form.max_tokens),
      });
    },
    onSuccess: () => {
      setForm({
        name: "",
        system_prompt: "",
        temperature: "0.7",
        max_tokens: 2048,
        graph: DEFAULT_GRAPH,
      });
      void botsQuery.refetch();
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Ошибка");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      if (!token) throw new Error("Нет токена");
      return deleteBot(token, id);
    },
    onSuccess: () => void botsQuery.refetch(),
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    createMutation.mutate();
  };

  const handleUpdateGraph = (bot: Bot) => {
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
        <div className="muted">
          Workspace: {activeWorkspaceId ?? "—"} · Всего: {stats.total}
          {!isOwner && " · Режим просмотра"}
        </div>
      </div>
      {isOwner && (
        <div className="card">
        <form className="grid gap-12" onSubmit={handleSubmit}>
          <div className="grid grid-2 gap-12">
            <label>
              <div className="muted">Название</div>
              <input
                className="input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            </label>
            <label>
              <div className="muted">System prompt</div>
              <input
                className="input"
                value={form.system_prompt}
                onChange={(e) =>
                  setForm({ ...form, system_prompt: e.target.value })
                }
                required
              />
            </label>
          </div>
          <div className="grid grid-2 gap-12">
            <label>
              <div className="muted">Temperature</div>
              <input
                className="input"
                type="text"
                value={form.temperature}
                onChange={(e) =>
                  setForm({ ...form, temperature: e.target.value })
                }
              />
            </label>
            <label>
              <div className="muted">Max tokens</div>
              <input
                className="input"
                type="number"
                value={form.max_tokens}
                onChange={(e) =>
                  setForm({ ...form, max_tokens: Number(e.target.value) })
                }
              />
            </label>
          </div>
          <label>
            <div className="muted">Graph JSON</div>
            <textarea
              className="textarea"
              value={form.graph}
              onChange={(e) => setForm({ ...form, graph: e.target.value })}
            />
          </label>
          {error && <div className="error">{error}</div>}
          <div className="flex" style={{ justifyContent: "flex-end" }}>
            <button className="btn" type="submit">
              Создать бота
            </button>
          </div>
        </form>
      </div>
      )}

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
                        onClick={() => handleUpdateGraph(bot)}
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

