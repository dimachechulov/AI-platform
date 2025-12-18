import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../state/auth";

export function AuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const { login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      setLoading(true);
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, fullName);
      }
      const redirectTo =
        (location.state as { from?: { pathname?: string } })?.from?.pathname ||
        "/app";
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background: "#0f172a",
        padding: "24px",
      }}
    >
      <div className="card" style={{ minWidth: 360, maxWidth: 420 }}>
        <div className="page-header" style={{ marginBottom: 12 }}>
          <h2 className="page-title">AI Platform</h2>
          <div className="actions">
            <button
              className={`btn ghost`}
              onClick={() => setMode(mode === "login" ? "register" : "login")}
              type="button"
            >
              {mode === "login" ? "Регистрация" : "У меня есть аккаунт"}
            </button>
          </div>
        </div>
        <form onSubmit={handleSubmit} className="grid gap-12">
          <div className="grid gap-8">
            <label>
              <div className="muted">Email</div>
              <input
                className="input"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            {mode === "register" && (
              <label>
                <div className="muted">Полное имя</div>
                <input
                  className="input"
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </label>
            )}
            <label>
              <div className="muted">Пароль</div>
              <input
                className="input"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn" type="submit" disabled={loading}>
            {loading
              ? "Подождите..."
              : mode === "login"
              ? "Войти"
              : "Создать аккаунт"}
          </button>
        </form>
      </div>
    </div>
  );
}

