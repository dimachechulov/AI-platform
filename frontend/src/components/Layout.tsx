import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";

const BASE_NAV_ITEMS = [
  { to: "/app", label: "Обзор" },
  { to: "/app/workspaces", label: "Рабочие пространства" },
  { to: "/app/documents", label: "Документы" },
  { to: "/app/api-tools", label: "API-инструменты" },
  { to: "/app/bots", label: "Боты" },
  { to: "/app/chat", label: "Чат" },
];

function WorkspaceSelector() {
  const { workspaces, activeWorkspaceId, setActiveWorkspaceId, create } =
    useWorkspaceContext();

  const handleCreate = async () => {
    const name = prompt("Название рабочего пространства");
    if (name) {
      await create(name.trim());
    }
  };

  return (
    <div>
      <div className="muted">Пространство</div>
      <div className="flex gap-8 mt-8">
        <select
          className="select"
          value={activeWorkspaceId ?? ""}
          onChange={(e) => setActiveWorkspaceId(Number(e.target.value))}
        >
          {workspaces.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <button className="btn ghost" onClick={handleCreate} type="button">
          +
        </button>
      </div>
    </div>
  );
}

export function AppLayout() {
  const { user, logout } = useAuth();
  const { isOwner } = useWorkspaceContext();
  const navigate = useNavigate();
  const navItems = isOwner
    ? [...BASE_NAV_ITEMS, { to: "/app/billing", label: "Биллинг" }]
    : BASE_NAV_ITEMS;

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <h1>AI Platform</h1>
          <div className="muted">
            {user?.full_name || user?.email || "Профиль"}
          </div>
        </div>
        <nav>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/app"}
              className={({ isActive }) =>
                isActive ? "nav-link active" : "nav-link"
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <WorkspaceSelector />
        <button className="btn ghost" onClick={handleLogout} type="button">
          Выйти
        </button>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

