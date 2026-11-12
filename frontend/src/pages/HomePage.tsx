import { ArrowRight, BookOpen, ChevronRight, LockKeyhole, Settings } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";
import { homeScene } from "../mocks/data";

export function HomePage({ onOpen, onPrivateChat }: { onOpen: (label: string) => void; onPrivateChat: () => void }) {
  return (
    <div className="page page-home">
      <StatusBar />
      <PageHeader title="林予的小家" subtitle="仅你和 Agent 可见" action={<button className="icon-button" onClick={() => onOpen("设置")} aria-label="设置"><Settings size={23} /></button>} />
      <section className="home-scene" aria-label="私人小家场景"><img src={homeScene} alt="英伦生活空间" /><div className="scene-overlay" /></section>
      <button className="conversation-card" onClick={() => onOpen("上次的对话")}><strong>上次的对话</strong><p>打开最近一次 Agent 私聊记录</p></button>
      <button className="list-row memory-row" onClick={() => onOpen("记忆簿")}><BookOpen size={22} /><strong>记忆簿</strong><ChevronRight size={18} /></button>
      <button className="private-entry home-entry" onClick={onPrivateChat}><LockKeyhole size={20} strokeWidth={1.6} /><span><strong>和 Agent 聊聊</strong></span><span className="entry-arrow"><ArrowRight size={21} /></span></button>
    </div>
  );
}
