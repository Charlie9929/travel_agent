import { Camera, CloudSun, List, Map as MapIcon, MessageCircle, Pencil, Plus, Receipt, Route, Settings, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, type ApiPoi, type ApiWeather, type JsonObject } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";
import type { Activity, Workspace } from "../types";

function formatDay(date: string) {
  const value = new Date(`${date}T00:00:00`);
  if (Number.isNaN(value.getTime())) return date;
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", weekday: "short" }).format(value);
}

function routeSummary(route: JsonObject | null) {
  const routes = route?.routes as Record<string, { available?: boolean; distance_m?: number; duration_min?: number }> | undefined;
  if (!routes) return "";
  const labels: Record<string, string> = { walk: "步行", bike: "骑行", drive: "驾车", transit: "公交" };
  return Object.entries(routes)
    .filter(([, value]) => value.available)
    .map(([mode, value]) => `${labels[mode] ?? mode} ${value.duration_min ?? "?"} 分钟 / ${value.distance_m ?? "?"} 米`)
    .join(" · ");
}

export function WorldPage({
  workspace,
  onReplan,
  onGenerate,
  onRevise,
  onOpenVersions,
  onAddActivity,
  onEditActivity,
  onDeleteActivity,
  onAddExpense,
  onAddRecord,
  onBack,
  onSettings,
}: {
  workspace: Workspace;
  onReplan: (activity: Activity) => void;
  onGenerate: () => void;
  onRevise: () => void;
  onOpenVersions: () => void;
  onAddActivity: (dayNumber: number) => void;
  onEditActivity: (activity: Activity) => void;
  onDeleteActivity: (activity: Activity) => void;
  onAddExpense: (activity: Activity) => void;
  onAddRecord: (activity: Activity) => void;
  onBack: () => void;
  onSettings: () => void;
}) {
  const days = useMemo(() => Array.from(new Map(workspace.activities.map((activity) => [activity.day, activity.date])).entries()).sort(([a], [b]) => a - b), [workspace.activities]);
  const [selectedDay, setSelectedDay] = useState(days[0]?.[0] ?? 1);
  const [view, setView] = useState<"space" | "schedule">("schedule");
  const [externalLoading, setExternalLoading] = useState(false);
  const [externalError, setExternalError] = useState("");
  const [weather, setWeather] = useState<ApiWeather | null>(null);
  const [poi, setPoi] = useState<ApiPoi | null>(null);
  const [route, setRoute] = useState<JsonObject | null>(null);

  useEffect(() => {
    setSelectedDay(days[0]?.[0] ?? 1);
    setWeather(null);
    setPoi(null);
    setRoute(null);
  }, [workspace.tripId, days]);

  const currentDay = workspace.activities.filter((activity) => activity.day === selectedDay).sort((a, b) => a.order - b.order);
  const selectedDate = days.find(([day]) => day === selectedDay)?.[1] ?? workspace.startDate;

  const loadMapAndWeather = async () => {
    setExternalLoading(true);
    setExternalError("");
    try {
      const first = currentDay[0];
      const second = currentDay[1];
      const calls: Promise<unknown>[] = [api.weather(workspace.city, selectedDate).then(setWeather)];
      if (first?.location) {
        calls.push(api.map.poi(workspace.city, first.location).then((result) => setPoi(result.items[0] ?? null)));
      }
      if (first?.latitude != null && first.longitude != null && second?.latitude != null && second.longitude != null) {
        calls.push(api.map.route(first.latitude, first.longitude, second.latitude, second.longitude).then(setRoute));
      }
      await Promise.all(calls);
    } catch (error) {
      setExternalError((error as Error).message);
    } finally {
      setExternalLoading(false);
    }
  };

  return (
    <div className="page page-world">
      <StatusBar />
      <PageHeader
        title="行程"
        subtitle={`${workspace.title} · 第 ${workspace.version} 版`}
        action={<div className="header-actions"><button className="action-pill" onClick={workspace.activities.length ? onRevise : onGenerate}>{workspace.activities.length ? "整体调整" : "Agent 生成"}</button><button className="icon-button header-settings-button" onClick={onSettings} aria-label="行程设置"><Settings size={19} /></button></div>}
        onBack={onBack}
      />
      <button className="version-link" onClick={onOpenVersions}>查看版本记录</button>
      {!workspace.activities.length ? <section className="itinerary-empty">
        <Sparkles size={30} />
        <h2>还没有生成行程</h2>
        <p>让 Agent 根据目的地、日期、预算和成员需求生成第一版行程。</p>
        <button className="primary-button" onClick={onGenerate}>开始生成行程</button>
      </section> : <>
        <div className="segmented-control">
          <button className={view === "space" ? "is-active" : ""} onClick={() => setView("space")}><MapIcon size={20} />地点顺序</button>
          <button className={view === "schedule" ? "is-active" : ""} onClick={() => setView("schedule")}><List size={20} />日程</button>
        </div>
        <div className="date-tabs dynamic-date-tabs">
          {days.map(([day, date]) => <button key={day} className={day === selectedDay ? "is-active" : ""} onClick={() => { setSelectedDay(day); setWeather(null); setPoi(null); setRoute(null); }}>{formatDay(date)}</button>)}
        </div>
        <button className="external-data-button" onClick={() => void loadMapAndWeather()} disabled={externalLoading}><CloudSun size={17} />{externalLoading ? "正在查询高德和天气…" : "查询当天真实天气与路线"}</button>
        {externalError && <p className="inline-error">{externalError}</p>}
        {weather && <section className="weather-card"><strong>{weather.city ?? workspace.city} · {weather.condition_day ?? "天气未知"}</strong><span>{weather.temperature_min ?? "?"}—{weather.temperature_max ?? "?"}℃ · 降水概率 {weather.precipitation_probability ?? "?"}%{weather.stale ? " · 缓存数据" : ""}</span></section>}
        {view === "space" ? <section className="route-map real-route-list" aria-label="当天地点顺序">
          {currentDay.map((activity, index) => <button key={activity.id} className="real-route-stop" onClick={() => onReplan(activity)}><span>{index + 1}</span><div><strong>{activity.title}</strong><small>{activity.time} · {activity.location}</small></div></button>)}
          {poi && <p className="external-meta">高德匹配：{poi.name ?? "未知地点"}{poi.address ? ` · ${poi.address}` : ""}</p>}
          {routeSummary(route) && <p className="external-meta">首段路线：{routeSummary(route)}</p>}
        </section> : <section className="schedule-view" aria-label="日程列表">
          <div className="schedule-title"><strong>{formatDay(selectedDate)}</strong><span>第 {selectedDay} 天 · {currentDay.length} 项活动</span><button className="inline-action" onClick={() => onAddActivity(selectedDay)}><Plus size={14} />新增活动</button></div>
          {currentDay.map((activity) => <div className="schedule-item" key={activity.id}><time>{activity.time}</time><div><strong>{activity.title}</strong><p>{activity.detail} · {activity.location}{activity.actualPrice != null ? ` · 实际 ¥${activity.actualPrice}` : activity.estimatedPrice != null ? ` · 预计 ¥${activity.estimatedPrice}` : ""}</p><div className="activity-actions"><button onClick={() => onEditActivity(activity)}><Pencil size={13} />编辑</button><button onClick={() => onReplan(activity)}><Sparkles size={13} />Agent 调整</button><button onClick={() => onAddExpense(activity)}><Receipt size={13} />记一笔</button><button onClick={() => onAddRecord(activity)}><Camera size={13} />写记录</button><button className="danger-inline" onClick={() => onDeleteActivity(activity)}><Trash2 size={13} />删除</button></div></div></div>)}
          {!currentDay.length && <button className="secondary-button full-button" onClick={() => onAddActivity(selectedDay)}><Plus size={16} />为这一天添加活动</button>}
        </section>}
      </>}
      <div className="world-footnote"><MessageCircle size={15} /> 当前计划 v{workspace.version} · 行程调整确认后才会写入</div>
      {!!currentDay.length && <div className="sr-only"><Route size={1} />{currentDay.length} 个活动</div>}
    </div>
  );
}
