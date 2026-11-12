import { ArrowRight, ChevronDown, ChevronRight, LockKeyhole, Plus, UsersRound } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";
import { lobbyScene } from "../mocks/data";
import type { Member, Workspace } from "../types";

function MemberCard({ member, className }: { member?: Member; className: string }) {
  if (!member) return null;
  return (
    <button className={`member-card ${className}`}>
      <span className="member-avatar" style={{ backgroundImage: `url(${member.avatar})`, backgroundPosition: member.avatarPosition ?? "0% center" }} aria-hidden="true" />
      <strong>{member.name}</strong>
      {member.role && <span>{member.role}</span>}
      <span>{member.status}</span>
      {member.proxy && <small>{member.proxy}</small>}
    </button>
  );
}

export function LobbyPage({ workspace, onSwitchTrip, onInvite, onOpenLobby, lobbyUnread, onPrivateChat }: { workspace: Workspace; onSwitchTrip: () => void; onInvite: () => void; onOpenLobby: () => void; lobbyUnread: number; onPrivateChat: () => void }) {
  const dateRange = workspace.startDate && workspace.endDate ? `${workspace.startDate.slice(5).replace("-", "月")}日至${workspace.endDate.slice(5).replace("-", "月")}日` : "日期待定";
  return (
    <div className="page page-lobby">
      <StatusBar />
      <PageHeader
        title={<button className="trip-title-button" onClick={onSwitchTrip} aria-label="切换旅行"><span>{workspace.title}</span><ChevronDown size={20} /></button>}
        subtitle={`${workspace.city} · ${dateRange} · ${workspace.travelerCount}人`}
        action={<button className="icon-button" onClick={onInvite} aria-label="邀请同行者"><Plus size={24} /></button>}
      />
      <section className="lobby-scene" aria-label="同行成员">
        <img src={lobbyScene} alt="雨林溪流场景" />
        <div className="scene-overlay" />
        <MemberCard member={workspace.members[0]} className="member-one" />
        <MemberCard member={workspace.members[1]} className="member-two" />
        <MemberCard member={workspace.members[2]} className="member-three" />
        <MemberCard member={workspace.members[3]} className="member-four" />
      </section>
      <button className="shared-card" onClick={() => onPrivateChat()}>
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
