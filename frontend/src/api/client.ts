import type { Activity, Member, ReplanResult, Workspace } from "../types";

type ApiEnvelope<T> = {
  code: string;
  data: T;
  msg: string;
};

export class ApiError extends Error {
  status: number;
  code: string;
  detail: unknown;

  constructor(message: string, status: number, code = "UNKNOWN", detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export type ApiTrip = {
  id: number;
  title: string;
  city: string;
  start_date: string;
  end_date: string;
  total_budget: string | number | null;
  traveler_count: number | null;
  version: number;
  status: string;
};

export type ApiTripDetail = ApiTrip & {
  days: { day_number: number; date: string; activities: ApiActivity[] }[];
};

export type ApiMember = {
  id: number;
  trip_id: number;
  user_id: number;
  role: string;
  joined_at: string;
};

export type ApiActivity = {
  id: number;
  day_number: number;
  order_index: number;
  title: string;
  type: Activity["type"];
  start_time: string | null;
  duration_min: number | null;
  location_name: string | null;
  price_estimated: string | number | null;
  price_real: string | number | null;
  description: string | null;
  extra: Record<string, unknown>;
};

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

function getToken() {
  return localStorage.getItem("travel-agent-token") || import.meta.env.VITE_ACCESS_TOKEN || "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${baseUrl}${path}`, { ...init, headers });
  const payload = (await response.json()) as ApiEnvelope<T> | { code?: string; msg?: string; data?: unknown };
  if (!response.ok) {
    const message = "msg" in payload && payload.msg ? payload.msg : `请求失败：${response.status}`;
    const code = "code" in payload && payload.code ? payload.code : "UNKNOWN";
    const detail = "data" in payload ? payload.data : null;
    throw new ApiError(message, response.status, code, detail);
  }
  return (payload as ApiEnvelope<T>).data;
}

export const api = {
  auth: {
    async login(username: string, password: string) {
      const result = await request<{ token: string } & Record<string, unknown>>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      if (result.token) localStorage.setItem("travel-agent-token", result.token);
      return result;
    },
    me: () => request<Record<string, unknown>>("/auth/me"),
  },
  trips: {
    list: () => request<{ items: ApiTrip[]; page: number; page_size: number }>("/trips"),
    get: (tripId: number) => request<ApiTripDetail>(`/trips/${tripId}`),
    revisions: (tripId: number) => request<Record<string, unknown>[]>(`/trips/${tripId}/revisions`),
    create: (body: Record<string, unknown>) => request<ApiTrip>("/trips", { method: "POST", body: JSON.stringify(body) }),
  },
  members: {
    list: (tripId: number) => request<ApiMember[]>(`/trips/${tripId}/members`),
    invite: (tripId: number, userId: number, role = "editor") => request<ApiMember>(`/trips/${tripId}/members/invite`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId, role }),
    }),
    createShareCode: (tripId: number, expiresInHours = 72) => request<{ share_code: string; expires_at: string }>(`/trips/${tripId}/share-code`, {
      method: "POST",
      body: JSON.stringify({ expires_in_hours: expiresInHours }),
    }),
    join: (shareCode: string) => request<ApiMember>("/trips/join", { method: "POST", body: JSON.stringify({ share_code: shareCode }) }),
  },
  activities: {
    list: (tripId: number, dayNumber?: number) => request<ApiActivity[]>(`/trips/${tripId}/activities${dayNumber ? `?day_number=${dayNumber}` : ""}`),
  },
  ai: {
    replan: async (body: {
      trip_id: number;
      day_number: number;
      adjustment_requirements: string;
      trip_version: number;
      after_time?: string;
      trigger?: Record<string, unknown>;
      candidate_replacements?: Record<string, unknown>[];
    }) => {
      const result = await request<{
        ai_run_id: number;
        candidate_itinerary: unknown;
        diff?: { ops: Record<string, unknown>[] };
        summary: string;
        base_version: number;
        retry_count?: number;
      }>("/ai/replan", { method: "POST", body: JSON.stringify(body) });
      return {
        aiRunId: result.ai_run_id,
        candidateItinerary: result.candidate_itinerary,
        summary: result.summary,
        baseVersion: result.base_version,
        diff: result.diff,
        retryCount: result.retry_count,
      } satisfies ReplanResult;
    },
    applyRun: (tripId: number, runId: number, tripVersion: number) => request<Record<string, unknown>>(`/trips/${tripId}/ai-runs/${runId}/apply`, {
      method: "POST",
      body: JSON.stringify({ trip_version: tripVersion, apply_mode: "replace_itinerary", selected_candidate_ids: [] }),
    }),
    applyGuideRun: (tripId: number, runId: number, tripVersion: number, selectedCandidateIds: string[]) => request<Record<string, unknown>>(`/trips/${tripId}/ai-runs/${runId}/apply`, {
      method: "POST",
      body: JSON.stringify({ trip_version: tripVersion, apply_mode: "append_selected", selected_candidate_ids: selectedCandidateIds }),
    }),
    generate: (tripId: number, additionalRequirements?: string) => request<Record<string, unknown>>("/ai/generate", { method: "POST", body: JSON.stringify({ trip_id: tripId, additional_requirements: additionalRequirements }) }),
    revise: (body: Record<string, unknown>) => request<Record<string, unknown>>("/ai/revise", { method: "POST", body: JSON.stringify(body) }),
    explainDiff: (body: Record<string, unknown>) => request<Record<string, unknown>>("/ai/explain-diff", { method: "POST", body: JSON.stringify(body) }),
    importGuide: (tripId: number, text: string) => request<Record<string, unknown>>("/ai/import-guide", { method: "POST", body: JSON.stringify({ trip_id: tripId, text }) }),
  },
  map: {
    poi: (city: string, keyword: string) => request<Record<string, unknown>>(`/map/poi?city=${encodeURIComponent(city)}&keyword=${encodeURIComponent(keyword)}`),
    route: (fromLat: number, fromLng: number, toLat: number, toLng: number, cityCode?: string) => request<Record<string, unknown>>(`/map/route?from_lat=${fromLat}&from_lng=${fromLng}&to_lat=${toLat}&to_lng=${toLng}${cityCode ? `&city_code=${encodeURIComponent(cityCode)}` : ""}`),
  },
  weather: (cityCode: string, date: string) => request<Record<string, unknown>>(`/weather?city_code=${encodeURIComponent(cityCode)}&date=${encodeURIComponent(date)}`),
};

export function mapApiWorkspace(trip: ApiTripDetail, members: ApiMember[], fallbackMembers: Member[] = []): Workspace {
  const activities = trip.days.flatMap((day) => day.activities.map((activity) => ({
    id: activity.id,
    day: day.day_number,
    date: day.date,
    time: activity.start_time?.slice(0, 5) ?? "待定",
    title: activity.title,
    type: activity.type,
    detail: activity.description ?? activity.location_name ?? "行程活动",
    location: activity.location_name ?? trip.city,
    status: activity.price_real ? "已确认" : undefined,
    booked: Boolean(activity.price_real),
  })));

  const mappedMembers: Member[] = members.map((member, index) => {
    const fallback = fallbackMembers[index];
    return {
      id: member.user_id,
      name: fallback?.name ?? `成员 ${member.user_id}`,
      role: member.role === "owner" ? "房主" : undefined,
      status: fallback?.status ?? "待补充",
      proxy: fallback?.proxy,
      avatar: fallback?.avatar ?? "",
      avatarPosition: fallback?.avatarPosition,
    };
  });

  return {
    tripId: trip.id,
    title: trip.title,
    city: trip.city,
    startDate: trip.start_date,
    endDate: trip.end_date,
    travelerCount: trip.traveler_count ?? members.length,
    version: trip.version,
    members: mappedMembers,
    sharedSummary: "从后端行程数据读取同行者偏好",
    sharedCount: 0,
    budget: trip.total_budget ? `¥${trip.total_budget}` : "未设置预算",
    activities,
    historyTrips: [],
  };
}

export const apiConfig = { baseUrl, useMocks: import.meta.env.VITE_USE_MOCKS !== "false" };
