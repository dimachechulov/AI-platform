import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { resetPassword } from "../api";

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const navigate = useNavigate();

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!token) {
      setError("Ссылка для сброса пароля недействительна");
      return;
    }
    if (password !== confirmPassword) {
      setError("Пароли не совпадают");
      return;
    }

    try {
      setLoading(true);
      const result = await resetPassword({ token, new_password: password });
      setSuccess(result.message);
      setTimeout(() => navigate("/login", { replace: true }), 2000);
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
          <h2 className="page-title">Новый пароль</h2>
        </div>
        <p className="muted" style={{ marginBottom: 16 }}>
          Введите новый пароль для вашего аккаунта.
        </p>
        <form onSubmit={handleSubmit} className="grid gap-12">
          <label>
            <div className="muted">Новый пароль</div>
            <input
              className="input"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <label>
            <div className="muted">Повторите пароль</div>
            <input
              className="input"
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </label>
          {error && <div className="error">{error}</div>}
          {success && <div style={{ color: "#4ade80" }}>{success}</div>}
          <button className="btn" type="submit" disabled={loading || !token}>
            {loading ? "Сохранение..." : "Сохранить пароль"}
          </button>
        </form>
        <div style={{ marginTop: 16, textAlign: "center" }}>
          <Link to="/login" className="muted">
            Вернуться ко входу
          </Link>
        </div>
      </div>
    </div>
  );
}
