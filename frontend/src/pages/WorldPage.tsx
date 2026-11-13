import { Camera, CalendarPlus, CloudSun, MapPin, Navigation, Pencil, Plus, Receipt, Route, Settings, Sparkles, Trash2, UsersRound } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ApiPoi, type ApiWeather } from "../api/client";
import { AmapTripMap } from "../components/AmapTripMap";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";
import type { Activity, Workspace } from "../types";

type MapApp = "amap" | "baidu" | "tencent";
type RouteChoice = { available?: boolean; distance_m?: number; duration_min?: number };
type Segment = { from: Activity; to: Activity; routes: Record<string, RouteChoice> };

function formatDay(date: string) {
  const value = new Date(`${date}T00:00:00`);
  return Number.isNaN(value.getTime()) ? date : new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", weekday: "short" }).format(value);
}

function formatQueryTime(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function mapRouteUrl(app: MapApp, activity: Activity, mode = "walk") {
  const { latitude: lat, longitude: lng } = activity;
  const name = encodeURIComponent(activity.location || activity.title);
  if (lat == null || lng == null) return `https://uri.amap.com/search?keyword=${name}&src=行伴`;
  if (app === "baidu") return `baidumap://map/direction?destination=latlng:${lat},${lng}|name:${name}&mode=${mode === "drive" ? "driving" : mode === "transit" ? "transit" : "walking"}&src=webapp.行伴`;
  if (app === "tencent") return `qqmap://map/routeplan?type=${mode === "drive" ? "drive" : mode === "transit" ? "bus" : "walk"}&to=${name}&tocoord=${lat},${lng}&referer=行伴`;
  return `https://uri.amap.com/navigation?to=${lng},${lat},${name}&mode=${mode === "drive" ? "car" : mode === "transit" ? "bus" : mode}&policy=1&src=行伴&coordinate=gaode&callnative=1`;
}

function downloadCalendar(workspace: Workspace, activities: Activity[]) {
  const pad = (value: number) => String(value).padStart(2, "0");
  const escape = (value: string) => value.replace(/\\/g, "\\\\").replace(/,/g, "\\,").replace(/;/g, "\\;").replace(/\n/g, "\\n");
  const events = activities.map((activity) => {
    const start = new Date(`${activity.date}T${activity.time === "待定" ? "09:00" : activity.time}:00`);
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    const stamp = (date: Date) => `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}T${pad(date.getHours())}${pad(date.getMinutes())}00`;
    return ["BEGIN:VEVENT", `UID:xingban-${workspace.tripId}-${activity.id}@local`, `DTSTART:${stamp(start)}`, `DTEND:${stamp(end)}`, `SUMMARY:${escape(activity.title)}`, `LOCATION:${escape(activity.location)}`, `DESCRIPTION:${escape(activity.detail)}`, "END:VEVENT"].join("\r\n");
  });
  const content = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//行伴//Travel Itinerary//CN", "CALSCALE:GREGORIAN", ...events, "END:VCALENDAR"].join("\r\n");
  const url = URL.createObjectURL(new Blob([content], { type: "text/calendar;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${workspace.title}.ics`;
  link.click();
  URL.revokeObjectURL(url);
}

export function WorldPage({ workspace, onReplan, onGenerate, onRevise, onOpenVersions, onAddActivity, onEditActivity, onDeleteActivity, onAddExpense, onAddRecord, onBack, onSettings }: {
  workspace: Workspace; onReplan: (activity: Activity) => void; onGenerate: () => void; onRevise: () => void; onOpenVersions: () => void; onAddActivity: (dayNumber: number) => void; onEditActivity: (activity: Activity) => void; onDeleteActivity: (activity: Activity) => void; onAddExpense: (activity: Activity) => void; onAddRecord: (activity: Activity) => void; onBack: () => void; onSettings: () => void;
}) {
  const days = useMemo(() => Array.from(new Map(workspace.activities.map((activity) => [activity.day, activity.date])).entries()).sort(([a], [b]) => a - b), [workspace.activities]);
  const [selectedDay, setSelectedDay] = useState(days[0]?.[0] ?? 1);
  const [selectedActivityId, setSelectedActivityId] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [mapApp, setMapApp] = useState<MapApp>(() => (localStorage.getItem("xingban-map-app") as MapApp | null) ?? "amap");
  const [externalLoading, setExternalLoading] = useState(false);
  const [externalError, setExternalError] = useState("");
  const [weather, setWeather] = useState<ApiWeather | null>(null);
  const [poi, setPoi] = useState<ApiPoi | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const currentDay = useMemo(() => workspace.activities.filter((activity) => activity.day === selectedDay).sort((a, b) => a.order - b.order), [workspace.activities, selectedDay]);
  const selectedDate = days.find(([day]) => day === selectedDay)?.[1] ?? workspace.startDate;

  useEffect(() => { setSelectedDay(days[0]?.[0] ?? 1); setSelectedActivityId(null); }, [workspace.tripId, days]);
  useEffect(() => { localStorage.setItem("xingban-map-app", mapApp); }, [mapApp]);

  const loadContext = useCallback(async () => {
    if (!currentDay.length) return;
    setExternalLoading(true); setExternalError("");
    try {
      const first = currentDay[0];
      const [weatherResult, poiResult] = await Promise.all([api.weather(workspace.city, selectedDate), first.location ? api.map.poi(workspace.city, first.location) : Promise.resolve({ items: [] as ApiPoi[], provider: "amap", queried_at: "" })]);
      setWeather(weatherResult); setPoi(poiResult.items[0] ?? null);
      const cityCode = poiResult.items[0]?.adcode ?? undefined;
      const nextSegments: Segment[] = [];
      for (let index = 0; index < currentDay.length - 1; index += 1) {
        const from = currentDay[index]; const to = currentDay[index + 1];
        if (from.latitude == null || from.longitude == null || to.latitude == null || to.longitude == null) continue;
        const result = await api.map.route(from.latitude, from.longitude, to.latitude, to.longitude, cityCode);
        nextSegments.push({ from, to, routes: (result.routes ?? {}) as Record<string, RouteChoice> });
      }
      setSegments(nextSegments);
    } catch (error) { setExternalError((error as Error).message); }
    finally { setExternalLoading(false); }
  }, [currentDay, selectedDate, workspace.city]);

  useEffect(() => { setWeather(null); setPoi(null); setSegments([]); void loadContext(); }, [loadContext]);
  const selectedActivity = currentDay.find((item) => item.id === selectedActivityId) ?? currentDay[0];

  return <div className="page page-world workbench-page"><StatusBar /><PageHeader title="行程" subtitle={`${workspace.title} · 第 ${workspace.version} 版`} onBack={onBack} action={<div className="header-actions"><button className="action-pill" onClick={workspace.activities.length ? onRevise : onGenerate}>{workspace.activities.length ? "整体调整" : "Agent 生成"}</button><button className="icon-button header-settings-button" onClick={onSettings} aria-label="行程设置"><Settings size={19} /></button></div>} />
    {!workspace.activities.length ? <section className="itinerary-empty"><Sparkles size={30} /><h2>还没有生成行程</h2><p>让 Agent 根据目的地、日期、预算和成员需求生成第一版行程。</p><button className="primary-button" onClick={onGenerate}>开始生成行程</button></section> : <div className="trip-workbench">
      <aside className="workbench-meta-panel"><div><small>本次旅行</small><h2>{workspace.title}</h2><p>{workspace.city} · {workspace.startDate}—{workspace.endDate}</p></div><div className="workbench-stat"><UsersRound size={17} /><span>{workspace.travelerCount} 人同行</span></div><div className="workbench-stat"><Route size={17} /><span>{workspace.activities.length} 项活动</span></div><section><small>同行成员</small><div className="workbench-members">{workspace.members.map((member) => <span title={`${member.name} · ${member.role ?? "member"}`} key={member.id}>{member.name.slice(0, 1)}</span>)}</div></section><label className="field-label compact-field">默认地图<select className="text-input" value={mapApp} onChange={(event) => setMapApp(event.target.value as MapApp)}><option value="amap">高德地图</option><option value="baidu">百度地图</option><option value="tencent">腾讯地图</option></select></label><button className="secondary-button workbench-side-action" onClick={() => selectedActivity && window.location.assign(mapRouteUrl(mapApp, selectedActivity))} disabled={!selectedActivity}><Navigation size={16} />导航到当前地点</button><button className="secondary-button workbench-side-action" onClick={() => downloadCalendar(workspace, workspace.activities)}><CalendarPlus size={16} />导出日历 .ics</button><button className="text-button" onClick={onOpenVersions}>查看第 {workspace.version} 版修改记录</button></aside>
      <main className="workbench-map-panel"><AmapTripMap activities={currentDay} selectedActivityId={selectedActivityId} onSelect={(activity) => setSelectedActivityId(activity.id)} /><div className="map-context-strip">{weather ? <><CloudSun size={17} /><strong>{weather.condition_day ?? "天气未知"}</strong><span>{weather.temperature_min ?? "?"}—{weather.temperature_max ?? "?"}℃ · 降水 {weather.precipitation_probability ?? "?"}%</span></> : <span>{externalLoading ? "正在查询天气与路线…" : "暂无天气信息"}</span>}{poi && <small>高德 POI · {poi.name}{poi.open_hours ? ` · 营业 ${poi.open_hours}` : ""}{poi.average_cost != null ? ` · 参考人均 ¥${poi.average_cost}` : ""}</small>}{externalError && <small className="inline-error">{externalError}</small>}</div></main>
      <section className={`workbench-itinerary-panel ${drawerOpen ? "is-open" : "is-collapsed"}`}><button className="mobile-drawer-handle" onClick={() => setDrawerOpen((value) => !value)} aria-label={drawerOpen ? "收起日程" : "展开日程"}><i /></button><div className="date-tabs dynamic-date-tabs">{days.map(([day, date]) => <button key={day} className={day === selectedDay ? "is-active" : ""} onClick={() => { setSelectedDay(day); setSelectedActivityId(null); }}>{formatDay(date)}</button>)}</div><div className="schedule-title workbench-schedule-title"><strong>第 {selectedDay} 天</strong><span>{currentDay.length} 项活动</span><button className="inline-action" onClick={() => onAddActivity(selectedDay)}><Plus size={14} />新增</button></div><div className="workbench-activity-list">{currentDay.map((activity) => { const segment = segments.find((item) => item.from.id === activity.id); const priceLabel = activity.actualPrice != null ? activity.priceSource === "amap" ? `高德参考 ¥${activity.actualPrice}${activity.priceQueriedAt ? ` · ${formatQueryTime(activity.priceQueriedAt)}查询` : ""}` : `人工记录 ¥${activity.actualPrice}` : activity.estimatedPrice != null ? `AI 估算 ¥${activity.estimatedPrice}` : "暂无价格"; return <div key={activity.id} className="activity-and-transfer"><article className={`workbench-activity-card ${selectedActivityId === activity.id ? "is-selected" : ""}`} onClick={() => setSelectedActivityId(activity.id)}><time>{activity.time}</time><div><strong>{activity.title}</strong><p><MapPin size={12} />{activity.location}</p><small>{priceLabel}</small>{activity.openHours && <small className="source-note">营业参考：{activity.openHours}{activity.openHoursSource ? ` · ${activity.openHoursSource}` : ""}</small>}{activity.quotedPriceNote && <small className="source-note">{activity.quotedPriceNote}</small>}<div className="activity-actions"><button onClick={(event) => { event.stopPropagation(); onEditActivity(activity); }}><Pencil size={13} />编辑</button><button onClick={(event) => { event.stopPropagation(); onReplan(activity); }}><Sparkles size={13} />重排</button><button onClick={(event) => { event.stopPropagation(); onAddExpense(activity); }}><Receipt size={13} />记账</button><button onClick={(event) => { event.stopPropagation(); onAddRecord(activity); }}><Camera size={13} />记录</button><button onClick={(event) => { event.stopPropagation(); window.location.assign(mapRouteUrl(mapApp, activity)); }}><Navigation size={13} />导航</button><button className="danger-inline" onClick={(event) => { event.stopPropagation(); onDeleteActivity(activity); }}><Trash2 size={13} />删除</button></div></div></article>{segment && <div className="segment-route-card"><span>{activity.title} → {segment.to.title}</span><div>{Object.entries(segment.routes).map(([mode, route]) => route.available && <button key={mode} onClick={() => window.location.assign(mapRouteUrl(mapApp, segment.to, mode))}>{({ walk: "步行", bike: "骑行", drive: "驾车", transit: "公交" } as Record<string, string>)[mode] ?? mode}<small>{route.duration_min ?? "?"} 分钟 · {route.distance_m ?? "?"} 米</small></button>)}</div></div>}</div>; })}{!currentDay.length && <button className="secondary-button full-button" onClick={() => onAddActivity(selectedDay)}>为这一天添加活动</button>}</div></section>
    </div>}
  </div>;
}
