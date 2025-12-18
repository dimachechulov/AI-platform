import { FormEvent, useEffect, useState } from "react";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";
import { addUserToWorkspace, listWorkspaceUsers, removeUserFromWorkspace } from "../api";
import { WorkspaceUser } from "../types";

export function WorkspacesPage() {
  const { user, token } = useAuth();
  const { workspaces, activeWorkspaceId, setActiveWorkspaceId, create, loading } =
    useWorkspaceContext();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  
  // Управление пользователями
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<number | null>(null);
  const [workspaceUsers, setWorkspaceUsers] = useState<WorkspaceUser[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [userEmail, setUserEmail] = useState("");
  const [addingUser, setAddingUser] = useState(false);
  const [userError, setUserError] = useState<string | null>(null);

  const selectedWorkspace = workspaces.find(w => w.id === selectedWorkspaceId);
  const isOwner = selectedWorkspace?.user_role === 'owner';

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim()) return;
    try {
      await create(name.trim());
      setName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка создания");
    }
  };

  const handleManageUsers = async (workspaceId: number) => {
    setSelectedWorkspaceId(workspaceId);
    setUserError(null);
    setLoadingUsers(true);
    try {
      if (!token) throw new Error("No token");
      const users = await listWorkspaceUsers(token, workspaceId);
      setWorkspaceUsers(users);
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Ошибка загрузки пользователей");
    } finally {
      setLoadingUsers(false);
    }
  };

  const handleAddUser = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedWorkspaceId || !userEmail.trim() || !token) return;
    setUserError(null);
    setAddingUser(true);
    try {
      await addUserToWorkspace(token, selectedWorkspaceId, {
        user_email: userEmail.trim(),
        role: "member",
      });
      setUserEmail("");
      // Обновляем список
      const users = await listWorkspaceUsers(token, selectedWorkspaceId);
      setWorkspaceUsers(users);
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Ошибка добавления пользователя");
    } finally {
      setAddingUser(false);
    }
  };

  const handleRemoveUser = async (userId: number) => {
    if (!selectedWorkspaceId || !token) return;
    if (!confirm("Вы уверены, что хотите удалить этого пользователя из воркспейса?")) return;
    setUserError(null);
    try {
      await removeUserFromWorkspace(token, selectedWorkspaceId, userId);
      // Обновляем список
      const users = await listWorkspaceUsers(token, selectedWorkspaceId);
      setWorkspaceUsers(users);
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Ошибка удаления пользователя");
    }
  };

  return (
    <div className="grid gap-16">
      <div className="page-header">
        <h2 className="page-title">Workspaces</h2>
        <div className="muted">Пользователь: {user?.email}</div>
      </div>
      <div className="card">
        <form className="grid grid-2 gap-12" onSubmit={handleSubmit}>
          <label>
            <div className="muted">Название</div>
            <input
              className="input"
              placeholder="Например, Ритейл"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <div className="flex gap-12" style={{ justifyContent: "flex-end" }}>
            <button className="btn" type="submit" disabled={!name.trim()}>
              Создать workspace
            </button>
          </div>
        </form>
        {error && <div className="error mt-8">{error}</div>}
      </div>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Роль</th>
              <th>Создан</th>
              <th>Активный</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6}>Загрузка...</td>
              </tr>
            )}
            {!loading &&
              workspaces.map((w) => (
                <tr key={w.id}>
                  <td>{w.id}</td>
                  <td>{w.name}</td>
                  <td>{w.user_role === 'owner' ? 'Владелец' : 'Участник'}</td>
                  <td>{w.created_at || "—"}</td>
                  <td>
                    <input
                      type="radio"
                      checked={w.id === activeWorkspaceId}
                      onChange={() => setActiveWorkspaceId(w.id)}
                    />
                  </td>
                  <td>
                    {w.user_role === 'owner' && (
                      <button
                        className="btn"
                        onClick={() => handleManageUsers(w.id)}
                        style={{ fontSize: '0.875rem', padding: '0.25rem 0.75rem' }}
                      >
                        Управление пользователями
                      </button>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {selectedWorkspaceId && isOwner && (
        <div className="card">
          <h3 className="page-title" style={{ marginBottom: '1rem' }}>
            Пользователи воркспейса: {selectedWorkspace?.name}
          </h3>
          
          <form className="grid grid-2 gap-12" onSubmit={handleAddUser} style={{ marginBottom: '1.5rem' }}>
            <label>
              <div className="muted">Email пользователя</div>
              <input
                className="input"
                type="email"
                placeholder="user@example.com"
                value={userEmail}
                onChange={(e) => setUserEmail(e.target.value)}
              />
            </label>
            <div className="flex gap-12" style={{ justifyContent: "flex-end" }}>
              <button className="btn" type="submit" disabled={!userEmail.trim() || addingUser}>
                {addingUser ? "Добавление..." : "Добавить пользователя"}
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => setSelectedWorkspaceId(null)}
                style={{ background: '#666' }}
              >
                Закрыть
              </button>
            </div>
          </form>
          
          {userError && <div className="error" style={{ marginBottom: '1rem' }}>{userError}</div>}
          
          {loadingUsers ? (
            <div>Загрузка пользователей...</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Имя</th>
                  <th>Роль</th>
                  <th>Добавлен</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {workspaceUsers.length === 0 ? (
                  <tr>
                    <td colSpan={5}>Нет пользователей</td>
                  </tr>
                ) : (
                  workspaceUsers.map((u) => (
                    <tr key={u.id}>
                      <td>{u.email}</td>
                      <td>{u.full_name || "—"}</td>
                      <td>{u.role}</td>
                      <td>{new Date(u.added_at).toLocaleDateString()}</td>
                      <td>
                        <button
                          className="btn"
                          onClick={() => handleRemoveUser(u.id)}
                          style={{ fontSize: '0.875rem', padding: '0.25rem 0.75rem', background: '#dc3545' }}
                        >
                          Удалить
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

