import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  deleteDocument,
  listDocuments,
  uploadDocument,
} from "../api";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";
import { DocumentItem } from "../types";

export function DocumentsPage() {
  const { token } = useAuth();
  const { activeWorkspaceId, isOwner } = useWorkspaceContext();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const docsQuery = useQuery({
    queryKey: ["documents", activeWorkspaceId],
    queryFn: () => listDocuments(token || "", activeWorkspaceId || 0),
    enabled: !!token && !!activeWorkspaceId,
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file || !token || !activeWorkspaceId) throw new Error("Нет файла");
      return uploadDocument(token, activeWorkspaceId, file);
    },
    onSuccess: () => {
      setFile(null);
      void docsQuery.refetch();
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Ошибка загрузки");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      if (!token) throw new Error("Нет токена");
      return deleteDocument(token, id);
    },
    onSuccess: () => void docsQuery.refetch(),
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    uploadMutation.mutate();
  };

  return (
    <div className="grid gap-16">
      <div className="page-header">
        <h2 className="page-title">Документы</h2>
        <div className="muted">
          Workspace: {activeWorkspaceId ?? "—"}
          {!isOwner && " · Режим просмотра"}
        </div>
      </div>
      {isOwner && (
        <div className="card">
        <form className="grid grid-2 gap-12" onSubmit={handleSubmit}>
          <div>
            <div className="muted">Файл (pdf, docx, txt)</div>
            <input
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="flex gap-12" style={{ justifyContent: "flex-end" }}>
            <button
              className="btn"
              type="submit"
              disabled={!file || uploadMutation.isLoading}
            >
              {uploadMutation.isLoading ? "Загружаем..." : "Загрузить"}
            </button>
          </div>
        </form>
        {error && <div className="error mt-8">{error}</div>}
      </div>
      )}

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Статус</th>
              <th>Размер</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {docsQuery.isLoading && (
              <tr>
                <td colSpan={5}>Загрузка...</td>
              </tr>
            )}
            {docsQuery.data?.map((doc: DocumentItem) => (
              <tr key={doc.id}>
                <td>{doc.id}</td>
                <td>{doc.filename}</td>
                <td>
                  <span className="badge">{doc.status}</span>
                </td>
                <td>{Math.round(doc.file_size / 1024)} КБ</td>
                <td>
                  {isOwner && (
                    <button
                      className="btn ghost"
                      onClick={() => deleteMutation.mutate(doc.id)}
                      type="button"
                    >
                      Удалить
                    </button>
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

