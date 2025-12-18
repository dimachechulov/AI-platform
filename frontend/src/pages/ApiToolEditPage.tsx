import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { getApiTool, updateApiTool } from "../api";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";
import { ApiTool } from "../types";
import { useNavigate, useParams } from "react-router-dom";

const METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"];

export function ApiToolEditPage() {
  const { id } = useParams<{ id: string }>();
  const toolId = Number(id);
  const { token } = useAuth();
  const { isOwner } = useWorkspaceContext();
  const navigate = useNavigate();

  const toolQuery = useQuery({
    queryKey: ["api-tool", toolId],
    queryFn: () => getApiTool(token || "", toolId),
    enabled: !!token && Number.isFinite(toolId),
  });

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

  useEffect(() => {
    const data = toolQuery.data;
    if (data) {
      setForm({
        name: data.name,
        description: data.description || "",
        url: data.url,
        method: data.method,
        headers: JSON.stringify(data.headers || {}, null, 2),
        params: JSON.stringify(data.params || {}, null, 2),
        body_schema: JSON.stringify(data.body_schema || {}, null, 2),
      });
    }
  }, [toolQuery.data]);

  const parseJsonField = (value: string) => {
    if (!value.trim()) return undefined;
    try {
      return JSON.parse(value);
    } catch (err) {
      throw new Error("Неверный JSON в одном из полей (headers/params/body)");
    }
  };

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!token) throw new Error("Нет токена");
      const payload: Partial<ApiTool> = {
        name: form.name,
        description: form.description,
        url: form.url,
        method: form.method,
        headers: parseJsonField(form.headers),
        params: parseJsonField(form.params),
        body_schema: parseJsonField(form.body_schema),
      };
      return updateApiTool(token, toolId, payload);
    },
    onSuccess: () => {
      navigate("/app/api-tools");
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Ошибка сохранения");
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    updateMutation.mutate();
  };

  if (toolQuery.isLoading) {
    return <div className="content">Загрузка...</div>;
  }

  if (!toolQuery.data) {
    return <div className="content">Инструмент не найден</div>;
  }

  return (
    <div className="grid gap-16">
      <div className="page-header">
        <h2 className="page-title">
          {isOwner ? "Редактирование" : "Просмотр"} API Tool #{toolId}
        </h2>
        <div className="muted">Workspace: {toolQuery.data.workspace_id}</div>
      </div>

      {!isOwner && (
        <div className="card" style={{ background: '#fff3cd', border: '1px solid #ffc107' }}>
          <div style={{ color: '#856404' }}>
            ⚠️ Режим только для просмотра. Только владелец воркспейса может редактировать API Tools.
          </div>
        </div>
      )}

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
                disabled={!isOwner}
              />
            </label>
            <label>
              <div className="muted">HTTP метод</div>
              <select
                className="select"
                value={form.method}
                onChange={(e) => setForm({ ...form, method: e.target.value })}
                disabled={!isOwner}
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
                disabled={!isOwner}
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
                disabled={!isOwner}
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
                spellCheck={false}
                disabled={!isOwner}
              />
            </label>
            <label>
              <div className="muted">Params (JSON)</div>
              <textarea
                className="textarea"
                value={form.params}
                onChange={(e) => setForm({ ...form, params: e.target.value })}
                spellCheck={false}
                disabled={!isOwner}
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
              spellCheck={false}
              disabled={!isOwner}
            />
          </label>

          {error && <div className="error">{error}</div>}

          <div className="flex gap-12" style={{ justifyContent: "flex-end" }}>
            <button className="btn ghost" type="button" onClick={() => navigate("/app/api-tools")}>
              {isOwner ? "Отмена" : "Назад"}
            </button>
            {isOwner && (
              <button className="btn" type="submit" disabled={updateMutation.isPending}>
                {updateMutation.isPending ? "Сохраняем..." : "Сохранить"}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}