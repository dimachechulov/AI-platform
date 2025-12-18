import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AppLayout } from "./components/Layout";
import { AuthPage } from "./pages/AuthPage";
import { DashboardPage } from "./pages/DashboardPage";
import { WorkspacesPage } from "./pages/WorkspacesPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ApiToolsPage } from "./pages/ApiToolsPage";
import { BotsPage } from "./pages/BotsPage";
import { ChatPage } from "./pages/ChatPage";
import { BotEditPage } from "./pages/BotEditPage";
import { ApiToolEditPage } from "./pages/ApiToolEditPage";
import { WorkspaceProvider } from "./state/workspace";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage />} />
      <Route element={<ProtectedRoute />}>
        <Route
          path="/"
          element={<Navigate to="/app" replace />}
        />
        <Route
          path="/app"
          element={
            <WorkspaceProvider>
              <AppLayout />
            </WorkspaceProvider>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="workspaces" element={<WorkspacesPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="api-tools" element={<ApiToolsPage />} />
          <Route path="api-tools/:id" element={<ApiToolEditPage />} />
          <Route path="bots" element={<BotsPage />} />
          <Route path="bots/:id" element={<BotEditPage />} />
          <Route path="chat" element={<ChatPage />} />
        </Route>
      </Route>
    </Routes>
  );
}

