import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  listBots,
  listChatMessages,
  listChatSessions,
  sendChatMessage,
} from "../api";
import { useAuth } from "../state/auth";
import { useWorkspaceContext } from "../state/workspace";
import { Bot, ChatMessage, ChatSession } from "../types";

export function ChatPage() {
  const { token } = useAuth();
  const { activeWorkspaceId } = useWorkspaceContext();
  const [selectedBotId, setSelectedBotId] = useState<number | undefined>();
  const [selectedSessionId, setSelectedSessionId] = useState<number | undefined>();
  const [message, setMessage] = useState("");

  const botsQuery = useQuery({
    queryKey: ["bots", activeWorkspaceId],
    queryFn: () => listBots(token || "", activeWorkspaceId),
    enabled: !!token,
    staleTime: 15_000,
  });

  useEffect(() => {
    if (!selectedBotId && botsQuery.data?.length) {
      setSelectedBotId(botsQuery.data[0].id);
    }
  }, [botsQuery.data, selectedBotId]);

  const sessionsQuery = useQuery({
    queryKey: ["sessions", selectedBotId],
    queryFn: () => listChatSessions(token || "", selectedBotId),
    enabled: !!token && !!selectedBotId,
  });

  const messagesQuery = useQuery({
    queryKey: ["messages", selectedSessionId],
    queryFn: () => listChatMessages(token || "", selectedSessionId || 0),
    enabled: !!token && !!selectedSessionId,
  });

  const sendMutation = useMutation({
    mutationFn: async () => {
      if (!token || !selectedBotId) throw new Error("Нет выбранного бота");
      return sendChatMessage(token, {
        bot_id: selectedBotId,
        session_id: selectedSessionId,
        message,
      });
    },
    onSuccess: (res) => {
      setMessage("");
      setSelectedSessionId(res.session_id);
      void sessionsQuery.refetch();
      void messagesQuery.refetch();
    },
  });

  const handleSend = (e: FormEvent) => {
    e.preventDefault();
    if (!message.trim()) return;
    sendMutation.mutate();
  };

  const handleSelectSession = (id?: number) => {
    setSelectedSessionId(id);
  };

  const renderMessage = (text: string) => {
    const escape = (input: string) =>
      input
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    const escaped = escape(text);
    const withBold = escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    const withBreaks = withBold.replace(/\n/g, "<br />");
    return { __html: withBreaks };
  };

  return (
    <div className="grid gap-16">
      <div className="page-header">
        <h2 className="page-title">Чат с ботом</h2>
        <div className="muted">Workspace: {activeWorkspaceId ?? "—"}</div>
      </div>
      <div className="card">
        <div className="grid grid-2 gap-12">
          <label>
            <div className="muted">Бот</div>
            <select
              className="select"
              value={selectedBotId ?? ""}
              onChange={(e) => {
                const id = Number(e.target.value);
                setSelectedBotId(id);
                setSelectedSessionId(undefined);
              }}
            >
              {botsQuery.data?.map((bot: Bot) => (
                <option key={bot.id} value={bot.id}>
                  {bot.name} (ws {bot.workspace_id})
                </option>
              ))}
            </select>
          </label>
          <label>
            <div className="muted">Сессия</div>
            <select
              className="select"
              value={selectedSessionId ?? ""}
              onChange={(e) =>
                handleSelectSession(
                  e.target.value ? Number(e.target.value) : undefined
                )
              }
            >
              <option value="">Новая сессия</option>
              {sessionsQuery.data?.map((s: ChatSession) => (
                <option key={s.id} value={s.id}>
                  #{s.id} · {s.created_at}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="card">
        <div className="chat-window">
          {sendMutation.isPending && (
            <div className="chat-overlay">
              <div className="spinner large" aria-label="waiting" />
              <div className="muted">Ждем ответ от бота...</div>
            </div>
          )}
          {messagesQuery.data?.map((msg: ChatMessage) => (
            <div
              key={msg.id}
              className={`message ${msg.role}`}
              title={msg.created_at}
            >
              <div className="muted" style={{ fontSize: 12 }}>
                {msg.role}
              </div>
              <div dangerouslySetInnerHTML={renderMessage(msg.content)} />
            </div>
          ))}
          {sendMutation.isPending && (
            <div className="flex gap-8" style={{ alignItems: "center" }}>
              <div className="spinner" aria-label="loading" />
              <div className="muted">Бот думает...</div>
            </div>
          )}
        </div>
        <form className="flex gap-12 mt-12" onSubmit={handleSend}>
          <textarea
            className="textarea"
            placeholder="Сообщение боту"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          <button
            className={`btn ${sendMutation.isPending ? "loading" : ""}`}
            type="submit"
            disabled={sendMutation.isPending}
          >
            {sendMutation.isPending && <div className="spinner small" aria-label="loading" />}
            {sendMutation.isPending ? "Ожидаем ответ..." : "Отправить"}
          </button>
        </form>
      </div>
    </div>
  );
}

