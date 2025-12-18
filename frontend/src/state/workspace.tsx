import { ReactNode, createContext, useContext, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { createWorkspace, listWorkspaces } from "../api";
import { Workspace } from "../types";
import { useAuth } from "./auth";

type WorkspaceContextValue = {
  workspaces: Workspace[];
  activeWorkspaceId?: number;
  activeWorkspace?: Workspace;
  isOwner: boolean;
  setActiveWorkspaceId: (id?: number) => void;
  refresh: () => Promise<void>;
  create: (name: string) => Promise<void>;
  loading: boolean;
};

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(
  undefined
);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const savedId = Number(localStorage.getItem("ai_platform_workspace_id"));
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<number | undefined>(
    Number.isFinite(savedId) ? savedId : undefined
  );

  const workspaceQuery = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => listWorkspaces(token || ""),
    enabled: !!token,
  });

  useEffect(() => {
    if (workspaceQuery.data && workspaceQuery.data.length > 0) {
      const exists = workspaceQuery.data.some((w) => w.id === activeWorkspaceId);
      if (!activeWorkspaceId || !exists) {
        const firstId = workspaceQuery.data[0]?.id;
        setActiveWorkspaceId(firstId);
        localStorage.setItem("ai_platform_workspace_id", String(firstId));
      }
    }
  }, [workspaceQuery.data, activeWorkspaceId]);

  const refresh = async () => {
    await workspaceQuery.refetch();
  };

  const create = async (name: string) => {
    if (!token) return;
    await createWorkspace(token, { name });
    await refresh();
  };

  const setWorkspace = (id?: number) => {
    setActiveWorkspaceId(id);
    if (id) {
      localStorage.setItem("ai_platform_workspace_id", String(id));
    } else {
      localStorage.removeItem("ai_platform_workspace_id");
    }
  };

  const activeWorkspace = workspaceQuery.data?.find(
    (w) => w.id === activeWorkspaceId
  );
  
  const isOwner = activeWorkspace?.user_role === 'owner';

  return (
    <WorkspaceContext.Provider
      value={{
        workspaces: workspaceQuery.data || [],
        activeWorkspaceId,
        activeWorkspace,
        isOwner,
        setActiveWorkspaceId: setWorkspace,
        refresh,
        create,
        loading: workspaceQuery.isLoading,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspaceContext() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error("useWorkspaceContext must be used within WorkspaceProvider");
  }
  return ctx;
}

