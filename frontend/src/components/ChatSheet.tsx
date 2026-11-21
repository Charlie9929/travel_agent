import { useEffect, useRef, useState } from "react";
import { Bot, RefreshCw, Send } from "lucide-react";
import type { AgentMessage, AuthUser, LobbyMessage } from "../types";
import { ModalSheet } from "./ModalSheet";

export function ChatSheet({
  mode,
  lobbyMessages,
  agentMessages,
  loading,
  onSend,
  onRetry,
  onRefresh,
  onOpenCandidate,
  onClose,
  title,
  currentUser,
  readOnly = false,
}: {
  mode: "lobby" | "agent";
  lobbyMessages: LobbyMessage[];
  agentMessages: AgentMessage[];
  loading: boolean;
  onSend: (content: string) => void;
  onRetry?: (message: LobbyMessage) => void;
  onRefresh: () => void;
  onOpenCandidate?: (data: Record<string, unknown>) => void;
  onClose: () => void;
  title?: string;
  currentUser: AuthUser;
  readOnly?: boolean;
}) {
  const [content, setContent] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const isLobby = mode === "lobby";
  const messages = isLobby ? lobbyMessages : agentMessages;

  useEffect(() => {
    const list = listRef.current;
    if (list && stickToBottom.current) list.scrollTop = list.scrollHeight;
  }, [messages.length, loading]);

  return (
    <ModalSheet title={title ?? (isLobby ? "大厅讨论" : "和 Agent 私聊")} onClose={onClose} wide>
      <div className="chat-toolbar"><span>{readOnly ? "旅行已归档 · 仅支持查看" : loading ? (isLobby ? "消息发送中…" : "Agent 正在思考…") : isLobby ? "同行者可见 · @Agent 可回答行程问题，也可生成调整候选" : "仅你和 Agent 可见 · 可询问行程或生成调整候选"}</span><button className="small-icon-button" onClick={onRefresh} aria-label="刷新消息"><RefreshCw size={16} /></button></div>
      <div className="chat-list" ref={listRef} onScroll={(event) => {
        const list = event.currentTarget;
        stickToBottom.current = list.scrollHeight - list.scrollTop - list.clientHeight < 72;
      }} aria-live="polite">
        {messages.length === 0 && <div className="empty-chat">还没有消息，发起第一条对话吧。</div>}
        {isLobby ? lobbyMessages.map((message) => {
          const mine = message.kind === "user" && message.senderId === currentUser.id;
          const hasCandidate = Boolean(message.structuredData.requires_confirmation && message.structuredData.ai_run_id);
          const localStatus = String(message.structuredData.local_status ?? "");
          const retryMessageId = Number(message.structuredData.retry_message_id ?? 0);
          const canRetry = localStatus === "failed" && (retryMessageId > 0 || Boolean(message.structuredData.retry_content));
          const label = mine ? "我" : message.kind === "agent" ? "Agent" : message.kind === "system" ? "系统" : message.senderNickname ?? "同行者";
          const displayContent = localStatus === "pending" ? "Agent 正在回复…" : message.content || (localStatus === "failed" ? "Agent 暂时无法回复" : "");
          return <div className={`chat-message-row ${mine ? "is-mine" : ""}`} key={message.id}>{!mine && <span className={`chat-avatar ${message.kind === "agent" ? "is-agent" : message.kind === "system" ? "is-system" : ""}`}>{message.kind === "agent" ? <Bot size={18} /> : message.kind === "system" ? "系" : message.senderAvatarUrl ? <img src={message.senderAvatarUrl} alt="" /> : label.slice(0, 1)}</span>}<article className={`chat-bubble ${mine ? "is-user" : message.kind === "agent" ? "is-agent" : message.kind === "system" ? "is-system" : ""}`}><strong>{label}</strong><p>{displayContent}</p>{hasCandidate && <button className="candidate-message-button" onClick={() => onOpenCandidate?.(message.structuredData)}>查看公开调整候选</button>}{canRetry && <button className="chat-retry-button" onClick={() => onRetry?.(message)}>重新尝试</button>}</article>{mine && <span className="chat-avatar">{currentUser.avatarUrl ? <img src={currentUser.avatarUrl} alt="" /> : currentUser.nickname.slice(0, 1)}</span>}</div>;
        }) : agentMessages.map((message) => {
          const hasCandidate = Boolean(message.structuredData.requires_confirmation && message.structuredData.ai_run_id);
          const applied = Boolean(message.structuredData.applied);
          const mine = message.role === "user";
          return <div className={`chat-message-row ${mine ? "is-mine" : ""}`} key={message.id}>{!mine && <span className="chat-avatar is-agent"><Bot size={18} /></span>}<article className={`chat-bubble ${mine ? "is-user" : "is-agent"}`}><strong>{mine ? "我" : "Agent"}</strong><p>{message.content || (message.status === "pending" ? "正在思考…" : "暂无内容")}</p>{hasCandidate && <button className="candidate-message-button" onClick={() => onOpenCandidate?.(message.structuredData)}>查看并确认调整建议</button>}{applied && !mine && <small className="candidate-applied">已应用到行程</small>}</article>{mine && <span className="chat-avatar">{currentUser.avatarUrl ? <img src={currentUser.avatarUrl} alt="" /> : currentUser.nickname.slice(0, 1)}</span>}</div>;
        })}
      </div>
      {readOnly ? <div className="empty-chat">旅行已归档，聊天内容仅支持查看。</div> : <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); if (content.trim()) { onSend(content.trim()); setContent(""); } }}>
        <input className="text-input" value={content} onChange={(event) => setContent(event.target.value)} placeholder={isLobby ? "输入消息，@Agent 可询问或请求调整" : "告诉 Agent 你的私密需求，例如过敏信息"} disabled={loading} />
        <button className="send-button" disabled={loading || !content.trim()} aria-label="发送"><Send size={18} /></button>
      </form>}
    </ModalSheet>
  );
}
