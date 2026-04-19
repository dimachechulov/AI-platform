import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { getBot, updateBot, listDocuments, listApiTools } from "../api";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";
import {
  Bot,
  BotGraphConfig,
  DEFAULT_GEMINI_MODEL,
  validateAllNodesReachableFromEntry,
  validateAlwaysExclusiveTransitions,
} from "../types";
import {
  BotGraphEditor,
  DEFAULT_BOT_GRAPH,
  normalizeBotGraph,
} from "../components/BotGraphEditor";
import { GeminiModelSelect } from "../components/GeminiModelSelect";

export function BotEditPage() {
  const queryClient = useQueryClient();
  const { token } = useAuth();
  const { isOwner } = useWorkspaceContext();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const botId = Number(id);

  const botQuery = useQuery({
    queryKey: ["bot", botId],
    queryFn: () => getBot(token || "", botId),
    enabled: !!token && Number.isFinite(botId),
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [temperature, setTemperature] = useState("0.7");
  const [maxTokens, setMaxTokens] = useState(2048);
  const [graph, setGraph] = useState<BotGraphConfig>(DEFAULT_BOT_GRAPH);

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
    onSuccess: (updated) => {
      setSuccess("Сохранено");
      queryClient.setQueryData(["bot", botId], updated);
      setName(updated.name);
      setSystemPrompt(updated.system_prompt);
      setTemperature(updated.temperature);
      setMaxTokens(updated.max_tokens);
      setGraph(normalizeBotGraph(updated.config));
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Ошибка обновления");
    },
  });

  /**
   * Синхронизация с сервером только при смене бота или первом успешном ответе.
   * Не добавлять botQuery.data в зависимости: при каждом новом объекте из кэша эффект бы
   * перезатирал локальный граф и поля.
   */
  useEffect(() => {
    if (!botQuery.isSuccess || !botQuery.data || botQuery.data.id !== botId) return;
    const b = botQuery.data;
    setName(b.name);
    setSystemPrompt(b.system_prompt);
    setTemperature(b.temperature);
    setMaxTokens(b.max_tokens);
    setGraph(normalizeBotGraph(b.config));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- см. комментарий выше
  }, [botId, botQuery.isSuccess]);

  const workspaceForLists = botQuery.data?.workspace_id;

  const documentsQuery = useQuery({
    queryKey: ["documents", workspaceForLists],
    queryFn: () => listDocuments(token || "", workspaceForLists!),
    enabled:
      !!token &&
      botQuery.isSuccess &&
      typeof workspaceForLists === "number" &&
      workspaceForLists > 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 30 * 60 * 1000,
  });

  const apiToolsQuery = useQuery({
    queryKey: ["apiTools", workspaceForLists],
    queryFn: () => listApiTools(token || "", workspaceForLists!),
    enabled:
      !!token &&
      botQuery.isSuccess &&
      typeof workspaceForLists === "number" &&
      workspaceForLists > 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 30 * 60 * 1000,
  });

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!graph.entry_node_id || !graph.nodes?.length) {
      setError("Граф должен содержать entry_node_id и хотя бы одну ноду");
      return;
    }

    const alwaysErr = validateAlwaysExclusiveTransitions(graph);
    if (alwaysErr) {
      setError(alwaysErr);
      return;
    }
    const reachErr = validateAllNodesReachableFromEntry(graph);
    if (reachErr) {
      setError(reachErr);
      return;
    }

    mutation.mutate({
      name,
      system_prompt: systemPrompt,
      temperature,
      max_tokens: maxTokens,
      graph,
    });
  };

  const bot = botQuery.data as Bot | undefined;

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
        <div className="grid gap-12">
          <form
            id={`bot-edit-meta-${botId}`}
            className="grid gap-12"
            onSubmit={handleSubmit}
          >
            <div className="grid grid-2 gap-12">
              <label>
                <div className="muted">Название</div>
                <input
                  className="input"
                  name="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  disabled={!isOwner}
                />
              </label>
              <label>
                <div className="muted">System prompt</div>
                <input
                  className="input"
                  name="system_prompt"
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
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
                  value={temperature}
                  onChange={(e) => setTemperature(e.target.value)}
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
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(Number(e.target.value))}
                  required
                  disabled={!isOwner}
                />
              </label>
            </div>
            <label>
              <div className="muted">Модель Gemini (LLM)</div>
              <GeminiModelSelect
                token={token}
                value={graph.gemini_model ?? DEFAULT_GEMINI_MODEL}
                onChange={(modelId) =>
                  setGraph({
                    ...graph,
                    gemini_model: modelId.trim() || DEFAULT_GEMINI_MODEL,
                  })
                }
                disabled={!isOwner}
              />
            </label>
          </form>
          <div>
            <div className="muted" style={{ marginBottom: 8 }}>
              Граф нод
            </div>
            <BotGraphEditor
              key={botId}
              graph={graph}
              onGraphChange={setGraph}
              documents={documentsQuery.data ?? []}
              apiTools={apiToolsQuery.data ?? []}
              readOnly={!isOwner}
              layoutStorageKey={`bot-graph-layout-${botId}`}
            />
          </div>
          {error && <div className="error">{error}</div>}
          {success && <div className="muted">{success}</div>}
          {isOwner && (
            <div className="flex" style={{ justifyContent: "flex-end" }}>
              <button
                className="btn"
                type="submit"
                form={`bot-edit-meta-${botId}`}
                disabled={mutation.isPending}
              >
                {mutation.isPending ? "Сохраняю..." : "Сохранить"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
