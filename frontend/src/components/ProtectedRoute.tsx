import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../state/auth";

export function ProtectedRoute() {
  const { token, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="content">Загрузка...</div>;
  }

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}

