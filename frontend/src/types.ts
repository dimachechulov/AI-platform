export type Workspace = {
  id: number;
  name: string;
  owner_id?: number;
  created_at?: string;
  user_role?: string; // 'owner' | 'member'
};

export type WorkspaceUser = {
  id: number;
  email: string;
  full_name?: string | null;
  role: string;
  added_at: string;
};

export type UserProfile = {
  id: number;
  email: string;
  full_name?: string | null;
  workspaces: Workspace[];
};

export type DocumentItem = {
  id: number;
  filename: string;
  file_size: number;
  file_type: string;
  status: string;
  error_message?: string | null;
  created_at: string;
  processed_at?: string | null;
};

export type ApiTool = {
  id: number;
  workspace_id: number;
  name: string;
  description?: string | null;
  url: string;
  method: string;
  headers?: Record<string, string>;
  params?: Record<string, unknown>;
  body_schema?: Record<string, unknown>;
  created_at: string;
};

export type TransitionConditionType = "always" | "keyword" | "llm_routing";

/** Для keyword — строка; для always и llm_routing на фронте всегда null. */
export type TransitionCondition = {
  type: TransitionConditionType;
  value?: string | null;
};

export type NodeTransition = {
  target_node_id: string;
  condition: TransitionCondition;
};

export type ToolTrigger = {
  tool_name: string;
  keywords: string[];
  extract_params?: Record<string, string>;
};

export type GraphNode = {
  id: string;
  name: string;
  system_prompt?: string;
  use_rag?: boolean;
  rag_settings?: Record<string, unknown> | null;
  allowed_document_ids?: number[];
  api_tool_ids?: number[];
  tool_triggers?: ToolTrigger[];
  transitions?: NodeTransition[];
};

/** Дефолт совпадает с `GEMINI_MODEL` в `app.core.config` (если в конфиге бота модель не задана). */
export const DEFAULT_GEMINI_MODEL = "gemini-2.5-flash";

/** Элемент списка из GET /api/v1/gemini/chat-models */
export type GeminiChatModel = {
  name: string;
  display_name?: string | null;
  description?: string | null;
};

export type BotGraphConfig = {
  entry_node_id: string;
  nodes: GraphNode[];
  /** Модель Gemini для LLM; если с бэка не пришла — подставляется DEFAULT_GEMINI_MODEL. */
  gemini_model?: string | null;
};

/** Ошибка или null: у узла не может быть «always» вместе с другими исходящими переходами. */
export function validateAlwaysExclusiveTransitions(
  graph: BotGraphConfig
): string | null {
  for (const node of graph.nodes) {
    const tr = node.transitions ?? [];
    if (tr.length <= 1) continue;
    if (tr.some((t) => t.condition?.type === "always")) {
      return `Узел «${node.name || node.id}»: при условии «always» не может быть других исходящих переходов.`;
    }
  }
  return null;
}

/** Ошибка или null: каждая нода должна быть достижима от стартовой (entry) по переходам. */
export function validateAllNodesReachableFromEntry(
  graph: BotGraphConfig
): string | null {
  const idSet = new Set(graph.nodes.map((n) => n.id));
  if (!idSet.has(graph.entry_node_id)) {
    return "Стартовая нода (entry) должна совпадать с одной из нод графа.";
  }
  const reachable = new Set<string>();
  const stack: string[] = [graph.entry_node_id];
  while (stack.length > 0) {
    const id = stack.pop()!;
    if (!idSet.has(id) || reachable.has(id)) continue;
    reachable.add(id);
    const node = graph.nodes.find((n) => n.id === id);
    for (const t of node?.transitions ?? []) {
      const tgt = t.target_node_id;
      if (idSet.has(tgt) && !reachable.has(tgt)) {
        stack.push(tgt);
      }
    }
  }
  const orphans = graph.nodes.filter((n) => !reachable.has(n.id));
  if (orphans.length === 0) return null;
  const labels = orphans.map((n) => `«${n.name || n.id}»`).join(", ");
  return `Есть ноды, недостижимые со стартовой: ${labels}. Добавьте переходы от entry или удалите лишние ноды.`;
}

export type Bot = {
  id: number;
  name: string;
  workspace_id: number;
  system_prompt: string;
  config: BotGraphConfig;
  temperature: string;
  max_tokens: number;
  created_at: string;
};

export type ChatSession = {
  id: number;
  bot_id: number;
  created_at?: string | null;
};

export type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  metadata?: Record<string, unknown> | null;
  created_at: string;
};

