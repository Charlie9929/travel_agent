import { ChevronRight, List, Map, MessageCircle, Route, Sparkles } from "lucide-react";
import { useState } from "react";
import routeMap from "../assets/route-map.svg";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";
import type { Activity, Workspace } from "../types";

const mapPoints = [
  { number: 1, title: "浙博孤山馆", meta: "09:30 · 参观", className: "point-one" },
  { number: 2, title: "湖畔午餐", meta: "12:00 · 已预订", className: "point-two" },
  { number: 3, title: "湖滨漫步", meta: "14:00 · 步行45分钟", className: "point-three" },
  { number: 4, title: "晚餐", meta: "18:30 · 已预订", className: "point-four" },
];

function activityForDay(workspace: Workspace, day: number) {
  return workspace.activities.filter((activity) => activity.day === day);
}

export function WorldPage({ workspace, onReplan }: { workspace: Workspace; onReplan: (activity: Activity) => void }) {
  const [view, setView] = useState<"space" | "schedule">("space");
  const currentActivity = workspace.activities.find((activity) => activity.title === "湖滨漫步") ?? workspace.activities[2] ?? {
    id: -1,
    day: 2,
    date: "",
    time: "14:00",
    title: "下午活动",
    type: "other" as const,
    detail: "等待行程活动",
    location: workspace.city,
  };
  const currentDay = activityForDay(workspace, 2);
  return (
    <div className="page page-world">
      <StatusBar />
      <PageHeader title="旅行世界" subtitle={`${workspace.city} · 行程第 ${workspace.version} 版`} action={<button className="action-pill" onClick={() => onReplan(currentActivity)}>补充需求</button>} />
      <button className="version-link">版本记录</button>
      <div className="segmented-control">
        <button className={view === "space" ? "is-active" : ""} onClick={() => setView("space")}><Map size={20} />空间</button>
        <button className={view === "schedule" ? "is-active" : ""} onClick={() => setView("schedule")}><List size={20} />日程</button>
      </div>
      <div className="date-tabs">
        <button>06 周五</button><button className="is-active">07 周六</button><button>08 周日</button>
      </div>
      {view === "space" ? <>
        <section className="route-map" aria-label="路线示意">
          <img src={routeMap} alt="杭州路线示意" />
          <span className="lake-label">西湖</span>
          <span className="walk-label">步行 10 分钟</span>
          {mapPoints.map((point) => <div key={point.number} className={`map-stop ${point.className}`}><span>{point.number}</span><div><strong>{point.title}</strong><small>{point.meta}</small></div></div>)}
          <small className="route-caption">路线示意</small>
        </section>
        <section className="current-activity">
          <div className="activity-heading"><span>第 2 天</span><button><Route size={15} />交通与预算</button></div>
          <div className="activity-main"><time>14:00</time><div><strong>{currentActivity.title}</strong><p>{currentActivity.detail} · {currentActivity.location}</p></div></div>
          <button className="proposal-card" onClick={() => onReplan(currentActivity)}>
            <div><strong><Sparkles size={16} />下午有一处调整建议</strong><p>乘车去湖边喝茶，其他三站照旧。</p></div><ChevronRight size={18} />
          </button>
        </section>
      </> : <section className="schedule-view" aria-label="日程列表">
        <div className="schedule-title"><strong>11月7日 · 周六</strong><span>第2天 · 行程第 {workspace.version} 版 · {workspace.travelerCount}人</span></div>
        {currentDay.map((activity, index) => <div className="schedule-item" key={activity.id}><time>{activity.time}</time><div><strong>{activity.title}</strong><p>{activity.detail}{activity.booked ? " · 已确认" : ""}</p></div>{index < currentDay.length - 1 && <small className="schedule-transport">{index === 0 ? "车程约20分钟" : index === 1 ? "步行约10分钟" : "返程约15分钟"}</small>}</div>)}
        <button className="proposal-card schedule-proposal" onClick={() => onReplan(currentActivity)}><div><strong><Sparkles size={16} />下午有一处调整建议</strong><p>乘车去湖边喝茶，其他三站照旧。</p></div><ChevronRight size={18} /></button>
      </section>}
      <div className="world-footnote"><MessageCircle size={15} /> 当前计划 v{workspace.version} · 仅更新行程，不会自动支付</div>
      <div className="sr-only">{currentDay.length} 个活动</div>
    </div>
  );
}
