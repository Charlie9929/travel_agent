import { useEffect, useRef, useState } from "react";
import type { Activity } from "../types";

type AMapInstance = { add: (items: unknown[]) => void; clearMap: () => void; setFitView: (items?: unknown[], immediately?: boolean, avoid?: number[]) => void; destroy: () => void };
type AMapNamespace = {
  Map: new (element: HTMLElement, options: Record<string, unknown>) => AMapInstance;
  Marker: new (options: Record<string, unknown>) => { on: (event: string, handler: () => void) => void };
  Polyline: new (options: Record<string, unknown>) => unknown;
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

export function AmapTripMap({ activities, selectedActivityId, onSelect }: { activities: Activity[]; selectedActivityId: number | null; onSelect: (activity: Activity) => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<AMapInstance | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void loadAmap().then((AMap) => {
      if (cancelled || !containerRef.current) return;
      if (!mapRef.current) mapRef.current = new AMap.Map(containerRef.current, { zoom: 12, viewMode: "2D", mapStyle: "amap://styles/whitesmoke" });
      const map = mapRef.current;
      map.clearMap();
      const located = activities.filter((item) => item.latitude != null && item.longitude != null);
      const markers = located.map((activity, index) => {
        const marker = new AMap.Marker({
          position: [activity.longitude, activity.latitude],
          title: activity.title,
          zIndex: selectedActivityId === activity.id ? 160 : 100,
          label: { direction: "top", content: `<span class="amap-order-label">${index + 1} · ${activity.title}</span>` },
        });
        marker.on("click", () => onSelect(activity));
        return marker;
      });
      const overlays: unknown[] = [...markers];
      if (located.length > 1) overlays.push(new AMap.Polyline({ path: located.map((item) => [item.longitude, item.latitude]), strokeColor: "#294c68", strokeWeight: 5, strokeOpacity: .82, showDir: true }));
      map.add(overlays);
      if (markers.length) map.setFitView(markers, false, [70, 70, 70, 70]);
      setError("");
    }).catch((reason: Error) => setError(reason.message));
    return () => { cancelled = true; };
  }, [activities, onSelect, selectedActivityId]);

  useEffect(() => () => { mapRef.current?.destroy(); mapRef.current = null; }, []);

  return <div className="amap-stage"><div className="amap-canvas" ref={containerRef} />{error && <div className="map-setup-message"><strong>地图尚未完成配置</strong><span>{error}</span><small>在 frontend/.env.local 中填写高德 JS API Key 后即可显示真实地图。</small></div>}</div>;
}
