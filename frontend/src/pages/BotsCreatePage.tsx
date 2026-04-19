import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { createBot, listDocuments, listApiTools } from "../api";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";
import {
  BotGraphConfig,
  DEFAULT_GEMINI_MODEL,
  validateAllNodesReachableFromEntry,
  validateAlwaysExclusiveTransitions,
} from "../types";
import {
  BotGraphEditor,
  DEFAULT_BOT_GRAPH,
} from "../components/BotGraphEditor";
import { GeminiModelSelect } from "../components/GeminiModelSelect";

export function BotsCreatePage() {
  const { token } = useAuth();
  const { activeWorkspaceId, isOwner } = useWorkspaceContext();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    system_prompt: "",
    temperature: "0.7",
    max_tokens: 2048,
  });
  const [graph, setGraph] = useState<BotGraphConfig>(DEFAULT_BOT_GRAPH);
  const [error, setError] = useState<string | null>(null);

  const documentsQuery = useQuery({
    queryKey: ["documents", activeWorkspaceId],
    queryFn: () => listDocuments(token || "", activeWorkspaceId || 0),
    enabled: !!token && !!activeWorkspaceId,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const apiToolsQuery = useQuery({
    queryKey: ["apiTools", activeWorkspaceId],
    queryFn: () => listApiTools(token || "", activeWorkspaceId || 0),
    enabled: !!token && !!activeWorkspaceId,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!token || !activeWorkspaceId) throw new Error("Нет workspace");
      if (!graph.entry_node_id || !graph.nodes?.length) {
        throw new Error("Задайте граф: нужна стартовая нода и хотя бы одна нода");
      }
      const alwaysErr = validateAlwaysExclusiveTransitions(graph);
      if (alwaysErr) throw new Error(alwaysErr);
      const reachErr = validateAllNodesReachableFromEntry(graph);
      if (reachErr) throw new Error(reachErr);
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
      navigate("/app/bots");
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Ошибка");
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    createMutation.mutate();
  };

  if (!isOwner) {
    return (
      <div className="grid gap-16">
        <div className="page-header">
          <h2 className="page-title">Новый бот</h2>
          <div className="actions">
            <button className="btn ghost" type="button" onClick={() => navigate("/app/bots")}>
              Назад к списку
            </button>
          </div>
        </div>
        <div className="card" style={{ background: "#fff3cd", border: "1px solid #ffc107" }}>
          <div style={{ color: "#856404" }}>
            Создавать ботов может только владелец воркспейса.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-16">
      <div className="page-header">
        <h2 className="page-title">Новый бот</h2>
        <div className="actions">
          <button className="btn ghost" type="button" onClick={() => navigate("/app/bots")}>
            Назад к списку
          </button>
        </div>
      </div>

      <div className="card">
        <form
          id="bots-create-meta"
          className="grid gap-12"
          onSubmit={handleSubmit}
        >
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
            />
          </label>
        </form>
        <div className="grid gap-12" style={{ marginTop: 16 }}>
          <div className="muted">
            Граф нод (ПКМ по полю — создать ноду, ПКМ по ноде — настройки,
            перетаскивание и соединения — переходы)
          </div>
          <BotGraphEditor
            graph={graph}
            onGraphChange={setGraph}
            documents={documentsQuery.data ?? []}
            apiTools={apiToolsQuery.data ?? []}
            layoutStorageKey="bot-graph-layout-new"
          />
        </div>
        {error && <div className="error">{error}</div>}
        <div className="flex" style={{ justifyContent: "flex-end", marginTop: 12 }}>
          <button
            className="btn"
            type="submit"
            form="bots-create-meta"
            disabled={createMutation.isPending}
          >
            {createMutation.isPending ? "Создаю..." : "Создать бота"}
          </button>
        </div>
      </div>
    </div>
  );
}
