import {
  Bike,
  BusFront,
  CalendarPlus,
  Camera,
  Car,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  CloudSun,
  Footprints,
  GripVertical,
  MapPinned,
  MapPin,
  Navigation,
  Pencil,
  Plus,
  Receipt,
  Route,
  Settings,
  Sparkles,
  Trash2,
  UsersRound,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ApiPoi, type ApiWeather } from "../api/client";
import { AmapTripMap, type MapRouteSegment } from "../components/AmapTripMap";
import { ModalSheet } from "../components/ModalSheet";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";
import type { Activity, Workspace } from "../types";

type MapApp = "amap" | "baidu" | "tencent" | "apple";
type RouteMode = "walk" | "bike" | "drive" | "transit";
type RouteChoice = {
  available?: boolean;
  distance_m?: number;
  duration_min?: number;
  path?: [number, number][];
};
type Segment = {
  from: Activity;
  to: Activity;
  routes: Record<string, RouteChoice>;
  isDayStart?: boolean;
  loading?: boolean;
  error?: string;
};
type DayContext = {
  segments: Segment[];
  weather: ApiWeather | null;
  poi: ApiPoi | null;
  activityPois: Record<number, ApiPoi>;
  loading: boolean;
  loaded: boolean;
  error: string;
};
type NavigationTarget = { activity: Activity; mode: RouteMode };

const ROUTE_MODES: RouteMode[] = ["walk", "bike", "drive", "transit"];
const ROUTE_LABELS: Record<RouteMode, string> = {
  walk: "步行",
  bike: "骑行",
  drive: "驾车",
  transit: "公共交通",
};
const MAP_APPS: { id: MapApp; name: string; description: string }[] = [
  { id: "amap", name: "高德地图", description: "使用高德地图导航" },
  { id: "baidu", name: "百度地图", description: "需已安装百度地图" },
  { id: "tencent", name: "腾讯地图", description: "使用腾讯地图路线页" },
  { id: "apple", name: "Apple 地图", description: "适用于 Apple 设备" },
];

const JOURNEY_ROLE_LABELS: Partial<Record<NonNullable<Activity["journeyRole"]>, string>> = {
  outbound: "去程",
  return: "返程",
  intercity_transfer: "城市间转移",
};
const TRANSPORT_MODE_LABELS: Partial<Record<NonNullable<Activity["transportMode"]>, string>> = {
  flight: "飞机",
  high_speed_rail: "高铁",
  rail: "普通列车",
};

function formatDay(date: string) {
  const value = new Date(`${date}T00:00:00`);
  return Number.isNaN(value.getTime())
    ? date
    : new Intl.DateTimeFormat("zh-CN", {
        month: "numeric",
        day: "numeric",
        weekday: "short",
      }).format(value);
}

function formatQueryTime(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
}

function formatDuration(value?: number) {
  if (value == null) return "时间待查询";
  if (value < 60) return `${value}分钟`;
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  return minutes ? `${hours}小时${minutes}分钟` : `${hours}小时`;
}

function formatDistance(value?: number) {
  if (value == null) return "距离待查询";
  if (value < 1000) return `${Math.round(value)}米`;
  return `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)}公里`;
}

function routeIcon(mode: RouteMode, size = 18) {
  if (mode === "walk") return <Footprints size={size} />;
  if (mode === "bike") return <Bike size={size} />;
  if (mode === "drive") return <Car size={size} />;
  return <BusFront size={size} />;
}

function segmentKey(segment: Segment) {
  return `${segment.from.id}-${segment.to.id}`;
}

function sameActivityLocation(first: Activity, second: Activity) {
  if (
    first.latitude != null &&
    first.longitude != null &&
    second.latitude != null &&
    second.longitude != null
  ) {
    return (
      Math.abs(first.latitude - second.latitude) < 0.0001 &&
      Math.abs(first.longitude - second.longitude) < 0.0001
    );
  }
  return first.location.trim() === second.location.trim();
}

function overnightHotel(activities: Activity[]) {
  const reversed = [...activities].reverse();
  return (
    reversed.find((activity) => activity.type === "hotel") ??
    reversed.find((activity) => /酒店|住宿|民宿|客栈/.test(`${activity.title}${activity.location}`))
  );
}

function recommendedMode(segment: Segment): RouteMode | null {
  const available = ROUTE_MODES.filter((mode) => segment.routes[mode]?.available);
  if (!available.length) return null;
  const walking = segment.routes.walk;
  if (walking?.available && (walking.distance_m ?? Number.POSITIVE_INFINITY) <= 1600) {
    return "walk";
  }
  const cycling = segment.routes.bike;
  if (cycling?.available && (cycling.distance_m ?? Number.POSITIVE_INFINITY) <= 6000) {
    return "bike";
  }
  return available.sort(
    (first, second) =>
      (segment.routes[first]?.duration_min ?? Number.POSITIVE_INFINITY) -
      (segment.routes[second]?.duration_min ?? Number.POSITIVE_INFINITY),
  )[0];
}

function mapRouteUrl(app: MapApp, activity: Activity, mode: RouteMode): string | null {
  const { latitude: lat, longitude: lng } = activity;
  const locationName = activity.location || activity.title;
  if (app === "baidu") {
    const baiduMode =
      mode === "drive"
        ? "driving"
        : mode === "transit"
          ? "transit"
          : mode === "bike"
            ? "riding"
            : "walking";
    const params = new URLSearchParams({
      origin: "我的位置",
      destination: lat == null || lng == null
        ? locationName
        : `name:${locationName}|latlng:${lat},${lng}`,
      mode: baiduMode,
      coord_type: "gcj02",
      src: "webapp.xingban",
    });
    return `baidumap://map/direction?${params.toString()}`;
  }
  if (app === "tencent") {
    // Tencent's public URI route planner currently documents bus, drive and
    // walk only. Do not silently turn a cycling request into another mode.
    if (mode === "bike") return null;
    const tencentMode = mode === "drive" ? "drive" : mode === "transit" ? "bus" : mode;
    const params = new URLSearchParams({
      type: tencentMode,
      to: locationName,
      coord_type: "2",
      referer: "xingban",
    });
    if (lat != null && lng != null) params.set("tocoord", `${lat},${lng}`);
    return `https://apis.map.qq.com/uri/v1/routeplan?${params.toString()}`;
  }
  if (app === "apple") {
    const appleMode = mode === "walk"
      ? "walking"
      : mode === "transit"
        ? "transit"
        : mode === "bike"
          ? "cycling"
          : "driving";
    // AMap coordinates are GCJ-02 while Apple unified URLs expect their own
    // location resolution. Use the verified POI name to avoid coordinate drift.
    const params = new URLSearchParams({ destination: locationName, mode: appleMode });
    return `https://maps.apple.com/directions?${params.toString()}`;
  }
  const name = encodeURIComponent(locationName);
  if (lat == null || lng == null) {
    return `https://uri.amap.com/search?keyword=${name}&src=xingban`;
  }
  const amapMode =
    mode === "drive" ? "car" : mode === "transit" ? "bus" : mode === "bike" ? "ride" : "walk";
  return `https://uri.amap.com/navigation?to=${lng},${lat},${name}&mode=${amapMode}&policy=1&src=xingban&coordinate=gaode&callnative=1`;
}

function downloadCalendar(workspace: Workspace, activities: Activity[]) {
  const pad = (value: number) => String(value).padStart(2, "0");
  const escape = (value: string) =>
    value.replace(/\\/g, "\\\\").replace(/,/g, "\\,").replace(/;/g, "\\;").replace(/\n/g, "\\n");
  const events = activities.map((activity) => {
    const start = new Date(
      `${activity.date}T${activity.time === "待定" ? "09:00" : activity.time}:00`,
    );
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    const stamp = (date: Date) =>
      `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}T${pad(date.getHours())}${pad(date.getMinutes())}00`;
    return [
      "BEGIN:VEVENT",
      `UID:xingban-${workspace.tripId}-${activity.id}@local`,
      `DTSTART:${stamp(start)}`,
      `DTEND:${stamp(end)}`,
      `SUMMARY:${escape(activity.title)}`,
      `LOCATION:${escape(activity.location)}`,
      `DESCRIPTION:${escape(activity.detail)}`,
      "END:VEVENT",
    ].join("\r\n");
  });
  const content = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//行伴//Travel Itinerary//CN",
    "CALSCALE:GREGORIAN",
    ...events,
    "END:VCALENDAR",
  ].join("\r\n");
  const url = URL.createObjectURL(
    new Blob([content], { type: "text/calendar;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `${workspace.title}.ics`;
  link.click();
  URL.revokeObjectURL(url);
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
  onReorderActivities,
  canEditItinerary,
  onInviteMember,
  onChangeMemberRole,
  currentUserId,
  canManageMembers,
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
  onReorderActivities: (dayNumber: number, activityIds: number[]) => Promise<void>;
  canEditItinerary: boolean;
  onInviteMember: () => void;
  onChangeMemberRole: (memberId: number, role: "editor" | "viewer") => Promise<void>;
  currentUserId: number | null;
  canManageMembers: boolean;
  onBack: () => void;
  onSettings: () => void;
}) {
  const days = useMemo(
    () =>
      Array.from(
        new Map(workspace.activities.map((activity) => [activity.day, activity.date])).entries(),
      ).sort(([first], [second]) => first - second),
    [workspace.activities],
  );
  const [selectedDay, setSelectedDay] = useState(days[0]?.[0] ?? 1);
  const [selectedActivityId, setSelectedActivityId] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [dayContexts, setDayContexts] = useState<Record<number, DayContext>>({});
  const [activeSegment, setActiveSegment] = useState<Segment | null>(null);
  const [routeSelections, setRouteSelections] = useState<Record<string, RouteMode>>({});
  const [navigationTarget, setNavigationTarget] = useState<NavigationTarget | null>(null);
  const [permissionMember, setPermissionMember] = useState<(typeof workspace.members)[number] | null>(null);
  const [permissionSaving, setPermissionSaving] = useState(false);
  const [draggedActivityId, setDraggedActivityId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<{ id: number; position: "before" | "after" } | null>(null);
  const routeLoadVersionRef = useRef(0);
  const routeLoadKeyRef = useRef("");
  const loadingDaysRef = useRef(new Set<number>());
  const loadedDaysRef = useRef(new Set<number>());

  const currentDay = useMemo(
    () =>
      workspace.activities
        .filter((activity) => activity.day === selectedDay)
        .sort((first, second) => first.order - second.order),
    [workspace.activities, selectedDay],
  );
  const estimatedTripCost = useMemo(
    () =>
      workspace.activities.reduce(
        (total, activity) => total + (activity.estimatedPrice ?? 0),
        0,
      ),
    [workspace.activities],
  );
  const hasEstimatedTripCost = workspace.activities.some(
    (activity) => activity.estimatedPrice != null,
  );
  useEffect(() => {
    setSelectedDay(days[0]?.[0] ?? 1);
    setSelectedActivityId(null);
    setActiveSegment(null);
    setNavigationTarget(null);
  }, [workspace.tripId, days]);

  useEffect(() => {
    const loadKey = `${workspace.tripId}:${workspace.version}`;
    if (routeLoadKeyRef.current !== loadKey) {
      routeLoadKeyRef.current = loadKey;
      routeLoadVersionRef.current += 1;
      loadingDaysRef.current.clear();
      loadedDaysRef.current.clear();
      setDayContexts({});
      setActiveSegment(null);
      setRouteSelections({});
    }
    const loadVersion = routeLoadVersionRef.current;
    if (
      loadingDaysRef.current.has(selectedDay) ||
      loadedDaysRef.current.has(selectedDay)
    ) return;

    const activitiesByDay = new Map(
      days.map(([day]) => [
        day,
        workspace.activities
          .filter((activity) => activity.day === day)
          .sort((first, second) => first.order - second.order),
      ]),
    );
    const dayStartHotels = new Map<number, Activity>();
    let latestHotel: Activity | undefined;
    for (const [day] of days) {
      if (latestHotel) dayStartHotels.set(day, latestHotel);
      latestHotel = overnightHotel(activitiesByDay.get(day) ?? []) ?? latestHotel;
    }
    const activities = activitiesByDay.get(selectedDay) ?? [];
    const pendingSegments: Segment[] = activities.slice(0, -1).map((from, index) => ({
      from,
      to: activities[index + 1],
      routes: {},
      loading: true,
    }));
    const hotel = dayStartHotels.get(selectedDay);
    const first = activities[0];
    if (hotel && first && !sameActivityLocation(hotel, first)) {
      pendingSegments.unshift({
        from: hotel,
        to: first,
        routes: {},
        isDayStart: true,
        loading: true,
      });
    }
    const initialContext: DayContext = {
      segments: pendingSegments,
      weather: null,
      poi: null,
      activityPois: {},
      loading: Boolean(activities.length),
      loaded: !activities.length,
      error: "",
    };
    setDayContexts((current) => ({ ...current, [selectedDay]: initialContext }));
    if (!activities.length) {
      loadedDaysRef.current.add(selectedDay);
      return;
    }
    loadingDaysRef.current.add(selectedDay);

    const updateDay = (day: number, update: Partial<DayContext>) => {
      if (routeLoadVersionRef.current !== loadVersion) return;
      setDayContexts((current) => ({
        ...current,
        [day]: { ...current[day], ...update },
      }));
    };

    const loadDay = async (day: number, date: string) => {
      const first = activities[0];
      const [weatherResult, poiResult] = await Promise.allSettled([
        api.weather(workspace.city, date),
        first.location
          ? api.map.poi(workspace.city, first.location)
          : Promise.resolve({ items: [] as ApiPoi[], provider: "amap", queried_at: "" }),
      ]);
      const weather = weatherResult.status === "fulfilled" ? weatherResult.value : null;
      const poi = poiResult.status === "fulfilled" ? poiResult.value.items[0] ?? null : null;
      const cityCode = poi?.adcode ?? undefined;
      const errors: string[] = [];
      if (weatherResult.status === "rejected") errors.push("天气查询失败");
      if (poiResult.status === "rejected") errors.push("地点信息查询失败");
      updateDay(day, { weather, poi });

      const nextSegments: Segment[] = [];
      for (const pending of pendingSegments) {
        const { from, to } = pending;
        if (
          from.latitude == null ||
          from.longitude == null ||
          to.latitude == null ||
          to.longitude == null
        ) {
          nextSegments.push({ ...pending, loading: false, error: "地点缺少坐标" });
          errors.push(`${from.title}到${to.title}缺少坐标`);
        } else {
          try {
            const result = await api.map.route(
              from.latitude,
              from.longitude,
              to.latitude,
              to.longitude,
              cityCode,
            );
            nextSegments.push({
              ...pending,
              routes: (result.routes ?? {}) as Record<string, RouteChoice>,
              loading: false,
            });
          } catch (error) {
            nextSegments.push({
              from,
              to,
              routes: {},
              loading: false,
              error: (error as Error).message,
            });
            errors.push(`${from.title}到${to.title}路线查询失败`);
          }
        }
        updateDay(day, {
          segments: [...nextSegments, ...pendingSegments.slice(nextSegments.length)],
        });
      }
      updateDay(day, {
        segments: nextSegments,
        loading: false,
        loaded: true,
        error: errors.join("；"),
      });
      const poiActivities = activities.filter(
        (activity) =>
          (activity.type === "sight" || activity.type === "food") &&
          !activity.openHours &&
          activity.location &&
          activity.location !== "地点待定",
      );
      if (poiActivities.length) {
        const metadataResults = await Promise.allSettled(
          poiActivities.map((activity) => api.map.poi(workspace.city, activity.location)),
        );
        const activityPois: Record<number, ApiPoi> = {};
        metadataResults.forEach((result, index) => {
          if (result.status !== "fulfilled") return;
          const activity = poiActivities[index];
          const matched =
            result.value.items.find((item) => item.poi_id === activity.poiId) ??
            result.value.items.find((item) => item.name === activity.location) ??
            result.value.items[0];
          if (matched) activityPois[activity.id] = matched;
        });
        updateDay(day, { activityPois });
      }
      if (routeLoadVersionRef.current === loadVersion) {
        loadedDaysRef.current.add(day);
      }
    };

    const selectedDate = days.find(([day]) => day === selectedDay)?.[1] ?? "";
    void loadDay(selectedDay, selectedDate).finally(() => {
      if (routeLoadVersionRef.current === loadVersion) {
        loadingDaysRef.current.delete(selectedDay);
      }
    });
  }, [days, selectedDay, workspace.activities, workspace.city, workspace.tripId, workspace.version]);

  const selectedContext = dayContexts[selectedDay];
  const segments = selectedContext?.segments ?? [];
  const weather = selectedContext?.weather ?? null;
  const poi = selectedContext?.poi ?? null;
  const externalLoading = selectedContext?.loading ?? false;
  const externalError = selectedContext?.error ?? "";
  const dayStartFallback = useMemo<Segment | undefined>(() => {
    const previousDays = days
      .filter(([day]) => day < selectedDay)
      .sort(([first], [second]) => second - first);
    const previousHotel = previousDays
      .map(([day]) =>
        overnightHotel(
          workspace.activities
            .filter((activity) => activity.day === day)
            .sort((first, second) => first.order - second.order),
        ),
      )
      .find((activity): activity is Activity => Boolean(activity));
    const first = currentDay[0];
    if (!previousHotel || !first || sameActivityLocation(previousHotel, first)) return undefined;
    return {
      from: previousHotel,
      to: first,
      routes: {},
      isDayStart: true,
      loading: true,
    };
  }, [currentDay, days, selectedDay, workspace.activities]);
  const dayStartSegment =
    segments.find((segment) => segment.isDayStart) ?? dayStartFallback;

  const selectedActivity =
    currentDay.find((item) => item.id === selectedActivityId) ?? currentDay[0];
  const activeSegmentMode = activeSegment
    ? routeSelections[segmentKey(activeSegment)] ?? recommendedMode(activeSegment)
    : null;
  const mapRouteSegments = useMemo<MapRouteSegment[]>(
    () =>
      segments.map((segment) => {
        const mode = routeSelections[segmentKey(segment)] ?? recommendedMode(segment);
        return {
          fromId: segment.from.id,
          toId: segment.to.id,
          fromPosition:
            segment.from.longitude != null && segment.from.latitude != null
              ? [segment.from.longitude, segment.from.latitude]
              : undefined,
          toPosition:
            segment.to.longitude != null && segment.to.latitude != null
              ? [segment.to.longitude, segment.to.latitude]
              : undefined,
          path: mode ? segment.routes[mode]?.path : undefined,
        };
      }),
    [routeSelections, segments],
  );

  useEffect(() => {
    if (!activeSegment) return;
    const updated = segments.find((segment) => segmentKey(segment) === segmentKey(activeSegment));
    if (updated && updated !== activeSegment) setActiveSegment(updated);
  }, [activeSegment, segments]);

  const chooseRouteMode = (segment: Segment, mode: RouteMode) => {
    if (!segment.routes[mode]?.available) return;
    setRouteSelections((current) => ({ ...current, [segmentKey(segment)]: mode }));
  };

  const beginNavigation = (activity: Activity, mode: RouteMode) => {
    setActiveSegment(null);
    setNavigationTarget({ activity, mode });
  };
  const changeMemberRole = async (role: "editor" | "viewer") => {
    if (!permissionMember) return;
    setPermissionSaving(true);
    try {
      await onChangeMemberRole(permissionMember.id, role);
      setPermissionMember(null);
    } catch {
      // 父组件负责显示具体接口错误；保留弹窗便于重试。
    } finally {
      setPermissionSaving(false);
    }
  };
  const dropActivity = async (targetId: number) => {
    if (draggedActivityId == null || draggedActivityId === targetId || !dropTarget) return;
    const remainingIds = currentDay
      .map((activity) => activity.id)
      .filter((activityId) => activityId !== draggedActivityId);
    const targetIndex = remainingIds.indexOf(targetId);
    if (targetIndex < 0) return;
    const insertIndex = targetIndex + (dropTarget.position === "after" ? 1 : 0);
    remainingIds.splice(insertIndex, 0, draggedActivityId);
    setDraggedActivityId(null);
    setDropTarget(null);
    try {
      await onReorderActivities(selectedDay, remainingIds);
    } catch {
      // 父组件负责展示接口错误或版本冲突处理。
    }
  };
  const handleSelectActivity = useCallback((activity: Activity) => {
    setSelectedActivityId(activity.id);
  }, []);

  const renderTransportSummary = (segment: Segment) => {
    const selectedMode = routeSelections[segmentKey(segment)] ?? recommendedMode(segment);
    const selectedRoute = selectedMode ? segment.routes[selectedMode] : undefined;
    return (
      <button
        className={`transport-summary-button ${segment.isDayStart ? "is-day-start" : ""}`}
        onClick={() => setActiveSegment(segment)}
      >
        <span className="transport-summary-icon">
          {selectedMode ? routeIcon(selectedMode, 16) : <Route size={16} />}
        </span>
        <span>
          <strong>
            {segment.isDayStart ? "从昨晚酒店出发 · " : ""}
            {selectedMode ? ROUTE_LABELS[selectedMode] : "查看交通方式"}
          </strong>
          <small>
            {selectedRoute?.available
              ? `${formatDuration(selectedRoute.duration_min)} · ${formatDistance(selectedRoute.distance_m)}`
              : segment.loading
                ? "正在查询四种交通方式…"
                : segment.error
                  ? "路线暂不可用，点击查看"
                  : "查看四种交通方式"}
          </small>
        </span>
        <ChevronRight size={16} />
      </button>
    );
  };

  return (
    <div className="page page-world workbench-page">
      <StatusBar />
      <PageHeader
        title="行程"
        subtitle={`${workspace.title} · 第 ${workspace.version} 版`}
        onBack={onBack}
        action={
          <div className="header-actions">
            <button
              className="action-pill"
              onClick={workspace.activities.length ? onRevise : onGenerate}
            >
              {workspace.activities.length ? "整体调整" : "Agent 生成"}
            </button>
            <button
              className="icon-button header-settings-button"
              onClick={onSettings}
              aria-label="行程设置"
            >
              <Settings size={19} />
            </button>
          </div>
        }
      />
      {!workspace.activities.length ? (
        <section className="itinerary-empty">
          <Sparkles size={30} />
          <h2>还没有生成行程</h2>
          <p>让 Agent 根据目的地、日期、预算和成员需求生成第一版行程。</p>
          <button className="primary-button" onClick={onGenerate}>
            开始生成行程
          </button>
        </section>
      ) : (
        <div className="trip-workbench">
          <aside className="workbench-meta-panel">
            <div>
              <small>本次旅行</small>
              <h2>{workspace.title}</h2>
              <p>
                {workspace.city} · {workspace.startDate}—{workspace.endDate}
              </p>
            </div>
            <div className="workbench-stat">
              <UsersRound size={17} />
              <span>{workspace.travelerCount} 人同行</span>
            </div>
            <div className="workbench-stat">
              <Route size={17} />
              <span>{workspace.activities.length} 项活动</span>
            </div>
            <div className="workbench-stat">
              <CircleDollarSign size={17} />
              <span>
                {hasEstimatedTripCost
                  ? `预计花销 ¥${estimatedTripCost.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`
                  : "暂无预计花销"}
              </span>
            </div>
            <section>
              <small>同行成员</small>
              <div className="workbench-members">
                {workspace.members.map((member) => {
                  const canEdit = canManageMembers && member.id !== currentUserId && member.permission !== "owner";
                  return (
                    <button
                      className={`workbench-member ${canEdit ? "is-manageable" : ""}`}
                      title={canEdit ? `修改 ${member.name} 的权限` : `${member.name} · ${member.role ?? "成员"}`}
                      onClick={() => canEdit && setPermissionMember(member)}
                      key={member.id}
                      type="button"
                    >
                      <span className="workbench-member-avatar">
                        {member.avatar ? <img src={member.avatar} alt="" /> : member.name.slice(0, 1)}
                      </span>
                      <strong>{member.name}</strong>
                      <small>{member.role ?? "成员"}</small>
                    </button>
                  );
                })}
                {canManageMembers && (
                  <button
                    className="workbench-member workbench-member-add"
                    onClick={onInviteMember}
                    title="添加同行成员"
                    type="button"
                  >
                    <span className="workbench-member-avatar"><Plus size={20} /></span>
                    <strong>添加成员</strong>
                    <small>邀请加入</small>
                  </button>
                )}
              </div>
            </section>
            <button
              className="secondary-button workbench-side-action"
              onClick={() => selectedActivity && beginNavigation(selectedActivity, "drive")}
              disabled={!selectedActivity}
            >
              <Navigation size={16} />导航到当前地点
            </button>
            <button
              className="secondary-button workbench-side-action"
              onClick={() => downloadCalendar(workspace, workspace.activities)}
            >
              <CalendarPlus size={16} />导出日历 .ics
            </button>
            <button className="text-button" onClick={onOpenVersions}>
              查看第 {workspace.version} 版修改记录
            </button>
          </aside>
          <main className="workbench-map-panel">
            <AmapTripMap
              activities={currentDay}
              routeSegments={mapRouteSegments}
              selectedActivityId={selectedActivityId}
              onSelect={handleSelectActivity}
            />
            <div className="map-context-strip">
              {weather ? (
                <>
                  <CloudSun size={17} />
                  <strong>{weather.condition_day ?? "天气未知"}</strong>
                  <span>
                    {weather.temperature_min ?? "?"}—{weather.temperature_max ?? "?"}℃ · 降水{" "}
                    {weather.precipitation_probability ?? "?"}%
                  </span>
                </>
              ) : (
                <span>{externalLoading ? "正在查询天气与路线…" : "暂无天气信息"}</span>
              )}
              {poi && (
                <small>
                  高德 POI · {poi.name}
                  {poi.open_hours ? ` · 营业 ${poi.open_hours}` : ""}
                  {poi.average_cost != null ? ` · 参考人均 ¥${poi.average_cost}` : ""}
                </small>
              )}
              {externalError && <small className="inline-error">{externalError}</small>}
            </div>
          </main>
          <section
            className={`workbench-itinerary-panel ${drawerOpen ? "is-open" : "is-collapsed"}`}
          >
            <button
              className="mobile-drawer-handle"
              onClick={() => setDrawerOpen((value) => !value)}
              aria-label={drawerOpen ? "收起日程" : "展开日程"}
            >
              <i />
            </button>
            <div className="date-tabs dynamic-date-tabs">
              {days.map(([day, date]) => (
                <button
                  key={day}
                  className={day === selectedDay ? "is-active" : ""}
                  onClick={() => {
                    setSelectedDay(day);
                    setSelectedActivityId(null);
                    setActiveSegment(null);
                  }}
                >
                  {formatDay(date)}
                </button>
              ))}
            </div>
            <div className="schedule-title workbench-schedule-title">
              <strong>第 {selectedDay} 天</strong>
              <span>{currentDay.length} 项活动</span>
              <button className="inline-action" onClick={() => onAddActivity(selectedDay)}>
                <Plus size={14} />新增
              </button>
            </div>
            <div className="workbench-activity-list">
              {dayStartSegment && renderTransportSummary(dayStartSegment)}
              {currentDay.map((activity) => {
                const segment = segments.find(
                  (item) => !item.isDayStart && item.from.id === activity.id,
                );
                const priceLabel =
                  activity.actualPrice != null
                    ? activity.priceSource === "amap"
                      ? `高德人均参考 ¥${activity.actualPrice}${activity.priceQueriedAt ? ` · ${formatQueryTime(activity.priceQueriedAt)}查询` : ""}`
                      : `人工记录 ¥${activity.actualPrice}`
                    : activity.estimatedPrice != null
                      ? `AI 估算 ¥${activity.estimatedPrice}`
                      : "暂无价格";
                const livePoi = selectedContext?.activityPois[activity.id];
                const openHours = activity.openHours ?? livePoi?.open_hours;
                const openHoursSource = activity.openHoursSource ?? (livePoi ? "高德" : undefined);
                const showsAccommodationBasis =
                  activity.type === "hotel" &&
                  (activity.estimatedPrice ?? 0) > 0 &&
                  /入住|办理入住|住宿/.test(activity.title);
                return (
                  <div key={activity.id} className="activity-and-transfer">
                    <article
                      className={`workbench-activity-card ${selectedActivityId === activity.id ? "is-selected" : ""} ${draggedActivityId === activity.id ? "is-dragging" : ""} ${dropTarget?.id === activity.id ? `is-drop-${dropTarget.position}` : ""}`}
                      onClick={() => setSelectedActivityId(activity.id)}
                      onDragOver={(event) => {
                        if (draggedActivityId == null || draggedActivityId === activity.id) return;
                        event.preventDefault();
                        const bounds = event.currentTarget.getBoundingClientRect();
                        setDropTarget({
                          id: activity.id,
                          position: event.clientY < bounds.top + bounds.height / 2 ? "before" : "after",
                        });
                      }}
                      onDrop={(event) => {
                        event.preventDefault();
                        void dropActivity(activity.id);
                      }}
                    >
                      {canEditItinerary && (
                        <button
                          className="activity-drag-handle"
                          type="button"
                          draggable
                          aria-label={`拖动调整“${activity.title}”的顺序`}
                          title="拖动调整顺序"
                          onClick={(event) => event.stopPropagation()}
                          onDragStart={(event) => {
                            event.stopPropagation();
                            event.dataTransfer.effectAllowed = "move";
                            event.dataTransfer.setData("text/plain", String(activity.id));
                            setDraggedActivityId(activity.id);
                            setDropTarget(null);
                          }}
                          onDragEnd={() => {
                            setDraggedActivityId(null);
                            setDropTarget(null);
                          }}
                        >
                          <GripVertical size={17} />
                        </button>
                      )}
                      <time className="activity-time-range">
                        <span>{activity.time}</span>
                        {activity.endTime !== "待定" && (
                          <>
                            <i aria-hidden="true" />
                            <span>{activity.endTime}</span>
                          </>
                        )}
                      </time>
                      <div>
                        <strong>{activity.title}</strong>
                        <p>
                          <MapPin size={12} />
                          {activity.location}
                          {activity.type === "sight" || activity.type === "food"
                            ? openHours
                              ? ` · 营业 ${openHours}${openHoursSource ? `（${openHoursSource}）` : ""}`
                              : ""
                            : ""}
                        </p>
                        <small>{priceLabel}</small>
                        {showsAccommodationBasis && (
                          <small className="source-note">
                            按 2 人/间折算
                          </small>
                        )}
                        {activity.journeyRole && JOURNEY_ROLE_LABELS[activity.journeyRole] && (
                          <small className="source-note">
                            {JOURNEY_ROLE_LABELS[activity.journeyRole]}
                            {activity.transportMode && TRANSPORT_MODE_LABELS[activity.transportMode]
                              ? ` · ${TRANSPORT_MODE_LABELS[activity.transportMode]}`
                              : ""}
                            {activity.transportService ? ` · ${activity.transportService}` : " · 待确认班次"}
                          </small>
                        )}
                        {activity.quotedPriceNote && (
                          <small className="source-note">{activity.quotedPriceNote}</small>
                        )}
                        <div className="activity-actions">
                          <button onClick={(event) => { event.stopPropagation(); onEditActivity(activity); }}>
                            <Pencil size={13} />编辑
                          </button>
                          <button onClick={(event) => { event.stopPropagation(); onReplan(activity); }}>
                            <Sparkles size={13} />重排
                          </button>
                          <button onClick={(event) => { event.stopPropagation(); onAddExpense(activity); }}>
                            <Receipt size={13} />记账
                          </button>
                          <button onClick={(event) => { event.stopPropagation(); onAddRecord(activity); }}>
                            <Camera size={13} />记录
                          </button>
                          <button className="danger-inline" onClick={(event) => { event.stopPropagation(); onDeleteActivity(activity); }}>
                            <Trash2 size={13} />删除
                          </button>
                        </div>
                      </div>
                    </article>
                    {segment && renderTransportSummary(segment)}
                  </div>
                );
              })}
              {!currentDay.length && (
                <button className="secondary-button full-button" onClick={() => onAddActivity(selectedDay)}>
                  为这一天添加活动
                </button>
              )}
            </div>
          </section>
        </div>
      )}
      {permissionMember && (
        <ModalSheet title="修改成员权限" onClose={() => !permissionSaving && setPermissionMember(null)}>
          <div className="member-permission-profile">
            <span className="workbench-member-avatar">
              {permissionMember.avatar ? <img src={permissionMember.avatar} alt="" /> : permissionMember.name.slice(0, 1)}
            </span>
            <div><strong>{permissionMember.name}</strong><small>当前权限：{permissionMember.role}</small></div>
          </div>
          <div className="member-permission-options">
            <button className={permissionMember.permission === "editor" ? "is-active" : ""} disabled={permissionSaving} onClick={() => void changeMemberRole("editor")}>
              <strong>可编辑</strong><small>可以编辑行程、使用 Agent 调整和添加内容</small>
            </button>
            <button className={permissionMember.permission === "viewer" ? "is-active" : ""} disabled={permissionSaving} onClick={() => void changeMemberRole("viewer")}>
              <strong>仅查看</strong><small>可以查看行程，但不能修改内容</small>
            </button>
          </div>
        </ModalSheet>
      )}

      {activeSegment && (
        <ModalSheet title="交通信息" onClose={() => setActiveSegment(null)}>
          <div className="transport-endpoints">
            <span>起</span><strong>{activeSegment.from.title}</strong>
            <span>终</span><strong>{activeSegment.to.title}</strong>
          </div>
          <div className="transport-mode-list">
            {ROUTE_MODES.map((mode) => {
              const route = activeSegment.routes[mode];
              const available = Boolean(route?.available);
              const selected = activeSegmentMode === mode;
              return (
                <button
                  key={mode}
                  className={`transport-mode-option ${selected ? "is-selected" : ""}`}
                  disabled={!available}
                  onClick={() => chooseRouteMode(activeSegment, mode)}
                >
                  {routeIcon(mode, 21)}
                  <strong>{ROUTE_LABELS[mode]}</strong>
                  <span>
                    {available
                      ? `${formatDistance(route.distance_m)} · ${formatDuration(route.duration_min)}`
                      : "暂无路线"}
                  </span>
                </button>
              );
            })}
          </div>
          <button
            className="primary-button full-button transport-navigate-button"
            disabled={!activeSegmentMode}
            onClick={() => activeSegmentMode && beginNavigation(activeSegment.to, activeSegmentMode)}
          >
            <Navigation size={18} />
            使用{activeSegmentMode ? ROUTE_LABELS[activeSegmentMode] : "所选方式"}导航
          </button>
        </ModalSheet>
      )}

      {navigationTarget && (
        <ModalSheet title="选择地图应用" onClose={() => setNavigationTarget(null)}>
          <button className="sheet-back-button" onClick={() => setNavigationTarget(null)}>
            <ChevronLeft size={16} />返回行程
          </button>
          <p className="sheet-intro">
            将使用{ROUTE_LABELS[navigationTarget.mode]}前往“{navigationTarget.activity.title}”。
          </p>
          <div className="map-app-list">
            {MAP_APPS.map((app) => {
              const routeUrl = mapRouteUrl(
                app.id,
                navigationTarget.activity,
                navigationTarget.mode,
              );
              return (
                <button
                  className="map-app-option"
                  disabled={!routeUrl}
                  key={app.id}
                  onClick={() => routeUrl && window.location.assign(routeUrl)}
                >
                  <span><MapPinned size={20} /></span>
                  <span>
                    <strong>{app.name}</strong>
                    <small>
                      {routeUrl ? app.description : "腾讯地图网页跳转暂不支持骑行路线"}
                    </small>
                  </span>
                  <ChevronRight size={18} />
                </button>
              );
            })}
          </div>
        </ModalSheet>
      )}
    </div>
  );
}
