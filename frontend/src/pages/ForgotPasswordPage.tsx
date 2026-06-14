import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { requestPasswordReset } from "../api";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    try {
      setLoading(true);
      const result = await requestPasswordReset({ email });
      setSuccess(result.message);
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
          <h2 className="page-title">Забыли пароль?</h2>
        </div>
        <p className="muted" style={{ marginBottom: 16 }}>
          Введите email — мы отправим ссылку для сброса пароля.
        </p>
        <form onSubmit={handleSubmit} className="grid gap-12">
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
          {error && <div className="error">{error}</div>}
          {success && <div style={{ color: "#4ade80" }}>{success}</div>}
          <button className="btn" type="submit" disabled={loading}>
            {loading ? "Отправка..." : "Отправить ссылку"}
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
