import { useEffect, useRef, useState } from "react";
import type { Activity } from "../types";

type AMapInstance = { add: (items: unknown[]) => void; remove: (items: unknown[]) => void; setFitView: (items?: unknown[], immediately?: boolean, avoid?: number[]) => void; destroy: () => void };
type AMapNamespace = {
  Map: new (element: HTMLElement, options: Record<string, unknown>) => AMapInstance;
  Marker: new (options: Record<string, unknown>) => { on: (event: string, handler: () => void) => void };
  Polyline: new (options: Record<string, unknown>) => unknown;
};

export type MapRouteSegment = {
  fromId: number;
  toId: number;
  fromPosition?: [number, number];
  toPosition?: [number, number];
  path?: [number, number][];
};

declare global {
  interface Window {
    AMap?: AMapNamespace;
    _AMapSecurityConfig?: { securityJsCode: string };
  }
}

let loader: Promise<AMapNamespace> | null = null;

function loadAmap() {
  if (window.AMap) return Promise.resolve(window.AMap);
  if (loader) return loader;
  const key = import.meta.env.VITE_AMAP_JS_KEY as string | undefined;
  const securityJsCode = import.meta.env.VITE_AMAP_SECURITY_CODE as string | undefined;
  if (!key) return Promise.reject(new Error("缺少 VITE_AMAP_JS_KEY"));
  if (securityJsCode) window._AMapSecurityConfig = { securityJsCode };
  loader = new Promise((resolve, reject) => {
    const callback = `initXingBanAmap${Date.now()}`;
    const callbackWindow = window as unknown as Record<string, unknown>;
    callbackWindow[callback] = () => {
      delete callbackWindow[callback];
      if (window.AMap) resolve(window.AMap);
      else reject(new Error("高德地图 JS API 未正确加载"));
    };
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}&callback=${callback}`;
    script.async = true;
    script.onerror = () => reject(new Error("高德地图 JS API 加载失败"));
    document.head.appendChild(script);
  });
  return loader;
}

export function AmapTripMap({
  activities,
  routeSegments,
  selectedActivityId,
  onSelect,
}: {
  activities: Activity[];
  routeSegments: MapRouteSegment[];
  selectedActivityId: number | null;
  onSelect: (activity: Activity) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<AMapInstance | null>(null);
  const overlaysRef = useRef<unknown[]>([]);
  const onSelectRef = useRef(onSelect);
  const [error, setError] = useState("");

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    let cancelled = false;
    void loadAmap().then((AMap) => {
      if (cancelled || !containerRef.current) return;
      if (!mapRef.current) mapRef.current = new AMap.Map(containerRef.current, { zoom: 12, viewMode: "2D", mapStyle: "amap://styles/normal" });
      const map = mapRef.current;
      const located = activities.filter((item) => item.latitude != null && item.longitude != null);
      const markers = located.map((activity, index) => {
        const marker = new AMap.Marker({
          position: [activity.longitude, activity.latitude],
          title: activity.title,
          zIndex: selectedActivityId === activity.id ? 160 : 100,
          label: { direction: "top", content: `<span class="amap-order-label">${index + 1} · ${activity.title}</span>` },
        });
        marker.on("click", () => onSelectRef.current(activity));
        return marker;
      });
      const locatedById = new Map(located.map((activity) => [activity.id, activity]));
      const routeLines = routeSegments.flatMap((segment) => {
        const from = locatedById.get(segment.fromId);
        const to = locatedById.get(segment.toId);
        const fromPosition = from
          ? [from.longitude, from.latitude] as [number, number]
          : segment.fromPosition;
        const toPosition = to
          ? [to.longitude, to.latitude] as [number, number]
          : segment.toPosition;
        if (!fromPosition || !toPosition) return [];
        const hasActualRoute = Boolean(segment.path && segment.path.length > 1);
        const path = hasActualRoute
          ? segment.path
          : [fromPosition, toPosition];
        return [
          new AMap.Polyline({
            path,
            strokeColor: hasActualRoute ? "#34745b" : "#89aa9d",
            strokeWeight: hasActualRoute ? 6 : 4,
            strokeOpacity: hasActualRoute ? 0.9 : 0.68,
            strokeStyle: hasActualRoute ? "solid" : "dashed",
            showDir: hasActualRoute,
            zIndex: 80,
          }),
        ];
      });
      const overlays: unknown[] = [...routeLines, ...markers];
      map.add(overlays);
      if (overlaysRef.current.length) map.remove(overlaysRef.current);
      overlaysRef.current = overlays;
      if (overlays.length) map.setFitView(overlays, false, [70, 70, 70, 70]);
      setError("");
    }).catch((reason: Error) => setError(reason.message));
    return () => { cancelled = true; };
  }, [activities, routeSegments, selectedActivityId]);

  useEffect(() => () => { overlaysRef.current = []; mapRef.current?.destroy(); mapRef.current = null; }, []);

  return <div className="amap-stage"><div className="amap-canvas" ref={containerRef} />{error && <div className="map-setup-message"><strong>地图尚未完成配置</strong><span>{error}</span><small>在 frontend/.env.local 中填写高德 JS API Key 后即可显示真实地图。</small></div>}</div>;
}
