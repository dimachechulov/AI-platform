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

export type TransitionCondition = {
  type: TransitionConditionType;
  value?: string;
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

export type BotGraphConfig = {
  entry_node_id: string;
  nodes: GraphNode[];
};

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

