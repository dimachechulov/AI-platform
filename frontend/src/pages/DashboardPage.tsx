import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";

export function DashboardPage() {
  const { user } = useAuth();
  const { workspaces, activeWorkspaceId } = useWorkspaceContext();
  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId);

  return (
    <div className="grid gap-16">
      <div className="page-header">
        <h2 className="page-title">Добро пожаловать</h2>
        <div className="muted">{user?.email}</div>
      </div>
      <div className="grid grid-2">
        <div className="card">
          <div className="muted">Активное пространство</div>
          <div style={{ fontWeight: 600, fontSize: 18 }}>
            {activeWorkspace?.name || "Не выбрано"}
          </div>
          <div className="muted mt-8">
            Всего workspaces: {workspaces.length}
          </div>
        </div>
        <div className="card">
          <div className="muted">Подсказки</div>
          <ul style={{ paddingLeft: 16, margin: 0, color: "#475569" }}>
            <li>Создайте workspace и загрузите документы</li>
            <li>Опишите API tools для интеграции</li>
            <li>Соберите граф бота и откройте чат</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

