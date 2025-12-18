import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { createApiTool, deleteApiTool, listApiTools } from "../api";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";
import { ApiTool } from "../types";
import { useNavigate } from "react-router-dom";

const METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"];

export function ApiToolsPage() {
  const { token } = useAuth();
  const { activeWorkspaceId, isOwner } = useWorkspaceContext();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    description: "",
    url: "",
    method: "GET",
    headers: "{}",
    params: "{}",
    body_schema: "{}",
  });
  const [error, setError] = useState<string | null>(null);

  const toolsQuery = useQuery({
    queryKey: ["api-tools", activeWorkspaceId],
    queryFn: () => listApiTools(token || "", activeWorkspaceId || 0),
    enabled: !!token && !!activeWorkspaceId,
  });

  const parseJsonField = (value: string) => {
    if (!value.trim()) return undefined;
    try {
      return JSON.parse(value);
    } catch (err) {
      throw new Error("Неверный JSON в одном из полей (headers/params/body)");
    }
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!token || !activeWorkspaceId) throw new Error("Нет токена");
      const payload = {
        workspace_id: activeWorkspaceId,
        name: form.name,
        description: form.description,
        url: form.url,
        method: form.method,
        headers: parseJsonField(form.headers),
        params: parseJsonField(form.params),
        body_schema: parseJsonField(form.body_schema),
      };
      return createApiTool(token, payload as any);
    },
    onSuccess: () => {
      setForm({
        name: "",
        description: "",
        url: "",
        method: "GET",
        headers: "{}",
        params: "{}",
        body_schema: "{}",
      });
      void toolsQuery.refetch();
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Ошибка");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      if (!token) throw new Error("Нет токена");
      return deleteApiTool(token, id);
    },
    onSuccess: () => void toolsQuery.refetch(),
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    createMutation.mutate();
  };

  const handleUpdate = (tool: ApiTool) => {
    navigate(`/app/api-tools/${tool.id}`);
  };

  return (
    <div className="grid gap-16">
      <div className="page-header">
        <h2 className="page-title">API Tools</h2>
        <div className="muted">
          Workspace: {activeWorkspaceId ?? "—"}
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
              <div className="muted">HTTP метод</div>
              <select
                className="select"
                value={form.method}
                onChange={(e) => setForm({ ...form, method: e.target.value })}
              >
                {METHODS.map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </select>
            </label>
            <label>
              <div className="muted">URL</div>
              <input
                className="input"
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                required
              />
            </label>
            <label>
              <div className="muted">Описание</div>
              <input
                className="input"
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
              />
            </label>
          </div>
          <div className="grid grid-2 gap-12">
            <label>
              <div className="muted">Headers (JSON)</div>
              <textarea
                className="textarea"
                value={form.headers}
                onChange={(e) => setForm({ ...form, headers: e.target.value })}
              />
            </label>
            <label>
              <div className="muted">Params (JSON)</div>
              <textarea
                className="textarea"
                value={form.params}
                onChange={(e) => setForm({ ...form, params: e.target.value })}
              />
            </label>
          </div>
          <label>
            <div className="muted">Body schema (JSON)</div>
            <textarea
              className="textarea"
              value={form.body_schema}
              onChange={(e) =>
                setForm({ ...form, body_schema: e.target.value })
              }
            />
          </label>
          {error && <div className="error">{error}</div>}
          <div className="flex" style={{ justifyContent: "flex-end" }}>
            <button className="btn" type="submit">
              Создать
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
              <th>URL</th>
              <th>Метод</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {toolsQuery.isLoading && (
              <tr>
                <td colSpan={5}>Загрузка...</td>
              </tr>
            )}
            {toolsQuery.data?.map((tool) => (
              <tr key={tool.id}>
                <td>{tool.id}</td>
                <td>{tool.name}</td>
                <td style={{ maxWidth: 260, overflowWrap: "anywhere" }}>
                  {tool.url}
                </td>
                <td>{tool.method}</td>
                <td className="flex gap-8">
                  {isOwner && (
                    <>
                      <button
                        className="btn ghost"
                        type="button"
                        onClick={() => handleUpdate(tool)}
                      >
                        Редактировать
                      </button>
                      <button
                        className="btn ghost"
                        type="button"
                        onClick={() => deleteMutation.mutate(tool.id)}
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

