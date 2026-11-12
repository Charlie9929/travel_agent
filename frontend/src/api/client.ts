import type {
  Activity,
  AgentMessage,
  AuthUser,
  LobbyMessage,
  Member,
  ReplanResult,
  Workspace,
} from "../types";

export type JsonObject = Record<string, unknown>;
type Money = string | number;

type ApiEnvelope<T> = { code: string; data: T; msg: string };

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

export type ApiTripStatus = "draft" | "ongoing" | "finished";
export type ApiTrip = {
  id: number; agent_trip_id?: string; title: string; city: string; start_date: string; end_date: string;
  total_budget: Money | null; creator_id?: number; traveler_count: number | null; origin_city?: string | null;
  preferences?: JsonObject; constraints?: JsonObject; version: number; status: ApiTripStatus;
  last_editor_id?: number | null; created_at?: string; updated_at?: string;
};
export type ApiTripDetail = ApiTrip & { days: { day_number: number; date: string; activities: ApiActivity[] }[] };
export type ApiMember = {
  id: number; trip_id: number; user_id: number; role: "owner" | "editor" | "viewer"; joined_at: string;
  username?: string | null; nickname?: string | null; avatar_url?: string | null; requirement_status?: string;
  requirement_filled_by?: number | null; requirement_filled_by_nickname?: string | null;
};
export type ApiUserSearch = { id: number; username: string; nickname: string; avatar_url: string | null; is_member: boolean; can_invite: boolean };
export type ApiUser = { id: number; username: string; nickname: string; avatar_url: string | null };
export type ApiActivity = {
  id: number; agent_activity_id: string; trip_id: number; day_number: number; order_index: number; title: string;
  type: Activity["type"]; start_time: string | null; duration_min: number | null; location_name: string | null;
  latitude: Money | null; longitude: Money | null; price_estimated: Money | null; price_real: Money | null;
  price_source: string | null; description: string | null; poi_provider: string | null; poi_id: string | null;
  extra: JsonObject; created_at?: string; updated_at?: string;
};
export type ApiRequirement = {
  id: number; trip_id: number; user_id: number; nickname: string; avatar_url: string | null; content: JsonObject | null;
  status: string; filled_by: number | null; filled_by_nickname: string | null; shared_summary: string | null;
  shared_at: string | null; can_view_private: boolean; updated_at: string;
};
export type ApiRevision = {
  id: number; trip_id: number; resource_id: number | null; user_id: number; version: number; action: string;
  diff_content: JsonObject; resource_type: string; created_at: string; summary?: string | null; before?: unknown;
  after?: unknown; changes?: JsonObject[];
};
export type ApiExpenseSplit = { user_id: number; nickname: string; ratio: Money; should_pay: Money };
export type ApiExpense = {
  id: number; trip_id: number; activity_id: number | null; payer_id: number; payer_nickname: string; title: string;
  amount: Money; split_type: "equal" | "ratio"; is_settled: boolean; settled_at: string | null;
  settled_by: number | null; splits: ApiExpenseSplit[]; created_at: string; updated_at: string;
};
export type ApiSettlementTransfer = { from_user_id: number; from_nickname: string; to_user_id: number; to_nickname: string; amount: Money };
export type ApiHighlight = {
  id: number; trip_id: number; activity_id: number | null; created_by: number; title: string; content: string | null; image_url: string | null;
  occurred_at: string | null; created_at: string; updated_at: string; images: ApiHighlightMedia[];
};
export type ApiHighlightMedia = { id: number; file_url: string; mime_type: string; size_bytes: number; sort_order: number; created_at: string };
export type ApiMemory = {
  id: number; user_id: number; title: string; content: string; visibility: "private" | "shared";
  authorized_trip_ids: number[]; created_at: string; updated_at: string;
};
export type ApiUserSettings = { agent_preferences: JsonObject; memory_enabled: boolean };
export type ApiWeather = {
  city: string | null; city_code: string; date: string; condition_day: string | null; condition_night: string | null;
  temperature_min: string | number | null; temperature_max: string | number | null;
  precipitation_probability: string | number | null; provider: string; queried_at: string; stale: boolean;
};
export type ApiPoi = {
  poi_id: string | null; name: string | null; address: string | null; type: string | null; adcode: string | null;
  province: string | null; longitude: number | null; latitude: number | null;
};
export type ApiLobbyMessage = {
  id: number; trip_id: number; sender_id: number | null; sender_nickname: string | null; sender_avatar_url?: string | null;
  kind: string; content: string; visibility: string; reply_to_id: number | null; structured_data: JsonObject; created_at: string;
};
export type ApiAgentConversation = { id: number; trip_id: number; user_id: number; title: string; created_at?: string; updated_at?: string };
export type ApiAgentMessage = {
  id: number; conversation_id: number; role: "user" | "assistant"; content: string; status: string;
  error_code: string | null; created_at: string;
};

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

function getToken() {
  return localStorage.getItem("travel-agent-token") || import.meta.env.VITE_ACCESS_TOKEN || "";
}

function queryString(params: Record<string, string | number | boolean | null | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  const value = query.toString();
  return value ? `?${value}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, { ...init, headers });
  } catch (error) {
    throw new ApiError("无法连接后端，请确认 FastAPI 已启动", 0, "NETWORK_ERROR", error);
  }
  const payload = (await response.json().catch(() => null)) as ApiEnvelope<T> | null;
  if (!response.ok || !payload) {
    throw new ApiError(payload?.msg || `请求失败：${response.status}`, response.status, payload?.code || "UNKNOWN", payload?.data ?? null);
  }
  return payload.data;
}

async function uploadFileRequest<T>(path: string, file: File) {
  const headers = new Headers({ "Content-Type": file.type });
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, { method: "POST", headers, body: file });
  } catch (error) {
    throw new ApiError("无法连接后端，请确认 FastAPI 已启动", 0, "NETWORK_ERROR", error);
  }
  const payload = (await response.json().catch(() => null)) as ApiEnvelope<T> | null;
  if (!response.ok || !payload) {
    throw new ApiError(payload?.msg || `上传失败：${response.status}`, response.status, payload?.code || "UNKNOWN", payload?.data ?? null);
  }
  return payload.data;
}

export function apiAssetUrl(path: string) {
  if (/^https?:\/\//.test(path)) return path;
  return new URL(path, new URL(baseUrl).origin).toString();
}

export const api = {
  auth: {
    async register(username: string, password: string, nickname: string) {
      const result = await request<{ token: string; user_info: ApiUser }>("/auth/register", { method: "POST", body: JSON.stringify({ username, password, nickname }) });
      localStorage.setItem("travel-agent-token", result.token);
      return { token: result.token, user: mapUser(result.user_info) };
    },
    async login(username: string, password: string) {
      const result = await request<{ token: string; user_info: ApiUser }>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
      localStorage.setItem("travel-agent-token", result.token);
      return { token: result.token, user: mapUser(result.user_info) };
    },
    me: async () => mapUser(await request<ApiUser>("/auth/me")),
    logout: () => localStorage.removeItem("travel-agent-token"),
  },
  trips: {
    list: (params: { page?: number; pageSize?: number; status?: ApiTripStatus } = {}) => request<{ items: ApiTrip[]; page: number; page_size: number }>(`/trips${queryString({ page: params.page, page_size: params.pageSize, status: params.status })}`),
    get: (tripId: number) => request<ApiTripDetail>(`/trips/${tripId}`),
    create: (body: JsonObject) => request<ApiTrip>("/trips", { method: "POST", body: JSON.stringify(body) }),
    update: (tripId: number, body: JsonObject & { version: number }) => request<ApiTrip>(`/trips/${tripId}`, { method: "PUT", body: JSON.stringify(body) }),
    remove: (tripId: number, version: number) => request<{ deleted: boolean }>(`/trips/${tripId}`, { method: "DELETE", body: JSON.stringify({ version }) }),
    revisions: (tripId: number, params: { resourceType?: string; resourceId?: number; page?: number; pageSize?: number } = {}) => request<ApiRevision[]>(`/trips/${tripId}/revisions${queryString({ resource_type: params.resourceType, resource_id: params.resourceId, page: params.page, page_size: params.pageSize })}`),
    revision: (tripId: number, revisionId: number) => request<ApiRevision>(`/trips/${tripId}/revisions/${revisionId}`),
    validate: (tripId: number, candidateActivities?: JsonObject[]) => request<JsonObject>(`/trips/${tripId}/validate`, { method: "POST", body: JSON.stringify({ candidate_activities: candidateActivities ?? null }) }),
  },
  members: {
    list: (tripId: number) => request<ApiMember[]>(`/trips/${tripId}/members`),
    invite: (tripId: number, userId: number, role: "editor" | "viewer" = "editor") => request<ApiMember>(`/trips/${tripId}/members/invite`, { method: "POST", body: JSON.stringify({ user_id: userId, role }) }),
    updateRole: (tripId: number, userId: number, role: "editor" | "viewer") => request<ApiMember>(`/trips/${tripId}/members/${userId}`, { method: "PUT", body: JSON.stringify({ role }) }),
    remove: (tripId: number, userId: number) => request<{ deleted: boolean }>(`/trips/${tripId}/members/${userId}`, { method: "DELETE" }),
    leave: (tripId: number) => request<{ left: boolean }>(`/trips/${tripId}/members/leave`, { method: "POST" }),
    createShareCode: (tripId: number, expiresInHours = 72) => request<{ share_code: string; expires_at: string }>(`/trips/${tripId}/share-code`, { method: "POST", body: JSON.stringify({ expires_in_hours: expiresInHours }) }),
    previewShare: (shareCode: string) => request<JsonObject>(`/trips/share/${encodeURIComponent(shareCode)}`),
    join: (shareCode: string) => request<ApiMember>("/trips/join", { method: "POST", body: JSON.stringify({ share_code: shareCode }) }),
  },
  activities: {
    list: (tripId: number, params: { dayNumber?: number; page?: number; pageSize?: number } = {}) => request<ApiActivity[]>(`/trips/${tripId}/activities${queryString({ day_number: params.dayNumber, page: params.page, page_size: params.pageSize })}`),
    create: (tripId: number, body: JsonObject & { trip_version: number }) => request<JsonObject>(`/trips/${tripId}/activities`, { method: "POST", body: JSON.stringify(body) }),
    update: (tripId: number, activityId: number, body: JsonObject & { trip_version: number }) => request<JsonObject>(`/trips/${tripId}/activities/${activityId}`, { method: "PUT", body: JSON.stringify(body) }),
    remove: (tripId: number, activityId: number, tripVersion: number) => request<JsonObject>(`/trips/${tripId}/activities/${activityId}`, { method: "DELETE", body: JSON.stringify({ trip_version: tripVersion }) }),
    reorder: (tripId: number, dayNumber: number, idOrder: number[], tripVersion: number) => request<JsonObject>(`/trips/${tripId}/activities/reorder`, { method: "PUT", body: JSON.stringify({ day_number: dayNumber, id_order: idOrder, trip_version: tripVersion }) }),
  },
  ai: {
    generate: (tripId: number, additionalRequirements?: string) => request<JsonObject>("/ai/generate", { method: "POST", body: JSON.stringify({ trip_id: tripId, additional_requirements: additionalRequirements || null }) }),
    replan: async (body: { trip_id: number; day_number: number; adjustment_requirements: string; trip_version: number; after_time?: string; trigger?: JsonObject; candidate_replacements?: JsonObject[] }) => {
      const result = await request<{ ai_run_id: number; candidate_itinerary: unknown; diff?: { ops: JsonObject[] }; summary: string; base_version: number; retry_count?: number; changed_items?: unknown[]; kept_items?: unknown[] }>("/ai/replan", { method: "POST", body: JSON.stringify(body) });
      return { aiRunId: result.ai_run_id, candidateItinerary: result.candidate_itinerary, summary: result.summary, baseVersion: result.base_version, diff: result.diff, retryCount: result.retry_count, changedItems: result.changed_items, keptItems: result.kept_items } satisfies ReplanResult;
    },
    revise: (body: { trip_id: number; changed_constraints: JsonObject; user_instruction?: string; trip_version: number }) => request<JsonObject>("/ai/revise", { method: "POST", body: JSON.stringify(body) }),
    explainDiff: (body: { trip_id: number; mode?: "explain" | "conflict"; old_itinerary: JsonObject; new_itinerary: JsonObject | JsonObject[]; teammate_itinerary?: JsonObject }) => request<JsonObject>("/ai/explain-diff", { method: "POST", body: JSON.stringify(body) }),
    importGuide: (tripId: number, text: string) => request<JsonObject>("/ai/import-guide", { method: "POST", body: JSON.stringify({ trip_id: tripId, text }) }),
    run: (runId: number) => request<JsonObject>(`/ai/runs/${runId}`),
    retryApply: (runId: number) => request<JsonObject>(`/ai/runs/${runId}/retry-apply`, { method: "POST" }),
    applyRun: (tripId: number, runId: number, tripVersion: number) => request<JsonObject>(`/trips/${tripId}/ai-runs/${runId}/apply`, { method: "POST", body: JSON.stringify({ trip_version: tripVersion, apply_mode: "replace_itinerary", selected_candidate_ids: [] }) }),
    applyGuideRun: (tripId: number, runId: number, tripVersion: number, selectedCandidateIds: string[]) => request<JsonObject>(`/trips/${tripId}/ai-runs/${runId}/apply`, { method: "POST", body: JSON.stringify({ trip_version: tripVersion, apply_mode: "append_selected", selected_candidate_ids: selectedCandidateIds }) }),
  },
  map: {
    poi: (city: string, keyword: string) => request<{ items: ApiPoi[]; provider: string; queried_at: string }>(`/map/poi${queryString({ city, keyword })}`),
    route: (fromLat: number, fromLng: number, toLat: number, toLng: number, cityCode?: string) => request<JsonObject>(`/map/route${queryString({ from_lat: fromLat, from_lng: fromLng, to_lat: toLat, to_lng: toLng, city_code: cityCode })}`),
  },
  weather: (cityCode: string, date: string) => request<ApiWeather>(`/weather${queryString({ city_code: cityCode, date })}`),
  users: {
    search: (query: string, tripId?: number, limit = 20) => request<ApiUserSearch[]>(`/users/search${queryString({ q: query, trip_id: tripId, limit })}`),
    updateProfile: (body: { nickname?: string; avatar_url?: string | null }) => request<ApiUser>("/users/me/profile", { method: "PUT", body: JSON.stringify(body) }),
    uploadAvatar: async (file: File) => mapUser(await uploadFileRequest<ApiUser>("/users/me/avatar", file)),
    changePassword: (currentPassword: string, newPassword: string) => request<{ changed: boolean }>("/users/me/password", { method: "PUT", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }),
    settings: () => request<ApiUserSettings>("/users/me/settings"),
    updateSettings: (body: Partial<ApiUserSettings>) => request<ApiUserSettings>("/users/me/settings", { method: "PUT", body: JSON.stringify(body) }),
  },
  requirements: {
    list: (tripId: number) => request<ApiRequirement[]>(`/trips/${tripId}/requirements`),
    saveMine: (tripId: number, content: JsonObject, status: "pending" | "completed" = "completed") => request<ApiRequirement>(`/trips/${tripId}/requirements/me`, { method: "PUT", body: JSON.stringify({ content, status }) }),
    saveForMember: (tripId: number, userId: number, content: JsonObject, status: "pending" | "completed" = "completed") => request<ApiRequirement>(`/trips/${tripId}/requirements/${userId}`, { method: "PUT", body: JSON.stringify({ content, status }) }),
    shareMine: (tripId: number, summary: string) => request<ApiRequirement>(`/trips/${tripId}/requirements/me/share`, { method: "POST", body: JSON.stringify({ summary }) }),
    unshareMine: (tripId: number) => request<ApiRequirement>(`/trips/${tripId}/requirements/me/share`, { method: "DELETE" }),
  },
  memories: {
    list: (page = 1, pageSize = 50) => request<ApiMemory[]>(`/memories${queryString({ page, page_size: pageSize })}`),
    create: (body: { title: string; content: string; visibility?: "private" | "shared"; authorized_trip_ids?: number[] }) => request<ApiMemory>("/memories", { method: "POST", body: JSON.stringify(body) }),
    get: (memoryId: number) => request<ApiMemory>(`/memories/${memoryId}`),
    update: (memoryId: number, body: Partial<Pick<ApiMemory, "title" | "content" | "visibility" | "authorized_trip_ids">>) => request<ApiMemory>(`/memories/${memoryId}`, { method: "PUT", body: JSON.stringify(body) }),
    remove: (memoryId: number) => request<{ deleted: boolean }>(`/memories/${memoryId}`, { method: "DELETE" }),
  },
  expenses: {
    list: (tripId: number, params: { settled?: boolean; page?: number; pageSize?: number } = {}) => request<ApiExpense[]>(`/trips/${tripId}/expenses${queryString({ settled: params.settled, page: params.page, page_size: params.pageSize })}`),
    create: (tripId: number, body: JsonObject) => request<ApiExpense>(`/trips/${tripId}/expenses`, { method: "POST", body: JSON.stringify(body) }),
    update: (tripId: number, expenseId: number, body: JsonObject) => request<ApiExpense>(`/trips/${tripId}/expenses/${expenseId}`, { method: "PUT", body: JSON.stringify(body) }),
    remove: (tripId: number, expenseId: number) => request<{ deleted: boolean }>(`/trips/${tripId}/expenses/${expenseId}`, { method: "DELETE" }),
    settlement: (tripId: number) => request<ApiSettlementTransfer[]>(`/trips/${tripId}/expenses/settlement`),
    settle: (tripId: number, expenseIds: number[], settled = true) => request<{ updated: number; settled: boolean }>(`/trips/${tripId}/expenses/settle`, { method: "POST", body: JSON.stringify({ expense_ids: expenseIds, settled }) }),
  },
  highlights: {
    list: (tripId: number, params: { activityId?: number; page?: number; pageSize?: number } = {}) => request<ApiHighlight[]>(`/trips/${tripId}/highlights${queryString({ activity_id: params.activityId, page: params.page, page_size: params.pageSize })}`),
    create: (tripId: number, body: { title: string; activity_id?: number; content?: string; image_url?: string; occurred_at?: string }) => request<ApiHighlight>(`/trips/${tripId}/highlights`, { method: "POST", body: JSON.stringify(body) }),
    update: (tripId: number, highlightId: number, body: Partial<Pick<ApiHighlight, "title" | "activity_id" | "content" | "image_url" | "occurred_at">>) => request<ApiHighlight>(`/trips/${tripId}/highlights/${highlightId}`, { method: "PUT", body: JSON.stringify(body) }),
    remove: (tripId: number, highlightId: number) => request<{ deleted: boolean }>(`/trips/${tripId}/highlights/${highlightId}`, { method: "DELETE" }),
    uploadImage: (tripId: number, highlightId: number, file: File) => uploadFileRequest<ApiHighlightMedia>(`/trips/${tripId}/highlights/${highlightId}/images`, file),
    reorderImages: (tripId: number, highlightId: number, imageIds: number[]) => request<ApiHighlightMedia[]>(`/trips/${tripId}/highlights/${highlightId}/images/reorder`, { method: "PUT", body: JSON.stringify({ image_ids: imageIds }) }),
    removeImage: (tripId: number, highlightId: number, imageId: number) => request<{ deleted: boolean }>(`/trips/${tripId}/highlights/${highlightId}/images/${imageId}`, { method: "DELETE" }),
  },
  collaboration: {
    lobby: {
      list: async (tripId: number, afterId?: number) => {
        const result = await request<{ items: ApiLobbyMessage[]; unread_count: number; next_after_id: number | null }>(`/trips/${tripId}/messages${queryString({ after_id: afterId })}`);
        return { ...result, items: result.items.map(mapLobbyMessage) };
      },
      send: async (tripId: number, content: string, askAgent = false) => (await request<ApiLobbyMessage[]>(`/trips/${tripId}/messages`, { method: "POST", body: JSON.stringify({ content, ask_agent: askAgent }) })).map(mapLobbyMessage),
      markRead: (tripId: number, messageId: number) => request<{ last_read_message_id: number }>(`/trips/${tripId}/messages/read`, { method: "POST", body: JSON.stringify({ last_read_message_id: messageId }) }),
    },
    agent: {
      conversations: () => request<ApiAgentConversation[]>("/agent/conversations"),
      conversation: (tripId: number) => request<ApiAgentConversation>(`/trips/${tripId}/agent/conversation`, { method: "POST" }),
      messages: async (conversationId: number, afterId?: number) => (await request<ApiAgentMessage[]>(`/agent/conversations/${conversationId}/messages${queryString({ after_id: afterId })}`)).map(mapAgentMessage),
      message: async (messageId: number) => mapAgentMessage(await request<ApiAgentMessage>(`/agent/messages/${messageId}`)),
      send: async (conversationId: number, content: string) => {
        const result = await request<{ user_message: ApiAgentMessage; agent_message: ApiAgentMessage }>(`/agent/conversations/${conversationId}/messages`, { method: "POST", body: JSON.stringify({ content }) });
        return { userMessage: mapAgentMessage(result.user_message), agentMessage: mapAgentMessage(result.agent_message) };
      },
    },
  },
};

function mapLobbyMessage(message: ApiLobbyMessage): LobbyMessage {
  return { id: message.id, tripId: message.trip_id, senderId: message.sender_id, senderNickname: message.sender_nickname, senderAvatarUrl: message.sender_avatar_url, kind: message.kind, content: message.content, visibility: message.visibility, replyToId: message.reply_to_id, createdAt: message.created_at };
}
function mapUser(user: ApiUser): AuthUser {
  return { id: user.id, username: user.username, nickname: user.nickname, avatarUrl: user.avatar_url };
}
function mapAgentMessage(message: ApiAgentMessage): AgentMessage {
  return { id: message.id, conversationId: message.conversation_id, role: message.role, content: message.content, status: message.status, errorCode: message.error_code, createdAt: message.created_at };
}

export function mapApiWorkspace(trip: ApiTripDetail, members: ApiMember[], requirements: ApiRequirement[], historyTrips: ApiTrip[] = []): Workspace {
  const activities = trip.days.flatMap((day) => day.activities.map((activity) => ({
    id: activity.id, day: day.day_number, date: day.date, order: activity.order_index,
    time: activity.start_time?.slice(0, 5) ?? "待定", title: activity.title, type: activity.type,
    detail: activity.description ?? activity.location_name ?? "暂无活动说明", location: activity.location_name ?? "地点待定",
    latitude: activity.latitude === null ? null : Number(activity.latitude), longitude: activity.longitude === null ? null : Number(activity.longitude),
    estimatedPrice: activity.price_estimated === null ? null : Number(activity.price_estimated), actualPrice: activity.price_real === null ? null : Number(activity.price_real),
    status: typeof activity.extra?.status === "string" ? activity.extra.status : undefined, booked: Boolean(activity.price_real),
  })));
  const requirementByUser = new Map(requirements.map((item) => [item.user_id, item]));
  const mappedMembers: Member[] = members.map((member) => {
    const requirement = requirementByUser.get(member.user_id);
    return {
      id: member.user_id, name: member.nickname || member.username || `成员 ${member.user_id}`,
      role: member.role === "owner" ? "房主" : member.role === "editor" ? "可编辑" : "只读",
      status: requirement?.status === "completed" || member.requirement_status === "completed" ? "已补充" : "待补充",
      proxy: requirement?.filled_by_nickname ? `由${requirement.filled_by_nickname}代填` : member.requirement_filled_by_nickname ? `由${member.requirement_filled_by_nickname}代填` : undefined,
      avatar: member.avatar_url ? apiAssetUrl(member.avatar_url) : requirement?.avatar_url ? apiAssetUrl(requirement.avatar_url) : "",
    };
  });
  const sharedRequirements = requirements.filter((item) => item.shared_summary);
  return {
    tripId: trip.id, title: trip.title, city: trip.city, startDate: trip.start_date, endDate: trip.end_date,
    status: trip.status, travelerCount: trip.traveler_count ?? members.length, version: trip.version, members: mappedMembers,
    sharedSummary: sharedRequirements.length ? sharedRequirements.map((item) => `${item.nickname}：${item.shared_summary}`).join("；") : "还没有同行者公开共享需求",
    sharedCount: sharedRequirements.length, budget: trip.total_budget === null ? "未设置预算" : `¥${trip.total_budget}`, activities,
    historyTrips: historyTrips.map((item) => ({ id: item.id, title: item.title, dates: `${item.start_date} 至 ${item.end_date}`, people: `${item.traveler_count ?? 0}人` })),
  };
}

export const apiConfig = { baseUrl };
