import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  memo,
  type CSSProperties,
} from "react";
import { createPortal } from "react-dom";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  MarkerType,
  type Node,
  type Edge,
  type Connection,
  type NodeTypes,
  type NodeProps,
  ReactFlowProvider,
  useReactFlow,
  BackgroundVariant,
  applyNodeChanges,
  applyEdgeChanges,
  type NodeChange,
  type EdgeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import {
  DEFAULT_GEMINI_MODEL,
  type ApiTool,
  type BotGraphConfig,
  type DocumentItem,
  type GraphNode,
  type NodeTransition,
  type TransitionCondition,
} from "../types";

/** Приводит ответ API к BotGraphConfig (строковые nodes и т.д.) */
export function normalizeBotGraph(raw: unknown): BotGraphConfig {
  const c =
    raw && typeof raw === "object"
      ? (raw as Record<string, unknown>)
      : {};
  let nodesUnknown: unknown = c["nodes"];
  if (typeof nodesUnknown === "string") {
    try {
      nodesUnknown = JSON.parse(nodesUnknown);
    } catch {
      nodesUnknown = [];
    }
  }
  if (!Array.isArray(nodesUnknown)) nodesUnknown = [];
  const nodes = nodesUnknown as GraphNode[];
  const entryRaw = c["entry_node_id"];
  const entry =
    typeof entryRaw === "string" && entryRaw
      ? entryRaw
      : nodes[0]?.id ?? "main";
  const gemRaw = c["gemini_model"];
  let gemini_model: string;
  if (typeof gemRaw === "string" && gemRaw.trim()) {
    gemini_model = gemRaw.trim();
  } else if (gemRaw != null && String(gemRaw).trim()) {
    gemini_model = String(gemRaw).trim();
  } else {
    gemini_model = DEFAULT_GEMINI_MODEL;
  }
  return {
    entry_node_id: entry,
    gemini_model,
    nodes: nodes.map((n) => ({
      ...n,
      transitions: Array.isArray(n.transitions) ? n.transitions : [],
      allowed_document_ids: Array.isArray(n.allowed_document_ids)
        ? n.allowed_document_ids
        : [],
      api_tool_ids: Array.isArray(n.api_tool_ids) ? n.api_tool_ids : [],
    })),
  };
}

type BotFlowData = {
  label: string;
  isEntry: boolean;
};

const BotFlowNode = memo(function BotFlowNode({ data }: NodeProps) {
  const d = data as BotFlowData;
  const style: CSSProperties = {
    padding: "10px 14px",
    borderRadius: 10,
    minWidth: 140,
    maxWidth: 220,
    fontSize: 13,
    fontWeight: 500,
    border: d.isEntry ? "2px solid #16a34a" : "1px solid #cbd5e1",
    background: d.isEntry ? "#dcfce7" : "#ffffff",
    color: "#0f172a",
    boxShadow: "0 1px 2px rgba(15,23,42,0.06)",
  };

  return (
    <div style={style}>
      <Handle
        type="target"
        position={Position.Top}
        style={{ width: 8, height: 8, background: "#64748b" }}
      />
      <div style={{ wordBreak: "break-word" }}>{d.label}</div>
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ width: 8, height: 8, background: "#64748b" }}
      />
    </div>
  );
});

const nodeTypes: NodeTypes = { botNode: BotFlowNode };

function defaultPosition(index: number): { x: number; y: number } {
  const col = index % 4;
  const row = Math.floor(index / 4);
  return { x: 80 + col * 240, y: 80 + row * 160 };
}

const edgeMarkerEnd = {
  type: MarkerType.ArrowClosed,
  width: 18,
  height: 18,
  color: "#64748b",
} as const;

function edgesFromGraph(graph: BotGraphConfig): Edge[] {
  const edges: Edge[] = [];
  for (const n of graph.nodes) {
    (n.transitions || []).forEach((t, i) => {
      edges.push({
        id: `e:${n.id}:${t.target_node_id}:${i}`,
        source: n.id,
        target: t.target_node_id,
        markerEnd: edgeMarkerEnd,
        label:
          t.condition.type === "always"
            ? undefined
            : t.condition.type === "keyword" && t.condition.value
              ? `keyword: ${t.condition.value}`
              : t.condition.type,
        data: { sourceId: n.id, transitionIndex: i },
      });
    });
  }
  return edges;
}

function loadStoredPositions(key: string): Record<string, { x: number; y: number }> {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, { x: number; y: number }>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveStoredPositions(
  key: string,
  pos: Record<string, { x: number; y: number }>
) {
  try {
    localStorage.setItem(key, JSON.stringify(pos));
  } catch {
    /* ignore */
  }
}

type PaneMenuState = { x: number; y: number; flowX: number; flowY: number };

type BotGraphEditorProps = {
  graph: BotGraphConfig;
  onGraphChange: (g: BotGraphConfig) => void;
  documents: DocumentItem[];
  apiTools: ApiTool[];
  readOnly?: boolean;
  /** Сохраняет координаты нод в localStorage */
  layoutStorageKey?: string;
};

function cloneGraph(g: BotGraphConfig): BotGraphConfig {
  return JSON.parse(JSON.stringify(g)) as BotGraphConfig;
}

/** Обход исходящих переходов: достижим ли `to` из `from`. */
function canReachNode(graph: BotGraphConfig, from: string, to: string): boolean {
  if (from === to) return true;
  const idSet = new Set(graph.nodes.map((n) => n.id));
  if (!idSet.has(from) || !idSet.has(to)) return false;
  const visited = new Set<string>();
  const stack: string[] = [from];
  while (stack.length) {
    const v = stack.pop()!;
    if (v === to) return true;
    if (visited.has(v)) continue;
    visited.add(v);
    const node = graph.nodes.find((n) => n.id === v);
    for (const t of node?.transitions || []) {
      if (!visited.has(t.target_node_id)) stack.push(t.target_node_id);
    }
  }
  return false;
}

/**
 * Переход source → target замыкает цикл, если уже есть путь target → … → source
 * (направленный граф переходов).
 */
function connectionCreatesCycle(
  graph: BotGraphConfig,
  source: string,
  target: string
): boolean {
  return canReachNode(graph, target, source);
}

function isDuplicateTransition(
  graph: BotGraphConfig,
  source: string,
  target: string
): boolean {
  const node = graph.nodes.find((n) => n.id === source);
  return !!node?.transitions?.some((t) => t.target_node_id === target);
}

function BotGraphCanvas({
  graph,
  onGraphChange,
  documents,
  apiTools,
  readOnly,
  layoutStorageKey,
}: BotGraphEditorProps) {
  const { screenToFlowPosition } = useReactFlow();
  const graphRef = useRef<string>("");
  const positionsRef = useRef<Record<string, { x: number; y: number }>>(
    layoutStorageKey ? loadStoredPositions(layoutStorageKey) : {}
  );
  const pendingLayoutRef = useRef<Record<string, { x: number; y: number }>>({});
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>(
    () => ({ ...positionsRef.current })
  );
  positionsRef.current = positions;

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  const [paneMenu, setPaneMenu] = useState<PaneMenuState | null>(null);
  const [nodeModal, setNodeModal] = useState<
    | { mode: "create"; flowPosition: { x: number; y: number } }
    | { mode: "edit"; nodeId: string }
    | null
  >(null);
  const [edgeModal, setEdgeModal] = useState<{
    sourceId: string;
    transitionIndex: number;
  } | null>(null);

  useEffect(() => {
    const serialized = JSON.stringify(graph);
    if (serialized === graphRef.current) return;
    graphRef.current = serialized;
    setEdges(edgesFromGraph(graph));
    setNodes((curr) =>
      graph.nodes.map((n, idx) => {
        const old = curr.find((c) => c.id === n.id);
        const stored = positionsRef.current[n.id];
        const pending = pendingLayoutRef.current[n.id];
        const pos =
          old?.position ?? pending ?? stored ?? defaultPosition(idx);
        if (pending) delete pendingLayoutRef.current[n.id];
        return {
          id: n.id,
          type: "botNode",
          position: pos ?? defaultPosition(idx),
          data: {
            label: n.name || n.id,
            isEntry: n.id === graph.entry_node_id,
          },
        };
      })
    );
  }, [graph]);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      if (readOnly) return;
      setNodes((nds) => applyNodeChanges(changes, nds));
    },
    [readOnly]
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      if (readOnly) return;
      const removed = changes.filter((c) => c.type === "remove");
      if (removed.length) {
        const g = cloneGraph(graph);
        const bySource = new Map<string, number[]>();
        for (const ch of removed) {
          if (!("id" in ch) || !ch.id) continue;
          const edge = edges.find((e) => e.id === ch.id);
          if (!edge?.data || typeof edge.data !== "object") continue;
          const d = edge.data as { sourceId?: string; transitionIndex?: number };
          if (d.sourceId == null || d.transitionIndex == null) continue;
          const arr = bySource.get(d.sourceId) ?? [];
          arr.push(d.transitionIndex);
          bySource.set(d.sourceId, arr);
        }
        for (const [sourceId, indices] of bySource) {
          const node = g.nodes.find((n) => n.id === sourceId);
          if (!node?.transitions?.length) continue;
          const sorted = [...new Set(indices)].sort((a, b) => b - a);
          for (const i of sorted) {
            if (i >= 0 && i < node.transitions.length) {
              node.transitions.splice(i, 1);
            }
          }
        }
        graphRef.current = JSON.stringify(g);
        onGraphChange(g);
        setEdges(edgesFromGraph(g));
        return;
      }
      setEdges((eds) => applyEdgeChanges(changes, eds));
    },
    [graph, onGraphChange, readOnly, edges]
  );

  const isValidConnection = useCallback(
    (c: Connection | Edge) => {
      if (readOnly) return false;
      const src = c.source ?? undefined;
      const tgt = c.target ?? undefined;
      if (!src || !tgt) return false;
      if (src === tgt) return false;
      const srcNode = graph.nodes.find((n) => n.id === src);
      const out = srcNode?.transitions ?? [];
      if (out.some((t) => t.condition.type === "always")) {
        return false;
      }
      if (isDuplicateTransition(graph, src, tgt)) return false;
      if (connectionCreatesCycle(graph, src, tgt)) return false;
      return true;
    },
    [graph, readOnly]
  );

  const onConnect = useCallback(
    (conn: Connection) => {
      if (readOnly || !conn.source || !conn.target) return;
      if (!isValidConnection(conn)) return;
      const g = cloneGraph(graph);
      const node = g.nodes.find((n) => n.id === conn.source);
      if (!node) return;
      const transitions = [...(node.transitions || [])];
      const condition: TransitionCondition =
        transitions.length === 0
          ? { type: "always", value: null }
          : { type: "llm_routing", value: null };
      transitions.push({
        target_node_id: conn.target,
        condition,
      });
      node.transitions = transitions;
      graphRef.current = JSON.stringify(g);
      onGraphChange(g);
      setEdges(edgesFromGraph(g));
    },
    [graph, onGraphChange, readOnly, isValidConnection]
  );

  const onNodeDragStop = useCallback(
    (_: unknown, node: Node) => {
      if (readOnly) return;
      setPositions((prev) => {
        const next = { ...prev, [node.id]: { ...node.position } };
        if (layoutStorageKey) saveStoredPositions(layoutStorageKey, next);
        return next;
      });
    },
    [layoutStorageKey, readOnly]
  );

  const onPaneContextMenu = useCallback(
    (e: MouseEvent | React.MouseEvent<Element>) => {
      if (readOnly) return;
      e.preventDefault();
      const flow = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      setPaneMenu({
        x: e.clientX,
        y: e.clientY,
        flowX: flow.x,
        flowY: flow.y,
      });
    },
    [readOnly, screenToFlowPosition]
  );

  const onNodeContextMenu = useCallback(
    (e: React.MouseEvent, node: Node) => {
      if (readOnly) return;
      e.preventDefault();
      setPaneMenu(null);
      setNodeModal({ mode: "edit", nodeId: node.id });
    },
    [readOnly]
  );

  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      if (readOnly) return;
      const d = edge.data as { sourceId?: string; transitionIndex?: number } | undefined;
      if (d?.sourceId != null && d.transitionIndex != null) {
        setEdgeModal({ sourceId: d.sourceId, transitionIndex: d.transitionIndex });
      }
    },
    [readOnly]
  );

  useEffect(() => {
    if (!paneMenu) return;
    const close = () => setPaneMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [paneMenu]);

  const flowStyle: CSSProperties = {
    width: "100%",
    height: 520,
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    background: "#f8fafc",
  };

  return (
    <div className="bot-graph-editor">
      <div style={flowStyle} onContextMenu={(e) => e.stopPropagation()}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          isValidConnection={isValidConnection}
          onNodeDragStop={onNodeDragStop}
          nodeTypes={nodeTypes}
          onPaneContextMenu={onPaneContextMenu}
          onNodeContextMenu={onNodeContextMenu}
          onEdgeClick={onEdgeClick}
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          elementsSelectable={!readOnly}
          deleteKeyCode={readOnly ? null : "Backspace"}
          fitView
          defaultEdgeOptions={{
            type: "smoothstep",
            markerEnd: edgeMarkerEnd,
          }}
          connectionLineStyle={{ stroke: "#64748b", strokeWidth: 2 }}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#cbd5e1" />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable />
        </ReactFlow>
      </div>

      {paneMenu && !readOnly && (
        <div
          style={{
            position: "fixed",
            left: paneMenu.x,
            top: paneMenu.y,
            zIndex: 50,
          }}
        >
          <button
            type="button"
            className="btn"
            style={{ boxShadow: "0 4px 12px rgba(15,23,42,0.12)" }}
            onClick={(e) => {
              e.stopPropagation();
              setPaneMenu(null);
              setNodeModal({
                mode: "create",
                flowPosition: { x: paneMenu.flowX, y: paneMenu.flowY },
              });
            }}
          >
            Создать ноду
          </button>
        </div>
      )}

      {nodeModal && (
        <NodeFormModal
          graph={graph}
          onGraphChange={onGraphChange}
          mode={nodeModal.mode}
          createAt={
            nodeModal.mode === "create" ? nodeModal.flowPosition : undefined
          }
          editNodeId={nodeModal.mode === "edit" ? nodeModal.nodeId : undefined}
          documents={documents}
          apiTools={apiTools}
          onClose={() => setNodeModal(null)}
          onApplyLayout={(nodeId, pos) => {
            pendingLayoutRef.current[nodeId] = pos;
            setPositions((prev) => {
              const next = { ...prev, [nodeId]: pos };
              if (layoutStorageKey) saveStoredPositions(layoutStorageKey, next);
              return next;
            });
          }}
        />
      )}

      {edgeModal && (
        <EdgeConditionModal
          key={`${edgeModal.sourceId}-${edgeModal.transitionIndex}`}
          graph={graph}
          onGraphChange={onGraphChange}
          sourceId={edgeModal.sourceId}
          transitionIndex={edgeModal.transitionIndex}
          onClose={() => setEdgeModal(null)}
        />
      )}
    </div>
  );
}

type NodeFormModalProps = {
  graph: BotGraphConfig;
  onGraphChange: (g: BotGraphConfig) => void;
  mode: "create" | "edit";
  createAt?: { x: number; y: number };
  editNodeId?: string;
  documents: DocumentItem[];
  apiTools: ApiTool[];
  onClose: () => void;
  onApplyLayout: (nodeId: string, pos: { x: number; y: number }) => void;
};

function NodeFormModal({
  graph,
  onGraphChange,
  mode,
  createAt,
  editNodeId,
  documents,
  apiTools,
  onClose,
  onApplyLayout,
}: NodeFormModalProps) {
  const existing =
    mode === "edit" && editNodeId
      ? graph.nodes.find((n) => n.id === editNodeId)
      : undefined;

  const [id, setId] = useState(
    () => existing?.id ?? `node-${Date.now().toString(36)}`
  );
  const [name, setName] = useState(() => existing?.name ?? "");
  const [systemPrompt, setSystemPrompt] = useState(
    () => existing?.system_prompt ?? ""
  );
  const [docIds, setDocIds] = useState<Set<number>>(
    () => new Set(existing?.allowed_document_ids ?? [])
  );
  const [toolIds, setToolIds] = useState<Set<number>>(
    () => new Set(existing?.api_tool_ids ?? [])
  );
  const [isEntry, setIsEntry] = useState(
    () => !!existing && graph.entry_node_id === existing.id
  );

  const toggleDoc = (docId: number) => {
    setDocIds((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  };

  const toggleTool = (toolId: number) => {
    setToolIds((prev) => {
      const next = new Set(prev);
      if (next.has(toolId)) next.delete(toolId);
      else next.add(toolId);
      return next;
    });
  };

  /** Без <form>: модалка вложена в форму страницы — вложенные form в HTML недопустимы и ломают сабмит. */
  const applyNode = () => {
    const trimmedId = id.trim();
    const trimmedName = name.trim();
    if (!trimmedId || !trimmedName) return;

    if (mode === "create") {
      if (graph.nodes.some((n) => n.id === trimmedId)) {
        alert("Нода с таким id уже есть");
        return;
      }
    }

    const allowedIds = Array.from(docIds);
    const node: GraphNode = {
      id: trimmedId,
      name: trimmedName,
      system_prompt: systemPrompt || undefined,
      use_rag: allowedIds.length > 0,
      allowed_document_ids: allowedIds,
      api_tool_ids: Array.from(toolIds),
      transitions: existing?.transitions ?? [],
      tool_triggers: existing?.tool_triggers,
      rag_settings: existing?.rag_settings,
    };

    let g = cloneGraph(graph);

    if (mode === "create") {
      g.nodes = [...g.nodes, node];
      if (!g.entry_node_id || g.nodes.length === 1) {
        g.entry_node_id = trimmedId;
      }
      if (createAt) {
        onApplyLayout(trimmedId, createAt);
      }
    } else if (editNodeId && editNodeId !== trimmedId) {
      alert("Нельзя менять id ноды после создания");
      return;
    } else {
      g.nodes = g.nodes.map((n) => (n.id === trimmedId ? node : n));
    }

    if (isEntry) {
      g.entry_node_id = trimmedId;
    } else if (g.entry_node_id === trimmedId) {
      const other = g.nodes.find((n) => n.id !== trimmedId);
      if (other) g.entry_node_id = other.id;
    }

    onGraphChange(g);
    onClose();
  };

  const removeNode = () => {
    if (mode !== "edit" || !editNodeId) return;
    if (!confirm("Удалить ноду и связанные переходы?")) return;
    let g = cloneGraph(graph);
    g.nodes = g.nodes.filter((n) => n.id !== editNodeId);
    for (const n of g.nodes) {
      n.transitions = (n.transitions || []).filter(
        (t) => t.target_node_id !== editNodeId
      );
    }
    if (g.entry_node_id === editNodeId) {
      g.entry_node_id = g.nodes[0]?.id ?? "";
    }
    if (!g.nodes.length) {
      alert("Должна остаться хотя бы одна нода");
      return;
    }
    onGraphChange(g);
    onClose();
  };

  return createPortal(
    <div
      className="modal-overlay"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,23,42,0.35)",
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        className="card"
        style={{ maxWidth: 560, width: "100%", maxHeight: "90vh", overflow: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ margin: "0 0 12px", fontSize: 18 }}>
          {mode === "create" ? "Новая нода" : "Настройка ноды"}
        </h3>
        <div className="grid gap-12">
          <label>
            <div className="muted">Id ноды</div>
            <input
              className="input"
              value={id}
              onChange={(e) => setId(e.target.value)}
              required
              disabled={mode === "edit"}
            />
          </label>
          <label>
            <div className="muted">Название</div>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </label>
          <label>
            <div className="muted">System prompt</div>
            <textarea
              className="textarea"
              rows={4}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
            />
          </label>
          <label className="flex gap-8" style={{ alignItems: "center" }}>
            <input
              type="checkbox"
              checked={isEntry}
              onChange={(e) => setIsEntry(e.target.checked)}
            />
            <span>Стартовая нода (только одна)</span>
          </label>

          <div>
            <div className="muted" style={{ marginBottom: 8 }}>
              Документы воркспейса
            </div>
            <div
              className="doc-tool-grid"
              style={{
                maxHeight: 160,
                overflow: "auto",
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                padding: 8,
              }}
            >
              {documents.length === 0 && (
                <span className="muted">Нет документов</span>
              )}
              {documents.map((d) => (
                <label
                  key={d.id}
                  className="flex gap-8"
                  style={{ alignItems: "flex-start", marginBottom: 6 }}
                >
                  <input
                    type="checkbox"
                    checked={docIds.has(d.id)}
                    onChange={() => toggleDoc(d.id)}
                  />
                  <span>
                    #{d.id} {d.filename}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <div className="muted" style={{ marginBottom: 8 }}>
              API tools воркспейса
            </div>
            <div
              style={{
                maxHeight: 160,
                overflow: "auto",
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                padding: 8,
              }}
            >
              {apiTools.length === 0 && (
                <span className="muted">Нет API tools</span>
              )}
              {apiTools.map((t) => (
                <label
                  key={t.id}
                  className="flex gap-8"
                  style={{ alignItems: "flex-start", marginBottom: 6 }}
                >
                  <input
                    type="checkbox"
                    checked={toolIds.has(t.id)}
                    onChange={() => toggleTool(t.id)}
                  />
                  <span>
                    #{t.id} {t.name}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex gap-8" style={{ justifyContent: "flex-end" }}>
            {mode === "edit" && (
              <button type="button" className="btn ghost" onClick={removeNode}>
                Удалить ноду
              </button>
            )}
            <button type="button" className="btn ghost" onClick={onClose}>
              Отмена
            </button>
            <button type="button" className="btn" onClick={applyNode}>
              {mode === "create" ? "Создать" : "Сохранить"}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

function EdgeConditionModal({
  graph,
  onGraphChange,
  sourceId,
  transitionIndex,
  onClose,
}: {
  graph: BotGraphConfig;
  onGraphChange: (g: BotGraphConfig) => void;
  sourceId: string;
  transitionIndex: number;
  onClose: () => void;
}) {
  const node = graph.nodes.find((n) => n.id === sourceId);
  const tr: NodeTransition | undefined = node?.transitions?.[transitionIndex];
  const [type, setType] = useState<TransitionCondition["type"]>("always");
  const [value, setValue] = useState("");

  useEffect(() => {
    if (!node || !tr) onClose();
  }, [node, tr, onClose]);

  useEffect(() => {
    if (!node || !tr) return;
    setType(tr.condition.type);
    setValue(
      tr.condition.type === "keyword" ? (tr.condition.value ?? "") : ""
    );
  }, [node, tr, sourceId, transitionIndex]);

  if (!node || !tr) {
    return null;
  }

  const save = () => {
    if (type === "keyword" && !value.trim()) {
      alert("Для условия keyword укажите значение");
      return;
    }
    const g = cloneGraph(graph);
    const n = g.nodes.find((x) => x.id === sourceId);
    if (!n?.transitions?.[transitionIndex]) return;
    if (type === "always" && n.transitions.length > 1) {
      alert(
        "При условии «always» у узла не может быть других исходящих переходов. Удалите лишние рёбра."
      );
      return;
    }
    n.transitions[transitionIndex].condition =
      type === "keyword"
        ? { type: "keyword", value: value.trim() }
        : { type, value: null };
    onGraphChange(g);
    onClose();
  };

  const remove = () => {
    if (!confirm("Удалить переход?")) return;
    const g = cloneGraph(graph);
    const n = g.nodes.find((x) => x.id === sourceId);
    if (!n?.transitions) return;
    n.transitions = n.transitions.filter((_, i) => i !== transitionIndex);
    onGraphChange(g);
    onClose();
  };

  return createPortal(
    <div
      className="modal-overlay"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,23,42,0.35)",
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        className="card"
        style={{ maxWidth: 400, width: "100%" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ margin: "0 0 12px", fontSize: 18 }}>Условие перехода</h3>
        <div className="grid gap-12">
          <label>
            <div className="muted">Тип</div>
            <select
              className="select"
              value={type}
              onChange={(e) => {
                const next = e.target.value as TransitionCondition["type"];
                setType(next);
                if (next !== "keyword") setValue("");
              }}
            >
              <option value="always">always</option>
              <option value="keyword">keyword</option>
              <option value="llm_routing">llm_routing</option>
            </select>
          </label>
          {type === "keyword" && (
            <label>
              <div className="muted">Ключевое слово в сообщении</div>
              <input
                className="input"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                required
              />
            </label>
          )}
          <div className="flex gap-8" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="btn ghost" onClick={remove}>
              Удалить переход
            </button>
            <button type="button" className="btn ghost" onClick={onClose}>
              Отмена
            </button>
            <button type="button" className="btn" onClick={save}>
              Сохранить
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

export function BotGraphEditor(props: BotGraphEditorProps) {
  return (
    <ReactFlowProvider>
      <BotGraphCanvas {...props} />
    </ReactFlowProvider>
  );
}

export const DEFAULT_BOT_GRAPH: BotGraphConfig = {
  entry_node_id: "main",
  gemini_model: DEFAULT_GEMINI_MODEL,
  nodes: [
    {
      id: "main",
      name: "General",
      system_prompt: "Ты дружелюбный ассистент.",
      use_rag: false,
      api_tool_ids: [],
      allowed_document_ids: [],
      transitions: [],
    },
  ],
};
