import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { getBot, updateBot } from "../api";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";
import { Bot, BotGraphConfig } from "../types";

export function BotEditPage() {
  const { token } = useAuth();
  const { isOwner } = useWorkspaceContext();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const botId = Number(id);

  const botQuery = useQuery({
    queryKey: ["bot", botId],
    queryFn: () => getBot(token || "", botId),
    enabled: !!token && Number.isFinite(botId),
  });

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async (payload: Partial<{
      name: string;
      system_prompt: string;
      graph: BotGraphConfig;
      temperature: string;
      max_tokens: number;
    }>) => {
      if (!token) throw new Error("Нет токена");
      return updateBot(token, botId, payload);
    },
    onSuccess: () => {
      setSuccess("Сохранено");
      void botQuery.refetch();
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Ошибка обновления");
    },
  });

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const formData = new FormData(e.currentTarget);
    const name = String(formData.get("name") || "");
    const system_prompt = String(formData.get("system_prompt") || "");
    const temperature = String(formData.get("temperature") || "");
    const max_tokens = Number(formData.get("max_tokens") || 0);
    const graphRaw = String(formData.get("graph") || "");

    let graph: BotGraphConfig | undefined;
    try {
      graph = JSON.parse(graphRaw);
      
      // Убеждаемся, что nodes является массивом
      if (graph && !Array.isArray(graph.nodes)) {
        // Если nodes - строка, пытаемся распарсить её
        if (typeof graph.nodes === "string") {
          try {
            graph.nodes = JSON.parse(graph.nodes);
          } catch {
            setError("nodes должен быть массивом объектов");
            return;
          }
        } else {
          setError("nodes должен быть массивом объектов");
          return;
        }
      }
      
      // Проверяем структуру graph
      if (!graph || !graph.entry_node_id || !Array.isArray(graph.nodes)) {
        setError("Graph должен содержать entry_node_id и nodes (массив)");
        return;
      }
    } catch (err) {
      setError("Graph должен быть валидным JSON");
      return;
    }

    mutation.mutate({
      name,
      system_prompt,
      temperature,
      max_tokens,
      graph,
    });
  };

  const bot = botQuery.data as Bot | undefined;

  // Нормализуем конфигурацию перед отображением
  const normalizedConfig = bot?.config ? (() => {
    const config = { ...bot.config };
    // Убеждаемся, что nodes является массивом
    if (config.nodes && typeof config.nodes === "string") {
      try {
        config.nodes = JSON.parse(config.nodes);
      } catch {
        // Если не JSON, оставляем как есть (будет ошибка при сохранении)
      }
    }
    if (!Array.isArray(config.nodes)) {
      config.nodes = [];
    }
    return config;
  })() : undefined;

  return (
    <div className="grid gap-16">
      <div className="page-header">
        <h2 className="page-title">
          {isOwner ? "Редактирование" : "Просмотр"} бота #{botId}
        </h2>
        <div className="actions">
          <button className="btn ghost" onClick={() => navigate(-1)} type="button">
            Назад
          </button>
        </div>
      </div>
      {botQuery.isLoading && <div className="muted">Загрузка...</div>}
      {!isOwner && (
        <div className="card" style={{ background: '#fff3cd', border: '1px solid #ffc107' }}>
          <div style={{ color: '#856404' }}>
            ⚠️ Режим только для просмотра. Только владелец воркспейса может редактировать ботов.
          </div>
        </div>
      )}
      {bot && (
        <form className="grid gap-12" onSubmit={handleSubmit}>
          <div className="grid grid-2 gap-12">
            <label>
              <div className="muted">Название</div>
              <input className="input" name="name" defaultValue={bot.name} required disabled={!isOwner} />
            </label>
            <label>
              <div className="muted">System prompt</div>
              <input
                className="input"
                name="system_prompt"
                defaultValue={bot.system_prompt}
                required
                disabled={!isOwner}
              />
            </label>
          </div>
          <div className="grid grid-2 gap-12">
            <label>
              <div className="muted">Temperature</div>
              <input
                className="input"
                name="temperature"
                defaultValue={bot.temperature}
                required
                disabled={!isOwner}
              />
            </label>
            <label>
              <div className="muted">Max tokens</div>
              <input
                className="input"
                name="max_tokens"
                type="number"
                defaultValue={bot.max_tokens}
                required
                disabled={!isOwner}
              />
            </label>
          </div>
          <label>
            <div className="muted">Graph (JSON)</div>
            <textarea
              className="textarea"
              name="graph"
              defaultValue={normalizedConfig ? JSON.stringify(normalizedConfig, null, 2) : ""}
              rows={14}
              disabled={!isOwner}
            />
          </label>
          {error && <div className="error">{error}</div>}
          {success && <div className="muted">{success}</div>}
          {isOwner && (
            <div className="flex" style={{ justifyContent: "flex-end" }}>
              <button className="btn" type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Сохраняю..." : "Сохранить"}
              </button>
            </div>
          )}
        </form>
      )}
    </div>
  );
}

