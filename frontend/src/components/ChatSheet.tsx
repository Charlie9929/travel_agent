import { useState } from "react";
import { Bot, RefreshCw, Send } from "lucide-react";
import type { AgentMessage, AuthUser, LobbyMessage } from "../types";
import { ModalSheet } from "./ModalSheet";

export function ChatSheet({
  mode,
  lobbyMessages,
  agentMessages,
  loading,
  onSend,
  onRefresh,
  onOpenCandidate,
  onClose,
  title,
  currentUser,
}: {
  mode: "lobby" | "agent";
  lobbyMessages: LobbyMessage[];
  agentMessages: AgentMessage[];
  loading: boolean;
  onSend: (content: string) => void;
  onRefresh: () => void;
  onOpenCandidate?: (data: Record<string, unknown>) => void;
  onClose: () => void;
  title?: string;
  currentUser: AuthUser;
}) {
  const [content, setContent] = useState("");
  const isLobby = mode === "lobby";
  const messages = isLobby ? lobbyMessages : agentMessages;

  return (
    <ModalSheet title={title ?? (isLobby ? "大厅讨论" : "和 Agent 私聊")} onClose={onClose} wide>
      <div className="chat-toolbar"><span>{isLobby ? "同行者可见 · @Agent 会结合最近 30 条公开消息生成候选" : "仅你和 Agent 可见 · 调整需求会生成候选"}</span><button className="small-icon-button" onClick={onRefresh} aria-label="刷新消息"><RefreshCw size={16} /></button></div>
      <div className="chat-list" aria-live="polite">
        {messages.length === 0 && <div className="empty-chat">还没有消息，发起第一条对话吧。</div>}
        {isLobby ? lobbyMessages.map((message) => {
          const mine = message.kind === "user" && message.senderId === currentUser.id;
          const hasCandidate = Boolean(message.structuredData.requires_confirmation && message.structuredData.ai_run_id);
          const label = mine ? "我" : message.kind === "agent" ? "Agent" : message.kind === "system" ? "系统" : message.senderNickname ?? "同行者";
          return <div className={`chat-message-row ${mine ? "is-mine" : ""}`} key={message.id}>{!mine && <span className={`chat-avatar ${message.kind === "agent" ? "is-agent" : message.kind === "system" ? "is-system" : ""}`}>{message.kind === "agent" ? <Bot size={18} /> : message.kind === "system" ? "系" : message.senderAvatarUrl ? <img src={message.senderAvatarUrl} alt="" /> : label.slice(0, 1)}</span>}<article className={`chat-bubble ${mine ? "is-user" : message.kind === "agent" ? "is-agent" : message.kind === "system" ? "is-system" : ""}`}><strong>{label}</strong><p>{message.content}</p>{hasCandidate && <button className="candidate-message-button" onClick={() => onOpenCandidate?.(message.structuredData)}>查看公开调整候选</button>}</article>{mine && <span className="chat-avatar">{currentUser.avatarUrl ? <img src={currentUser.avatarUrl} alt="" /> : currentUser.nickname.slice(0, 1)}</span>}</div>;
        }) : agentMessages.map((message) => {
          const hasCandidate = Boolean(message.structuredData.requires_confirmation && message.structuredData.ai_run_id);
          const applied = Boolean(message.structuredData.applied);
          const mine = message.role === "user";
          return <div className={`chat-message-row ${mine ? "is-mine" : ""}`} key={message.id}>{!mine && <span className="chat-avatar is-agent"><Bot size={18} /></span>}<article className={`chat-bubble ${mine ? "is-user" : "is-agent"}`}><strong>{mine ? "我" : "Agent"}</strong><p>{message.content || (message.status === "pending" ? "正在思考…" : "暂无内容")}</p>{hasCandidate && <button className="candidate-message-button" onClick={() => onOpenCandidate?.(message.structuredData)}>查看并确认调整建议</button>}{applied && !mine && <small className="candidate-applied">已应用到行程</small>}</article>{mine && <span className="chat-avatar">{currentUser.avatarUrl ? <img src={currentUser.avatarUrl} alt="" /> : currentUser.nickname.slice(0, 1)}</span>}</div>;
        })}
      </div>
      <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); if (content.trim()) { onSend(content.trim()); setContent(""); } }}>
        <input className="text-input" value={content} onChange={(event) => setContent(event.target.value)} placeholder={isLobby ? "输入消息，@Agent 请求建议" : "告诉 Agent 你的私密需求，例如过敏信息"} disabled={loading} />
        <button className="send-button" disabled={loading || !content.trim()} aria-label="发送"><Send size={18} /></button>
      </form>
    </ModalSheet>
  );
}
