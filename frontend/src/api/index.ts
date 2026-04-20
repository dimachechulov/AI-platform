import {
  ApiTool,
  Bot,
  BotGraphConfig,
  ChatMessage,
  ChatSession,
  DocumentItem,
  GeminiChatModel,
  TokenUsageResponse,
  BillingSummary,
  BillingTransaction,
  SpendingResponse,
  WorkspacePlanLimits,
  UserProfile,
  Workspace,
  WorkspaceUser,
} from "../types";
import { apiRequest } from "./client";

export async function registerUser(payload: {
  email: string;
  password: string;
  full_name?: string;
}): Promise<{ id: number; email: string }> {
  return apiRequest("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function loginUser(payload: {
  username: string;
  password: string;
}): Promise<{ access_token: string; refresh_token: string; token_type: string }> {
  const params = new URLSearchParams();
  params.append("username", payload.username);
  params.append("password", payload.password);

  return apiRequest("/auth/login", {
    method: "POST",
    body: params,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
}

export async function refreshTokenApi(payload: {
  refresh_token: string;
}): Promise<{ access_token: string; refresh_token: string; token_type: string }> {
  return apiRequest("/auth/refresh", {
    method: "POST",
    body: JSON.stringify(payload),
    retryOnAuthError: false,
  });
}

export async function getProfile(token: string): Promise<UserProfile> {
  return apiRequest("/auth/me", { token });
}

export async function listWorkspaces(token: string): Promise<Workspace[]> {
  return apiRequest("/workspaces", { token });
}

export async function createWorkspace(
  token: string,
  payload: { name: string }
): Promise<Workspace> {
  return apiRequest("/workspaces", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function listDocuments(
  token: string,
  workspaceId: number
): Promise<DocumentItem[]> {
  return apiRequest(`/documents?workspace_id=${workspaceId}`, { token });
}

export async function uploadDocument(
  token: string,
  workspaceId: number,
  file: File
): Promise<DocumentItem> {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest(`/documents?workspace_id=${workspaceId}`, {
    method: "POST",
    token,
    body: formData,
  });
}

export async function deleteDocument(token: string, id: number): Promise<void> {
  return apiRequest(`/documents/${id}`, { method: "DELETE", token });
}

export async function listApiTools(
  token: string,
  workspaceId: number
): Promise<ApiTool[]> {
  return apiRequest(`/api-tools?workspace_id=${workspaceId}`, { token });
}

export async function createApiTool(
  token: string,
  payload: Omit<ApiTool, "id" | "created_at">
): Promise<ApiTool> {
  return apiRequest("/api-tools", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function updateApiTool(
  token: string,
  id: number,
  payload: Partial<ApiTool>
): Promise<ApiTool> {
  return apiRequest(`/api-tools/${id}`, {
    method: "PUT",
    token,
    body: JSON.stringify(payload),
  });
}

export async function deleteApiTool(token: string, id: number): Promise<void> {
  return apiRequest(`/api-tools/${id}`, {
    method: "DELETE",
    token,
  });
}

export async function getApiTool(token: string, id: number): Promise<ApiTool> {
  return apiRequest(`/api-tools/${id}`, { token });
}

export async function listGeminiChatModels(
  token: string
): Promise<GeminiChatModel[]> {
  return apiRequest("/gemini/chat-models", { token });
}

export async function listBots(
  token: string,
  workspaceId?: number
): Promise<Bot[]> {
  const suffix = workspaceId ? `?workspace_id=${workspaceId}` : "";
  return apiRequest(`/bots${suffix}`, { token });
}

export async function getBot(token: string, id: number): Promise<Bot> {
  return apiRequest(`/bots/${id}`, { token });
}

export async function createBot(
  token: string,
  payload: {
    name: string;
    workspace_id: number;
    system_prompt: string;
    graph: BotGraphConfig;
    temperature?: string;
    max_tokens?: number;
  }
): Promise<Bot> {
  return apiRequest("/bots", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function updateBot(
  token: string,
  id: number,
  payload: Partial<{
    name: string;
    system_prompt: string;
    graph: BotGraphConfig;
    temperature: string;
    max_tokens: number;
  }>
): Promise<Bot> {
  return apiRequest(`/bots/${id}`, {
    method: "PUT",
    token,
    body: JSON.stringify(payload),
  });
}

export async function deleteBot(token: string, id: number): Promise<void> {
  return apiRequest(`/bots/${id}`, { method: "DELETE", token });
}

export async function sendChatMessage(
  token: string,
  payload: { message: string; bot_id: number; session_id?: number }
): Promise<{ session_id: number; message: ChatMessage; metadata?: object }> {
  return apiRequest("/chat", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function listChatMessages(
  token: string,
  sessionId: number
): Promise<ChatMessage[]> {
  return apiRequest(`/chat/sessions/${sessionId}/messages`, { token });
}

export async function listChatSessions(
  token: string,
  botId?: number
): Promise<ChatSession[]> {
  const suffix = botId ? `?bot_id=${botId}` : "";
  return apiRequest(`/chat/sessions${suffix}`, { token });
}

export async function listWorkspaceUsers(
  token: string,
  workspaceId: number
): Promise<WorkspaceUser[]> {
  return apiRequest(`/workspaces/${workspaceId}/users`, { token });
}

export async function addUserToWorkspace(
  token: string,
  workspaceId: number,
  payload: { user_email: string; role?: string }
): Promise<WorkspaceUser> {
  return apiRequest(`/workspaces/${workspaceId}/users`, {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function removeUserFromWorkspace(
  token: string,
  workspaceId: number,
  userId: number
): Promise<void> {
  return apiRequest(`/workspaces/${workspaceId}/users/${userId}`, {
    method: "DELETE",
    token,
  });
}

export async function getTokenUsage(
  token: string,
  params: {
    workspaceId: number;
    timeFrom?: string;
    timeTo?: string;
    bucketMinutes?: number;
    botId?: number;
    model?: string;
  }
): Promise<TokenUsageResponse> {
  const sp = new URLSearchParams();
  sp.set("workspace_id", String(params.workspaceId));
  if (params.timeFrom) sp.set("time_from", params.timeFrom);
  if (params.timeTo) sp.set("time_to", params.timeTo);
  if (params.bucketMinutes != null) {
    sp.set("bucket_minutes", String(params.bucketMinutes));
  }
  if (params.botId != null) sp.set("bot_id", String(params.botId));
  if (params.model) sp.set("model", params.model);
  return apiRequest(`/usage/tokens?${sp.toString()}`, { token });
}

export async function listTokenUsageModels(
  token: string,
  params: {
    workspaceId: number;
    timeFrom?: string;
    timeTo?: string;
    botId?: number;
  }
): Promise<{ models: string[] }> {
  const sp = new URLSearchParams();
  sp.set("workspace_id", String(params.workspaceId));
  if (params.timeFrom) sp.set("time_from", params.timeFrom);
  if (params.timeTo) sp.set("time_to", params.timeTo);
  if (params.botId != null) sp.set("bot_id", String(params.botId));
  return apiRequest(`/usage/tokens/models?${sp.toString()}`, { token });
}

export async function getBillingSummary(
  token: string,
  workspaceId: number
): Promise<BillingSummary> {
  return apiRequest(`/billing/summary?workspace_id=${workspaceId}`, { token });
}

export async function listBillingTransactions(
  token: string,
  workspaceId: number
): Promise<BillingTransaction[]> {
  return apiRequest(`/billing/transactions?workspace_id=${workspaceId}`, { token });
}

export async function getSpendingUsage(
  token: string,
  params: { workspaceId: number; timeFrom?: string; timeTo?: string; bucketMinutes?: number }
): Promise<SpendingResponse> {
  const sp = new URLSearchParams();
  sp.set("workspace_id", String(params.workspaceId));
  if (params.timeFrom) sp.set("time_from", params.timeFrom);
  if (params.timeTo) sp.set("time_to", params.timeTo);
  if (params.bucketMinutes != null) sp.set("bucket_minutes", String(params.bucketMinutes));
  return apiRequest(`/billing/spending?${sp.toString()}`, { token });
}

export async function createSubscriptionCheckout(
  token: string,
  payload: { workspace_id: number; plan: "lite" | "full" }
): Promise<{ url: string }> {
  return apiRequest("/billing/checkout/subscription", {
    method: "POST",
    token,
    body: JSON.stringify({ workspace_id: payload.workspace_id, plan: payload.plan }),
  });
}

export async function createTopupCheckout(
  token: string,
  payload: { workspace_id: number; amount_usd: string }
): Promise<{ url: string }> {
  return apiRequest("/billing/checkout/topup", {
    method: "POST",
    token,
    body: JSON.stringify({ workspace_id: payload.workspace_id, amount_usd: payload.amount_usd }),
  });
}

export async function getWorkspacePlanLimits(
  token: string,
  workspaceId: number
): Promise<WorkspacePlanLimits> {
  return apiRequest(`/billing/limits?workspace_id=${workspaceId}`, { token });
}

export async function switchWorkspaceToTrial(
  token: string,
  workspaceId: number
): Promise<BillingSummary> {
  return apiRequest(`/billing/plan/trial?workspace_id=${workspaceId}`, {
    method: "POST",
    token,
  });
}

