import { ChevronRight, MessageCircle, UsersRound } from "lucide-react";
import type { ApiTrip } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";

export type LobbyPreview = { tripId: number; lastMessage: string; lastAt: string | null; unread: number };

function messageTime(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export function LobbyListPage({ trips, previews, loading, onOpenChat, onManage }: { trips: ApiTrip[]; previews: LobbyPreview[]; loading: boolean; onOpenChat: (tripId: number) => void; onManage: (tripId: number) => void }) {
  return <div className="page page-lobby-list">
    <StatusBar />
    <PageHeader title="协作大厅" subtitle="每场旅行都有独立的同行群聊" />
    {!trips.length ? <section className="itinerary-empty"><UsersRound size={30} /><h2>还没有旅行群聊</h2><p>创建或加入旅行后，对应的协作群聊会出现在这里。</p></section> : <section className="lobby-thread-list">
      {trips.map((trip) => {
        const preview = previews.find((item) => item.tripId === trip.id);
        return <article className="lobby-thread" key={trip.id}>
          <button className="lobby-thread-main" onClick={() => onOpenChat(trip.id)}>
            <span className="lobby-thread-avatar"><MessageCircle size={23} /></span>
            <span className="lobby-thread-copy"><strong>{trip.title}</strong><small>{preview?.lastMessage || (loading ? "正在读取消息…" : `${trip.city}旅行群聊`)}</small></span>
            <span className="lobby-thread-meta"><time>{messageTime(preview?.lastAt ?? null)}</time>{Boolean(preview?.unread) && <b>{preview?.unread}</b>}</span>
          </button>
          <button className="lobby-thread-manage" onClick={() => onManage(trip.id)} aria-label={`管理${trip.title}`}><UsersRound size={16} /><span>成员与需求</span><ChevronRight size={14} /></button>
        </article>;
      })}
    </section>}
  </div>;
}
