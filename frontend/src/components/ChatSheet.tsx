import { useState } from "react";
import { RefreshCw, Send } from "lucide-react";
import type { AgentMessage, LobbyMessage } from "../types";
import { ModalSheet } from "./ModalSheet";

export function ChatSheet({
  mode,
  lobbyMessages,
  agentMessages,
  loading,
  onSend,
  onRefresh,
  onClose,
  title,
}: {
  mode: "lobby" | "agent";
  lobbyMessages: LobbyMessage[];
  agentMessages: AgentMessage[];
  loading: boolean;
  onSend: (content: string) => void;
  onRefresh: () => void;
  onClose: () => void;
  title?: string;
}) {
  const [content, setContent] = useState("");
  const isLobby = mode === "lobby";
  const messages = isLobby ? lobbyMessages : agentMessages;

  return (
    <ModalSheet title={title ?? (isLobby ? "大厅讨论" : "和 Agent 私聊")} onClose={onClose} wide>
      <div className="chat-toolbar"><span>{isLobby ? "同行者可见 · @Agent 可请求公开建议" : "仅你和 Agent 可见"}</span><button className="small-icon-button" onClick={onRefresh} aria-label="刷新消息"><RefreshCw size={16} /></button></div>
      <div className="chat-list" aria-live="polite">
        {messages.length === 0 && <div className="empty-chat">还没有消息，发起第一条对话吧。</div>}
        {isLobby ? lobbyMessages.map((message) => <article className={`chat-bubble ${message.kind === "agent" ? "is-agent" : ""}`} key={message.id}><strong>{message.kind === "agent" ? "Agent" : message.senderNickname ?? "同行者"}</strong><p>{message.content}</p></article>) : agentMessages.map((message) => <article className={`chat-bubble ${message.role === "assistant" ? "is-agent" : "is-user"}`} key={message.id}><strong>{message.role === "assistant" ? "Agent" : "我"}</strong><p>{message.content || (message.status === "pending" ? "正在思考…" : "暂无内容")}</p></article>)}
      </div>
      <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); if (content.trim()) { onSend(content.trim()); setContent(""); } }}>
        <input className="text-input" value={content} onChange={(event) => setContent(event.target.value)} placeholder={isLobby ? "输入消息，@Agent 请求建议" : "告诉 Agent 你的私密需求，例如过敏信息"} disabled={loading} />
        <button className="send-button" disabled={loading || !content.trim()} aria-label="发送"><Send size={18} /></button>
      </form>
    </ModalSheet>
  );
}
