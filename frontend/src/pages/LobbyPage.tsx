import { ArrowRight, ChevronRight, LockKeyhole, Plus, UsersRound } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";
import type { Member, Workspace } from "../types";

function MemberCard({ member }: { member: Member }) {
  return (
    <article className="member-card">
      <span className={`member-avatar ${member.avatar ? "" : "member-avatar-fallback"}`} style={member.avatar ? { backgroundImage: `url(${member.avatar})`, backgroundPosition: member.avatarPosition ?? "center" } : undefined} aria-hidden="true">{member.avatar ? "" : member.name.slice(0, 1)}</span>
      <span className="member-copy"><strong>{member.name}</strong><small>{[member.role, member.status, member.proxy].filter(Boolean).join(" · ")}</small></span>
    </article>
  );
}

export function LobbyPage({ workspace, onBack, onInvite, onOpenLobby, lobbyUnread, onPrivateChat, onOpenRequirements }: { workspace: Workspace; onBack: () => void; onInvite: () => void; onOpenLobby: () => void; lobbyUnread: number; onPrivateChat: () => void; onOpenRequirements: () => void }) {
  const dateRange = workspace.startDate && workspace.endDate ? `${workspace.startDate.slice(5).replace("-", "月")}日至${workspace.endDate.slice(5).replace("-", "月")}日` : "日期待定";
  return (
    <div className="page page-lobby">
      <StatusBar />
      <PageHeader
        title={workspace.title}
        subtitle={`${workspace.city} · ${dateRange} · ${workspace.travelerCount}人`}
        action={<button className="icon-button" onClick={onInvite} aria-label="邀请同行者"><Plus size={24} /></button>}
        onBack={onBack}
      />
      <section className="member-grid" aria-label="同行成员">{workspace.members.map((member) => <MemberCard member={member} key={member.id} />)}</section>
      <button className="shared-card" onClick={onOpenRequirements}>
        <div className="shared-card-title"><strong>同行者的想法</strong><span>同行者可见</span></div>
        <p>{workspace.sharedSummary}</p>
        <small>{workspace.budget} · 已分享 {workspace.sharedCount} 条</small>
        <ChevronRight className="shared-card-chevron" size={17} />
      </button>
      <button className="list-row discussion-row" onClick={onOpenLobby}>
        <UsersRound size={22} /><strong>大厅讨论</strong><span>{lobbyUnread ? `${lobbyUnread} 条未读` : "打开群聊"}</span><ChevronRight size={18} />
      </button>
      <button className="private-entry" onClick={onPrivateChat}>
        <LockKeyhole size={20} strokeWidth={1.6} />
        <span><strong>和 Agent 私聊</strong><small>仅你和 Agent 可见</small></span>
        <span className="entry-arrow"><ArrowRight size={21} /></span>
      </button>
    </div>
  );
}
