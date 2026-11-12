import { Camera, ChevronRight, Clock3, WalletCards } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";
import type { Workspace } from "../types";

const icons = [Clock3, WalletCards, Camera];

export function FunctionsPage({ workspace, onOpen }: { workspace: Workspace; onOpen: (label: string) => void }) {
  const rows = [
    ["行程版本", `当前第 ${workspace.version} 版 · 查看真实记录`],
    ["记账与分账", "查看账单和成员分摊"],
    ["旅行高光", "查看本次旅行记录"],
  ] as const;
  return (
    <div className="page page-functions">
      <StatusBar />
      <PageHeader title="功能" />
      <section className="trip-overview"><small>本次旅行</small><strong>{workspace.city}</strong><span>11月6—8日 · {workspace.travelerCount}人</span><b>正在规划</b></section>
      <div className="function-list">
        {rows.map(([title, description], index) => {
          const Icon = icons[index];
          return <button key={title} className="list-row function-row" onClick={() => onOpen(title)}><Icon size={22} /><span><strong>{title}</strong><small>{description}</small></span><ChevronRight size={20} /></button>;
        })}
      </div>
      <section className="history-section"><small>历史旅行</small>{workspace.historyTrips.map((trip) => <button className="history-row" key={trip.title} onClick={() => onOpen(trip.title)}><span><strong>{trip.title}</strong><small>{trip.dates} · {trip.people}</small></span><ChevronRight size={20} /></button>)}</section>
      <section className="closed-feature"><strong>足迹地图</strong><span>暂未开放</span></section>
    </div>
  );
}
