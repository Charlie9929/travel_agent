import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "./components/AppShell";
import { ActivityEditorSheet, type ActivityFormValues } from "./components/ActivityEditorSheet";
import { AuthSheet } from "./components/AuthSheet";
import { CandidateSheet } from "./components/CandidateSheet";
import { ChatSheet } from "./components/ChatSheet";
import { CreateTripSheet, type CreateTripValues } from "./components/CreateTripSheet";
import { DataSheet, type DataRow } from "./components/DataSheet";
import { ExpenseSheet, type ExpenseFormValues } from "./components/ExpenseSheet";
import { GuideImportSheet } from "./components/GuideImportSheet";
import { GenerationInputSheet } from "./components/GenerationInputSheet";
import { GuideCandidateSheet, type GuidePlacement } from "./components/GuideCandidateSheet";
import { HighlightSheet } from "./components/HighlightSheet";
import { ModalSheet } from "./components/ModalSheet";
import { PasswordSheet } from "./components/PasswordSheet";
import { ProcessingLabel } from "./components/ProcessingLabel";
import { ProcessingSteps } from "./components/ProcessingSteps";
import { RevisionSheet } from "./components/RevisionSheet";
import { SaveTextSheet } from "./components/SaveTextSheet";
import { TripSettingsSheet } from "./components/TripSettingsSheet";
import { TravelJournalSheet } from "./components/TravelJournalSheet";
import {
  ApiError,
  api,
  apiAssetUrl,
  apiConfig,
  mapApiWorkspace,
  type ApiRequirement,
  type ApiHighlight,
  type ApiRevision,
  type ApiTrip,
  type ApiUserSearch,
  type JsonObject,
} from "./api/client";
import { FunctionsPage } from "./pages/FunctionsPage";
import { HomePage } from "./pages/HomePage";
import { LobbyListPage, type LobbyPreview } from "./pages/LobbyListPage";
import { LobbyPage } from "./pages/LobbyPage";
import { TripListPage } from "./pages/TripListPage";
import { WorldPage } from "./pages/WorldPage";
import type { Activity, AgentMessage, AuthUser, LobbyMessage, ReplanResult, Tab, Workspace } from "./types";

function hasToken() {
  return Boolean(localStorage.getItem("travel-agent-token") || import.meta.env.VITE_ACCESS_TOKEN);
}

function readSavedText(key: string) {
  return localStorage.getItem(key) ?? "";
}

function personalPreferencesKey(userId: number | null) {
  return `travel-agent-personal-preferences-${userId ?? "guest"}`;
}

const CACHED_USER_KEY = "travel-agent-cached-user-v1";
const CACHED_TRIPS_KEY = "travel-agent-cached-trips-v1";
const WORKSPACE_CACHE_PREFIX = "travel-agent-workspace-cache-v1-";

function readCachedValue<T>(key: string): T | null {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null") as T | null;
    return value ?? null;
  } catch {
    localStorage.removeItem(key);
    return null;
  }
}

function cachedWorkspaceKey(tripId: number) {
  return `${WORKSPACE_CACHE_PREFIX}${tripId}`;
}

function readCachedWorkspace(tripId: number | null) {
  return tripId ? readCachedValue<Workspace>(cachedWorkspaceKey(tripId)) : null;
}

function persistWorkspace(workspace: Workspace) {
  localStorage.setItem(cachedWorkspaceKey(workspace.tripId), JSON.stringify(workspace));
}

const generationSteps = ["正在读取需求", "正在构思行程", "正在生成计划"];

function shareCodeFromPath() {
  const match = window.location.pathname.match(/^\/join\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function agentMentioned(content: string) {
  return /(?:@|＠)\s*agent\b/i.test(content) || /艾特\s*agent\b/i.test(content);
}

function mergeLobbyMessages(current: LobbyMessage[], incoming: LobbyMessage[]) {
  const serverMessages = new Map(current.filter((item) => item.id > 0).map((item) => [item.id, item]));
  const incomingServer = incoming.filter((item) => item.id > 0);
  incomingServer.forEach((item) => serverMessages.set(item.id, item));
  const localMessages = [...current.filter((item) => item.id < 0), ...incoming.filter((item) => item.id < 0)]
    .filter((local) => !incomingServer.some((server) => server.kind === local.kind && server.senderId === local.senderId && server.content === local.content));
  return [...serverMessages.values(), ...localMessages].sort((left, right) => {
    const timeDiff = new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime();
    return timeDiff || left.id - right.id;
  });
}

function candidateFromResponse(response: JsonObject): ReplanResult {
  const diff = response.diff as { ops: JsonObject[] } | undefined;
  return {
    aiRunId: Number(response.ai_run_id),
    summary: String(response.summary ?? "Agent 已生成一版调整建议"),
    candidateItinerary: response.candidate_itinerary,
    baseVersion: Number(response.base_version),
    diff,
    retryCount: Number(response.retry_count ?? 0),
    changedItems: Array.isArray(response.changed_items) ? response.changed_items : diff?.ops,
    keptItems: Array.isArray(response.kept_items) ? response.kept_items : [],
  };
}

type ConflictResolution = {
  action: string;
  submittedVersion?: number;
  currentVersion?: number;
  retry: () => Promise<void>;
};

function versionConflictDetail(error: unknown) {
  if (!(error instanceof ApiError) || error.code !== "VERSION_CONFLICT") return null;
  const detail = error.detail && typeof error.detail === "object" ? error.detail as Record<string, unknown> : {};
  return {
    submittedVersion: typeof detail.submitted_version === "number" ? detail.submitted_version : undefined,
    currentVersion: typeof detail.current_version === "number" ? detail.current_version : undefined,
  };
}

function specificErrorMessage(error: unknown) {
  if (!(error instanceof ApiError)) return (error as Error).message;
  const detail = error.detail && typeof error.detail === "object"
    ? error.detail as Record<string, unknown>
    : {};
  const validation = detail.validation_errors && typeof detail.validation_errors === "object"
    ? detail.validation_errors as Record<string, unknown>
    : detail;
  const groups = [
    Array.isArray(validation) ? validation : [],
    validation.errors,
    validation.route_errors,
    validation.poi_issues,
  ]
    .filter(Array.isArray)
    .flat() as Record<string, unknown>[];
  const categories = [
    { label: "时间安排冲突", codes: /^(TIME_|INVALID_TIME|DAY_SCHEDULE_OVERFLOW|DAY_TOO_LONG|ROUTE_TIME_INFEASIBLE|DATE_)/ },
    { label: "营业时间冲突", codes: /^(OUTSIDE_OPEN_HOURS|OPEN_HOURS_NO_FIT)/ },
    { label: "预算超出", codes: /^BUDGET_EXCEEDED$/ },
    { label: "报价信息不完整", codes: /^(COST_REQUIRED|INVALID_COST|QUOTED_PRICE_)/ },
    { label: "地点校验失败", codes: /^(LOCATION_|POI_|CITY_MISMATCH|UNTRUSTED_POI_ID|PLACEHOLDER_LOCATION)/ },
    { label: "路线校验失败", codes: /^(ROUTE_|AMAP_|BOUNDARY_|UNSUPPORTED_INTERCITY_MODE)/ },
    { label: "用餐安排缺失", codes: /^MISSING_LUNCH$/ },
    { label: "行程内容不完整", codes: /^(EMPTY_GENERATED_DAY|DAYS_REQUIRED|DAY_COUNT_MISMATCH|DAY_INDEX_MISMATCH)/ },
    { label: "Agent 输出格式错误", codes: /^(SUMMARY_|PROPOSED_|DIFF_|DRAFT_|MISSING_FIELD|UNEXPECTED_FIELD|INVALID_ACTIVITY|ACTIVITY_NOT_OBJECT|DAY_NOT_OBJECT|DUPLICATE_ACTIVITY)/ },
  ];
  for (const category of categories) {
    const messages = groups
      .filter((item) => category.codes.test(String(item.code || "")))
      .map((item) => String(item.message || ""))
      .filter((message, index, items) => Boolean(message) && items.indexOf(message) === index)
      .slice(0, 2);
    if (messages.length) return `${category.label}：${messages.join("；")}`;
  }
  for (const category of categories) {
    if (category.codes.test(error.code)) return `${category.label}：${error.message}`;
  }
  const providerLabels: Record<string, string> = {
    AGENT_LLM_TIMEOUT: "Agent 服务超时，请稍后重试",
    AGENT_LLM_UNAVAILABLE: "Agent 服务暂时不可用",
    AGENT_RATE_LIMIT: "Agent 请求过于频繁，请稍后重试",
    AGENT_QUOTA_EXCEEDED: "Agent 账户额度不足",
    AGENT_OUTPUT_INVALID: "Agent 返回的行程格式不符合要求",
    VERSION_CONFLICT: "行程已被其他成员更新，请刷新后重试",
  };
  return providerLabels[error.code] || error.message;
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>("world");
  const [workspace, setWorkspace] = useState<Workspace | null>(() => {
    if (!hasToken()) return null;
    const tripId = Number(localStorage.getItem("travel-agent-selected-trip")) || null;
    return readCachedWorkspace(tripId);
  });
  const [requirements, setRequirements] = useState<ApiRequirement[]>([]);
  const [tripNote, setTripNote] = useState("");
  const [personalPreferences, setPersonalPreferences] = useState("");
  const [trips, setTrips] = useState<ApiTrip[]>(() => readCachedValue<ApiTrip[]>(CACHED_TRIPS_KEY) ?? []);
  const [authUser, setAuthUser] = useState<AuthUser | null>(() => hasToken() ? readCachedValue<AuthUser>(CACHED_USER_KEY) : null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authOpen, setAuthOpen] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [createTripOpen, setCreateTripOpen] = useState(false);
  const [tripDetailOpen, setTripDetailOpen] = useState(() => Boolean(hasToken() && readCachedValue<AuthUser>(CACHED_USER_KEY) && workspace));
  const [lobbyDetailOpen, setLobbyDetailOpen] = useState(false);
  const [tripSettingsOpen, setTripSettingsOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteQuery, setInviteQuery] = useState("");
  const [inviteUsers, setInviteUsers] = useState<ApiUserSearch[]>([]);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteRole, setInviteRole] = useState<"editor" | "viewer">("editor");
  const [chatMode, setChatMode] = useState<"lobby" | "agent" | null>(null);
  const [lobbyMessages, setLobbyMessages] = useState<LobbyMessage[]>([]);
  const [lobbyUnread, setLobbyUnread] = useState(0);
  const [lobbyPreviews, setLobbyPreviews] = useState<LobbyPreview[]>([]);
  const [lobbyListLoading, setLobbyListLoading] = useState(false);
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>([]);
  const [agentConversationId, setAgentConversationId] = useState<number | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [replanActivity, setReplanActivity] = useState<Activity | null>(null);
  const [activityEditor, setActivityEditor] = useState<{ activity?: Activity; day: number } | null>(null);
  const [expenseActivity, setExpenseActivity] = useState<Activity | null | undefined>(undefined);
  const [recordActivity, setRecordActivity] = useState<Activity | null | undefined>(undefined);
  const [replanResult, setReplanResult] = useState<ReplanResult | null>(null);
  const [replanLoading, setReplanLoading] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [generationContext, setGenerationContext] = useState("");
  const [clarifyQuestions, setClarifyQuestions] = useState<string[]>([]);
  const [generationStep, setGenerationStep] = useState(0);
  const [reviseOpen, setReviseOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideResult, setGuideResult] = useState<{ runId: number; candidates: JsonObject[] } | null>(null);
  const [tripNotesOpen, setTripNotesOpen] = useState(false);
  const [personalPreferencesOpen, setPersonalPreferencesOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [dataSheet, setDataSheet] = useState<{ title: string; rows: DataRow[] } | null>(null);
  const [revisionSheet, setRevisionSheet] = useState<ApiRevision[] | null>(null);
  const [journalSheet, setJournalSheet] = useState<{ workspace: Workspace; highlights: ApiHighlight[] } | null>(null);
  const [dataLoading, setDataLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [archivedActionNoticeOpen, setArchivedActionNoticeOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [syncIndicatorVisible, setSyncIndicatorVisible] = useState(false);
  const [conflict, setConflict] = useState<ConflictResolution | null>(null);
  const lobbyMessagesRef = useRef<LobbyMessage[]>([]);
  const localMessageIdRef = useRef(-1);
  const authUserRef = useRef<AuthUser | null>(authUser);
  const tripsRef = useRef<ApiTrip[]>(trips);
  const workspaceRef = useRef<Workspace | null>(workspace);

  useEffect(() => { authUserRef.current = authUser; }, [authUser]);
  useEffect(() => { tripsRef.current = trips; }, [trips]);
  useEffect(() => { workspaceRef.current = workspace; }, [workspace]);

  useEffect(() => {
    if (!loading) {
      setSyncIndicatorVisible(false);
      return;
    }
    const timer = window.setTimeout(() => setSyncIndicatorVisible(true), 450);
    return () => window.clearTimeout(timer);
  }, [loading]);

  useEffect(() => {
    lobbyMessagesRef.current = lobbyMessages;
  }, [lobbyMessages]);

  const handleUnauthorized = useCallback(() => {
    api.auth.logout();
    localStorage.removeItem("travel-agent-selected-trip");
    localStorage.removeItem(CACHED_USER_KEY);
    setAuthUser(null);
    setWorkspace(null);
    setTrips([]);
    setAuthOpen(true);
  }, []);

  const refreshWorkspace = useCallback(async (preferredTripId?: number) => {
    setLoading(true);
    try {
      const currentUser = authUserRef.current;
      const currentWorkspace = workspaceRef.current;
      const canUseFastRefresh = Boolean(
        preferredTripId &&
        currentWorkspace?.tripId === preferredTripId &&
        currentUser &&
        tripsRef.current.length,
      );
      let user = currentUser;
      let items = tripsRef.current;
      let joinedTripId: number | undefined;
      const shareCode = shareCodeFromPath();
      if (!canUseFastRefresh && shareCode) {
        user = await api.auth.me();
        setAuthUser(user);
        localStorage.setItem(CACHED_USER_KEY, JSON.stringify(user));
        try {
          const membership = await api.members.join(shareCode);
          joinedTripId = membership.trip_id;
          window.history.replaceState({}, "", "/");
          setNotice("已通过分享码加入旅行");
        } catch (error) {
          if (!(error instanceof ApiError) || error.code !== "MEMBER_EXISTS") throw error;
          window.history.replaceState({}, "", "/");
        }
      }
      if (!canUseFastRefresh && !shareCode) {
        const [freshUser, tripResult] = await Promise.all([
          api.auth.me(),
          api.trips.list({ pageSize: 100 }),
        ]);
        user = freshUser;
        items = tripResult.items;
        setAuthUser(user);
        localStorage.setItem(CACHED_USER_KEY, JSON.stringify(user));
      } else if (!canUseFastRefresh) {
        const tripResult = await api.trips.list({ pageSize: 100 });
        items = tripResult.items;
      }
      setTrips(items);
      tripsRef.current = items;
      localStorage.setItem(CACHED_TRIPS_KEY, JSON.stringify(items));
      const requestedId = joinedTripId ?? preferredTripId ?? (Number(localStorage.getItem("travel-agent-selected-trip")) || 0);
      const selectedTrip = items.find((trip) => trip.id === requestedId) ?? items.find((trip) => trip.status !== "finished") ?? items[0];
      if (!selectedTrip) {
        setWorkspace(null);
        setRequirements([]);
        return null;
      }
      localStorage.setItem("travel-agent-selected-trip", String(selectedTrip.id));
      const [detail, members, requirementItems, collaborationNote] = await Promise.all([
        api.trips.get(selectedTrip.id),
        api.members.list(selectedTrip.id),
        api.requirements.list(selectedTrip.id),
        api.trips.collaborationNote(selectedTrip.id),
      ]);
      setRequirements(requirementItems);
      const mappedWorkspace = mapApiWorkspace(detail, members, requirementItems, items.filter((trip) => trip.status === "finished" && trip.id !== selectedTrip.id));
      setWorkspace(mappedWorkspace);
      workspaceRef.current = mappedWorkspace;
      persistWorkspace(mappedWorkspace);
      setTripNote(collaborationNote.content);
      if (user) setPersonalPreferences(readSavedText(personalPreferencesKey(user.id)));
      setCreateTripOpen(false);
      return mappedWorkspace;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        handleUnauthorized();
      } else {
        setNotice(`读取真实数据失败：${(error as Error).message}`);
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, [handleUnauthorized]);

  useEffect(() => {
    if (!hasToken()) {
      setAuthOpen(true);
      return;
    }
    void refreshWorkspace();
  }, [refreshWorkspace]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 4200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!authUser || !workspace) return;
    let cancelled = false;
    let inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const [detail, members, requirementItems, collaborationNote] = await Promise.all([
          api.trips.get(workspace.tripId),
          api.members.list(workspace.tripId),
          api.requirements.list(workspace.tripId),
          api.trips.collaborationNote(workspace.tripId),
        ]);
        if (cancelled) return;
        setTripNote(collaborationNote.content);
        if (detail.version === workspace.version) return;
        const mapped = mapApiWorkspace(detail, members, requirementItems, trips.filter((trip) => trip.status === "finished" && trip.id !== detail.id));
        setRequirements(requirementItems);
        setTrips((items) => items.map((trip) => trip.id === detail.id ? { ...trip, ...detail } : trip));
        setWorkspace(mapped);
        setNotice(`检测到同行者更新，已同步到第 ${detail.version} 版`);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) handleUnauthorized();
      } finally {
        inFlight = false;
      }
    };
    const timer = window.setInterval(() => void poll(), 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [authUser, handleUnauthorized, trips, workspace]);

  const offerConflictResolution = (error: unknown, action: string, retry: () => Promise<void>) => {
    const versions = versionConflictDetail(error);
    if (!versions) return false;
    setConflict({ action, ...versions, retry });
    return true;
  };

  useEffect(() => {
    if (activeTab !== "lobby" || !authUser || !trips.length) {
      if (!trips.length) setLobbyPreviews([]);
      return;
    }
    let cancelled = false;
    let inFlight = false;
    setLobbyListLoading(true);
    const loadPreviews = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const items = await Promise.all(trips.map(async (trip) => {
          try {
            const result = await api.collaboration.lobby.list(trip.id);
            const latest = result.items.at(-1);
            return { tripId: trip.id, lastMessage: latest?.content ?? "", lastAt: latest?.createdAt ?? null, unread: result.unread_count } satisfies LobbyPreview;
          } catch {
            return { tripId: trip.id, lastMessage: "消息暂时无法读取", lastAt: null, unread: 0 } satisfies LobbyPreview;
          }
        }));
        if (!cancelled) setLobbyPreviews(items);
      } finally {
        inFlight = false;
        if (!cancelled) setLobbyListLoading(false);
      }
    };
    void loadPreviews();
    const timer = window.setInterval(() => void loadPreviews(), 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [activeTab, authUser, trips]);

  useEffect(() => {
    if (chatMode !== "lobby" || !workspace || !authUser) return;
    const tripId = workspace.tripId;
    let cancelled = false;
    let inFlight = false;
    const pollLobby = async () => {
      if (inFlight) return;
      inFlight = true;
      const lastServerId = lobbyMessagesRef.current.filter((item) => item.id > 0).at(-1)?.id;
      try {
        const result = await api.collaboration.lobby.list(tripId, lastServerId);
        if (cancelled) return;
        if (result.items.length) {
          setLobbyMessages((items) => {
            const next = mergeLobbyMessages(items, result.items);
            lobbyMessagesRef.current = next;
            return next;
          });
          const latest = result.items.at(-1);
          if (latest) {
            await api.collaboration.lobby.markRead(tripId, latest.id);
            if (!cancelled) {
              setLobbyUnread(0);
              setLobbyPreviews((items) => items.map((item) => item.tripId === tripId ? { ...item, lastMessage: latest.content, lastAt: latest.createdAt, unread: 0 } : item));
            }
          }
        } else if (!cancelled) {
          setLobbyUnread(result.unread_count);
        }
      } catch (error) {
        if (!cancelled && error instanceof ApiError && error.status === 401) handleUnauthorized();
      } finally {
        inFlight = false;
      }
    };
    const timer = window.setInterval(() => void pollLobby(), 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [authUser, chatMode, handleUnauthorized, workspace]);

  const handleAuth = async (values: { username: string; password: string; nickname: string }) => {
    setAuthLoading(true);
    setAuthError("");
    try {
      const result = authMode === "login" ? await api.auth.login(values.username, values.password) : await api.auth.register(values.username, values.password, values.nickname);
      setAuthUser(result.user);
      localStorage.setItem(CACHED_USER_KEY, JSON.stringify(result.user));
      setAuthOpen(false);
      setTripDetailOpen(false);
      setLobbyDetailOpen(false);
      setNotice("登录成功，正在读取行程");
      await refreshWorkspace();
    } catch (error) {
      setAuthError((error as Error).message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleForgotPassword = async (values: { username: string; nickname: string; newPassword: string }) => {
    setAuthLoading(true);
    setAuthError("");
    try {
      await api.auth.forgotPassword(values.username.trim(), values.nickname.trim(), values.newPassword);
      setNotice("密码已重置，请使用新密码登录");
      return true;
    } catch (error) {
      setAuthError((error as Error).message);
      return false;
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    api.auth.logout();
    localStorage.removeItem("travel-agent-selected-trip");
    localStorage.removeItem(CACHED_USER_KEY);
    setWorkspace(null);
    setTrips([]);
    setAuthUser(null);
    setPersonalPreferences("");
    setAuthOpen(true);
    setActiveTab("world");
    setTripDetailOpen(false);
    setLobbyDetailOpen(false);
  };

  const handleCreateTrip = async (values: CreateTripValues) => {
    setLoading(true);
    try {
      const createdTrip = await api.trips.create({ ...values, preferences: {}, constraints: {} });
      setCreateTripOpen(false);
      await refreshWorkspace(createdTrip.id);
      setGenerateOpen(true);
      setGenerationContext("");
      setClarifyQuestions([]);
      setActiveTab("world");
      setTripDetailOpen(true);
      setNotice("行程已创建，请补充要求后让 Agent 生成路线");
    } catch (error) {
      setNotice(`创建行程失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const openGenerateFlow = () => {
    if (workspace?.status === "finished") {
      setNotice("旅行已归档，行程内容仅支持查看");
      return;
    }
    setGenerationContext("");
    setClarifyQuestions([]);
    setGenerateOpen(true);
  };

  const handleSelectTrip = async (tripId: number) => {
    setActiveTab("world");
    await refreshWorkspace(tripId);
    setTripDetailOpen(true);
    setNotice("已切换旅行");
  };

  const isTripArchived = workspace?.status === "finished";
  const showArchivedActionNotice = () => {
    setArchivedActionNoticeOpen(true);
  };
  const ensureTripWritable = () => {
    if (isTripArchived) {
      showArchivedActionNotice();
      return false;
    }
    return true;
  };

  const handleSaveTripNote = async (value: string) => {
    if (!workspace || !ensureTripWritable()) return;
    const note = await api.trips.updateCollaborationNote(workspace.tripId, value);
    setTripNote(note.content);
    setNotice("同行者的想法已共享保存");
  };

  const handleSavePersonalPreferences = (value: string) => {
    setPersonalPreferences(value);
    localStorage.setItem(personalPreferencesKey(authUser?.id ?? null), value);
    setNotice("旅行备忘录已保存");
  };

  const handleOpenHistory = async (tripId: number) => {
    const selectedWorkspace = await refreshWorkspace(tripId);
    if (!selectedWorkspace) return;
    setTripDetailOpen(false);
    setActiveTab("functions");
    await openFeature("旅行手帐", selectedWorkspace);
  };

  const isTripOwner = Boolean(workspace && workspace.members.some((member) => member.id === authUser?.id && member.role === "房主"));
  const canEditItinerary = Boolean(!isTripArchived && workspace && workspace.members.some((member) => member.id === authUser?.id && member.permission !== "viewer"));

  const handleArchiveTrip = async () => {
    if (!workspace || !window.confirm("结束后会保留旅行记录，确认归档这场旅行吗？")) return;
    setLoading(true);
    try {
      await api.trips.update(workspace.tripId, { status: "finished", version: workspace.version });
      setTripSettingsOpen(false);
      await refreshWorkspace(workspace.tripId);
      setNotice("旅行已归档");
    } catch (error) {
      setNotice(`归档旅行失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteTrip = async () => {
    if (!workspace || !window.confirm("删除后无法恢复，确认删除这场旅行吗？")) return;
    setLoading(true);
    try {
      await api.trips.remove(workspace.tripId, workspace.version);
      localStorage.removeItem("travel-agent-selected-trip");
      setTripSettingsOpen(false);
      await refreshWorkspace();
      setTripDetailOpen(false);
      setNotice("旅行已删除");
    } catch (error) {
      setNotice(`删除旅行失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleLeaveTrip = async () => {
    if (!workspace) return;
    if (isTripOwner) {
      setNotice("房主不能退出自己的旅行，请先结束或删除");
      return;
    }
    if (!window.confirm("退出后将无法继续查看这场旅行，确认退出吗？")) return;
    setLoading(true);
    try {
      await api.members.leave(workspace.tripId);
      localStorage.removeItem("travel-agent-selected-trip");
      setTripSettingsOpen(false);
      await refreshWorkspace();
      setTripDetailOpen(false);
      setLobbyDetailOpen(false);
      setNotice("已退出旅行");
    } catch (error) {
      setNotice(`退出旅行失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const openLobby = async (tripId = workspace?.tripId) => {
    if (!tripId) return;
    setChatMode("lobby");
    setChatLoading(true);
    try {
      const result = await api.collaboration.lobby.list(tripId);
      setLobbyMessages(result.items);
      lobbyMessagesRef.current = result.items;
      setLobbyUnread(result.unread_count);
      const latest = result.items.at(-1);
      if (latest) await api.collaboration.lobby.markRead(tripId, latest.id);
      if (latest) setLobbyUnread(0);
      setLobbyPreviews((items) => items.map((item) => item.tripId === tripId ? { ...item, unread: 0 } : item));
    } catch (error) {
      setNotice(`读取大厅消息失败：${(error as Error).message}`);
    } finally {
      setChatLoading(false);
    }
  };

  const handleOpenTripChat = async (tripId: number) => {
    const selectedWorkspace = await refreshWorkspace(tripId);
    if (selectedWorkspace) await openLobby(tripId);
  };

  const handleManageLobby = async (tripId: number) => {
    const selectedWorkspace = await refreshWorkspace(tripId);
    if (selectedWorkspace) setLobbyDetailOpen(true);
  };

  const openAgentChat = async (tripId = workspace?.tripId) => {
    if (!tripId) return;
    setChatMode("agent");
    setChatLoading(true);
    try {
      const conversation = await api.collaboration.agent.conversation(tripId);
      setAgentConversationId(conversation.id);
      setAgentMessages(await api.collaboration.agent.messages(conversation.id));
    } catch (error) {
      setNotice(`读取 Agent 私聊失败：${(error as Error).message}`);
    } finally {
      setChatLoading(false);
    }
  };

  const openRecentAgentChat = async () => {
    setChatLoading(true);
    try {
      const conversations = await api.collaboration.agent.conversations();
      const latest = conversations[0];
      if (!latest) {
        setNotice("还没有 Agent 对话，先创建或打开一场旅行吧");
        return;
      }
      await refreshWorkspace(latest.trip_id);
      await openAgentChat(latest.trip_id);
    } catch (error) {
      setNotice(`读取最近对话失败：${(error as Error).message}`);
    } finally {
      setChatLoading(false);
    }
  };

  const handleChatSend = async (content: string) => {
    if (!chatMode || !workspace || !authUser || !ensureTripWritable()) return;
    const asksAgent = agentMentioned(content);
    const localUserId = localMessageIdRef.current--;
    const localAgentId = localMessageIdRef.current--;
    const createdAt = new Date().toISOString();
    setChatLoading(true);
    if (chatMode === "lobby") {
      const localUserMessage: LobbyMessage = {
        id: localUserId,
        tripId: workspace.tripId,
        senderId: authUser.id,
        senderNickname: authUser.nickname,
        senderAvatarUrl: authUser.avatarUrl ?? null,
        kind: "user",
        content,
        visibility: "trip",
        replyToId: null,
        structuredData: { local_id: localUserId },
        createdAt,
      };
      const localAgentMessage: LobbyMessage = {
        id: localAgentId,
        tripId: workspace.tripId,
        senderId: null,
        senderNickname: null,
        senderAvatarUrl: null,
        kind: "agent",
        content: "",
        visibility: "trip",
        replyToId: localUserId,
        structuredData: { local_status: "pending", retry_content: content, local_user_id: localUserId },
        createdAt: new Date(Date.now() + 1).toISOString(),
      };
      const optimistic = asksAgent ? [localUserMessage, localAgentMessage] : [localUserMessage];
      setLobbyMessages((items) => {
        const next = mergeLobbyMessages(items, optimistic);
        lobbyMessagesRef.current = next;
        return next;
      });
    } else {
      const localUserMessage: AgentMessage = {
        id: localUserId,
        conversationId: agentConversationId ?? 0,
        role: "user",
        content,
        status: "succeeded",
        errorCode: null,
        structuredData: { local_id: localUserId },
        createdAt,
      };
      const localAgentMessage: AgentMessage = {
        id: localAgentId,
        conversationId: agentConversationId ?? 0,
        role: "assistant",
        content: "",
        status: "pending",
        errorCode: null,
        structuredData: { local_status: "pending", retry_content: content },
        createdAt: new Date(Date.now() + 1).toISOString(),
      };
      setAgentMessages((items) => [...items, localUserMessage, localAgentMessage]);
    }
    try {
      if (chatMode === "lobby") {
        const created = await api.collaboration.lobby.send(workspace.tripId, content, asksAgent);
        setLobbyMessages((items) => {
          const next = mergeLobbyMessages(items.filter((item) => item.id !== localUserId && item.id !== localAgentId), created);
          lobbyMessagesRef.current = next;
          return next;
        });
        const latest = created.at(-1);
        if (latest) {
          await api.collaboration.lobby.markRead(workspace.tripId, latest.id);
          setLobbyUnread(0);
          setLobbyPreviews((items) => items.map((item) => item.tripId === workspace.tripId ? { ...item, lastMessage: latest.content, lastAt: latest.createdAt, unread: 0 } : item));
        }
      } else if (agentConversationId) {
        const result = await api.collaboration.agent.send(agentConversationId, content);
        setAgentMessages((items) => [...items.filter((item) => item.id !== localUserId && item.id !== localAgentId), result.userMessage, result.agentMessage]);
        if (result.agentMessage.status === "failed") setNotice(`Agent 暂时无法回复：${result.agentMessage.content || "请稍后重试"}`);
      }
    } catch (error) {
      if (chatMode === "lobby" && asksAgent) {
        const detail = error instanceof ApiError && error.detail && typeof error.detail === "object" ? error.detail as Record<string, unknown> : {};
        const savedMessageId = typeof detail.user_message_id === "number" ? detail.user_message_id : undefined;
        let serverMessages: LobbyMessage[] | null = null;
        if (savedMessageId) {
          try {
            serverMessages = (await api.collaboration.lobby.list(workspace.tripId)).items;
          } catch {
            serverMessages = null;
          }
        }
        const failedAgent: LobbyMessage = {
          id: localAgentId,
          tripId: workspace.tripId,
          senderId: null,
          senderNickname: null,
          senderAvatarUrl: null,
          kind: "agent",
          content: "",
          visibility: "trip",
          replyToId: savedMessageId ?? localUserId,
          structuredData: {
            local_status: "failed",
            retry_content: content,
            retry_message_id: savedMessageId,
            local_user_id: localUserId,
          },
          createdAt: new Date().toISOString(),
        };
        setLobbyMessages((items) => {
          const base = serverMessages ?? items;
          const withoutLocal = base.filter((item) => item.id !== localUserId && item.id !== localAgentId);
          const next = mergeLobbyMessages(withoutLocal, [failedAgent]);
          lobbyMessagesRef.current = next;
          return next;
        });
        setNotice(`Agent 暂时无法回复：${specificErrorMessage(error)}`);
      } else {
        if (chatMode === "lobby") {
          setLobbyMessages((items) => {
            const next = items.filter((item) => item.id !== localUserId);
            lobbyMessagesRef.current = next;
            return next;
          });
        } else {
          setAgentMessages((items) => items.filter((item) => item.id !== localUserId && item.id !== localAgentId));
        }
        setNotice(`发送失败：${specificErrorMessage(error)}`);
      }
    } finally {
      setChatLoading(false);
    }
  };

  const handleLobbyRetry = async (message: LobbyMessage) => {
    if (!workspace || !ensureTripWritable()) return;
    const retryContent = String(message.structuredData.retry_content ?? "");
    const retryMessageId = Number(message.structuredData.retry_message_id ?? 0);
    if (!retryContent) return;
    setChatLoading(true);
    setLobbyMessages((items) => {
      const next = items.map((item) => item.id === message.id ? { ...item, content: "", structuredData: { ...item.structuredData, local_status: "pending" } } : item);
      lobbyMessagesRef.current = next;
      return next;
    });
    try {
      const created = retryMessageId > 0
        ? await api.collaboration.lobby.retryAgent(workspace.tripId, retryMessageId)
        : await api.collaboration.lobby.send(workspace.tripId, retryContent, true);
      setLobbyMessages((items) => {
        const next = mergeLobbyMessages(items.filter((item) => item.id !== message.id && item.id !== Number(message.structuredData.local_user_id ?? 0)), created);
        lobbyMessagesRef.current = next;
        return next;
      });
      const latest = created.at(-1);
      if (latest) {
        await api.collaboration.lobby.markRead(workspace.tripId, latest.id);
        setLobbyUnread(0);
      }
    } catch (error) {
      setLobbyMessages((items) => {
        const next = items.map((item) => item.id === message.id ? { ...item, structuredData: { ...item.structuredData, local_status: "failed" } } : item);
        lobbyMessagesRef.current = next;
        return next;
      });
      setNotice(`Agent 暂时无法回复：${specificErrorMessage(error)}`);
    } finally {
      setChatLoading(false);
    }
  };

  const searchInviteUsers = async (query: string) => {
    setInviteQuery(query);
    if (!workspace || !query.trim()) {
      setInviteUsers([]);
      return;
    }
    setInviteLoading(true);
    try {
      setInviteUsers(await api.users.search(query, workspace.tripId));
    } catch (error) {
      setNotice(`搜索用户失败：${(error as Error).message}`);
    } finally {
      setInviteLoading(false);
    }
  };

  const handleInvite = async (userId: number) => {
    if (!workspace) return;
    try {
      await api.members.invite(workspace.tripId, userId, inviteRole);
      setNotice("成员已加入旅行");
      await refreshWorkspace(workspace.tripId);
    } catch (error) {
      setNotice(`邀请失败：${(error as Error).message}`);
    }
  };

  const handleChangeMemberRole = async (userId: number, role: "editor" | "viewer") => {
    if (!workspace) return;
    try {
      await api.members.updateRole(workspace.tripId, userId, role);
      await refreshWorkspace(workspace.tripId);
      setNotice(`成员权限已修改为${role === "editor" ? "可编辑" : "仅查看"}`);
    } catch (error) {
      setNotice(`修改成员权限失败：${(error as Error).message}`);
      throw error;
    }
  };

  const handleCopyInvite = async () => {
    if (!workspace) return;
    try {
      const result = await api.members.createShareCode(workspace.tripId);
      const inviteUrl = `${window.location.origin}/join/${result.share_code}`;
      try {
        await navigator.clipboard.writeText(inviteUrl);
        setNotice(`邀请链接已复制，有效期至 ${new Date(result.expires_at).toLocaleString("zh-CN")}`);
      } catch {
        window.prompt("邀请链接已生成，但浏览器未允许自动复制，请手动复制：", inviteUrl);
        setNotice(`邀请链接已生成，有效期至 ${new Date(result.expires_at).toLocaleString("zh-CN")}`);
      }
    } catch (error) {
      setNotice(`生成邀请链接失败：${(error as Error).message}`);
    }
  };

  const handleGenerate = async (requirementsText: string, referenceGuide = "") => {
    if (!workspace || !ensureTripWritable()) return;
    setReplanLoading(true);
    try {
      setGenerationStep(2);
      await api.ai.generate(workspace.tripId, requirementsText || undefined, referenceGuide || undefined);
      setGenerationStep(generationSteps.length);
      setGenerateOpen(false);
      await refreshWorkspace(workspace.tripId);
      setNotice("Agent 已生成并保存初始行程");
    } catch (error) {
      setNotice(`生成行程失败：${specificErrorMessage(error)}`);
    } finally {
      setReplanLoading(false);
    }
  };

  const handlePrepareGeneration = async (answer: string, referenceGuide = "") => {
    if (!workspace || !ensureTripWritable()) return;
    if (!answer.trim() && referenceGuide.trim() && !clarifyQuestions.length) {
      await handleGenerate("", referenceGuide);
      return;
    }
    const combined = [generationContext, clarifyQuestions.length ? `Agent 追问：${clarifyQuestions.join("；")}` : "", answer].filter(Boolean).join("\n");
    setReplanLoading(true);
    setGenerationStep(0);
    try {
      const result = await api.ai.clarifyPreferences(workspace.tripId, answer, combined);
      setGenerationStep(1);
      if (!result.ready) {
        setGenerationContext(combined);
        setClarifyQuestions(result.questions);
        return;
      }
      if (Object.keys(result.structured_constraints).length) {
        await api.trips.update(workspace.tripId, { constraints: result.structured_constraints, version: workspace.version });
        await refreshWorkspace(workspace.tripId);
      }
      await handleGenerate(result.summary || combined, referenceGuide);
    } catch (error) {
      setNotice(`偏好理解失败：${(error as Error).message}`);
    } finally {
      setReplanLoading(false);
    }
  };

  const handleRevise = async (instruction: string) => {
    if (!workspace || !ensureTripWritable()) return;
    setReplanLoading(true);
    try {
      const result = await api.ai.revise({ trip_id: workspace.tripId, changed_constraints: {}, user_instruction: instruction, trip_version: workspace.version });
      setReviseOpen(false);
      setReplanResult(candidateFromResponse(result));
    } catch (error) {
      setNotice(`生成整体修订失败：${specificErrorMessage(error)}`);
    } finally {
      setReplanLoading(false);
    }
  };

  const handleReplan = async (instruction: string) => {
    if (!replanActivity || !workspace || !ensureTripWritable()) return;
    setReplanLoading(true);
    try {
      const result = await api.ai.replan({ trip_id: workspace.tripId, day_number: replanActivity.day, adjustment_requirements: instruction, trip_version: workspace.version, after_time: replanActivity.time === "待定" ? undefined : replanActivity.time });
      setReplanActivity(null);
      setReplanResult(result);
    } catch (error) {
      setNotice(`生成调整建议失败：${specificErrorMessage(error)}`);
    } finally {
      setReplanLoading(false);
    }
  };

  const handleApplyCandidate = async () => {
    if (!replanResult || !workspace || !ensureTripWritable()) return;
    setReplanLoading(true);
    try {
      await api.ai.applyRun(workspace.tripId, replanResult.aiRunId, workspace.version);
      setReplanResult(null);
      await refreshWorkspace(workspace.tripId);
      if (agentConversationId) setAgentMessages(await api.collaboration.agent.messages(agentConversationId));
      if (chatMode === "lobby") await openLobby(workspace.tripId);
      setNotice("调整已应用，行程已刷新");
    } catch (error) {
      const tripId = workspace.tripId;
      const runId = replanResult.aiRunId;
      if (!offerConflictResolution(error, "应用 Agent 调整", async () => {
        const latest = await refreshWorkspace(tripId);
        if (!latest) return;
        await api.ai.applyRun(tripId, runId, latest.version);
        setReplanResult(null);
        await refreshWorkspace(tripId);
        setNotice("已在最新版上应用 Agent 调整");
      })) setNotice(`应用调整失败：${specificErrorMessage(error)}`);
    } finally {
      setReplanLoading(false);
    }
  };

  const handleSaveActivity = async (values: ActivityFormValues) => {
    if (!workspace || !activityEditor || !ensureTripWritable()) return;
    setLoading(true);
    try {
      if (activityEditor.activity) {
        await api.activities.update(workspace.tripId, activityEditor.activity.id, { ...values, trip_version: workspace.version });
        setNotice("活动已更新");
      } else {
        await api.activities.create(workspace.tripId, { ...values, extra: {}, trip_version: workspace.version });
        setNotice("活动已添加");
      }
      setActivityEditor(null);
      await refreshWorkspace(workspace.tripId);
    } catch (error) {
      const tripId = workspace.tripId;
      const editing = activityEditor;
      if (!offerConflictResolution(error, editing.activity ? "保存活动修改" : "新增活动", async () => {
        const latest = await refreshWorkspace(tripId);
        if (!latest) return;
        if (editing.activity) await api.activities.update(tripId, editing.activity.id, { ...values, trip_version: latest.version });
        else await api.activities.create(tripId, { ...values, extra: {}, trip_version: latest.version });
        setActivityEditor(null);
        await refreshWorkspace(tripId);
        setNotice("已在最新版行程上重试并保存");
      })) setNotice(`保存活动失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteActivity = async (activity: Activity) => {
    if (!workspace || !ensureTripWritable() || !window.confirm(`确认删除“${activity.title}”吗？该操作会生成版本记录。`)) return;
    setLoading(true);
    try {
      await api.activities.remove(workspace.tripId, activity.id, workspace.version);
      await refreshWorkspace(workspace.tripId);
      setNotice("活动已删除");
    } catch (error) {
      const tripId = workspace.tripId;
      if (!offerConflictResolution(error, `删除“${activity.title}”`, async () => {
        const latest = await refreshWorkspace(tripId);
        if (!latest) return;
        await api.activities.remove(tripId, activity.id, latest.version);
        await refreshWorkspace(tripId);
        setNotice("已在最新版行程上完成删除");
      })) setNotice(`删除活动失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleReorderActivities = async (dayNumber: number, activityIds: number[]) => {
    if (!workspace || !ensureTripWritable()) return;
    setLoading(true);
    try {
      await api.activities.reorder(workspace.tripId, dayNumber, activityIds, workspace.version);
      await refreshWorkspace(workspace.tripId);
      setNotice("活动顺序已调整");
    } catch (error) {
      const tripId = workspace.tripId;
      if (!offerConflictResolution(error, `调整第 ${dayNumber} 天的活动顺序`, async () => {
        const latest = await refreshWorkspace(tripId);
        if (!latest) return;
        await api.activities.reorder(tripId, dayNumber, activityIds, latest.version);
        await refreshWorkspace(tripId);
        setNotice("已在最新版行程上完成排序");
      })) setNotice(`调整活动顺序失败：${(error as Error).message}`);
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const handleCreateExpense = async (values: ExpenseFormValues) => {
    if (!workspace || !ensureTripWritable()) return;
    setLoading(true);
    try {
      await api.expenses.create(workspace.tripId, values);
      setExpenseActivity(undefined);
      setNotice("账单已保存，可以在旅行工具中统一查看和结算");
    } catch (error) {
      setNotice(`保存账单失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRecord = async (title: string, content: string, files: File[]) => {
    if (!workspace || !ensureTripWritable()) return;
    setLoading(true);
    try {
      const activity = recordActivity || undefined;
      const occurredAt = activity
        ? new Date(`${activity.date}T${activity.time === "待定" ? "12:00" : activity.time}:00`).toISOString()
        : new Date().toISOString();
      const record = await api.highlights.create(workspace.tripId, {
        title,
        content: content || undefined,
        activity_id: activity?.id,
        occurred_at: occurredAt,
      });
      for (const file of files) await api.highlights.uploadImage(workspace.tripId, record.id, file);
      setRecordActivity(undefined);
      setNotice(`旅行记录已保存${files.length ? `，已上传 ${files.length} 张照片` : ""}`);
    } catch (error) {
      setNotice(`保存旅行记录失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleImportGuide = async (text: string) => {
    if (!workspace || !ensureTripWritable()) return;
    setLoading(true);
    try {
      const result = await api.ai.importGuide(workspace.tripId, text);
      const candidates = Array.isArray(result.candidates) ? result.candidates as JsonObject[] : [];
      setGuideOpen(false);
      setGuideResult({ runId: Number(result.ai_run_id), candidates });
    } catch (error) {
      setNotice(`攻略导入失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRecognizeGuideImage = async (file: File) => {
    if (!workspace) throw new Error("请先打开一个行程");
    if (!ensureTripWritable()) throw new Error("旅行已归档，内容仅支持查看");
    const result = await api.ai.recognizeGuideImage(workspace.tripId, file);
    return result.text;
  };

  const handleVerifyGuide = async (placements: GuidePlacement[]) => {
    if (!workspace || !guideResult || !ensureTripWritable()) return [];
    setLoading(true);
    try {
      const result = await api.ai.verifyGuideRun(workspace.tripId, guideResult.runId, workspace.version, placements);
      return result.candidates;
    } catch (error) {
      setNotice(`攻略地点校验失败：${specificErrorMessage(error)}`);
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const handleApplyGuide = async (placements: GuidePlacement[]) => {
    if (!workspace || !guideResult || !placements.length || !ensureTripWritable()) return;
    setLoading(true);
    try {
      await api.ai.applyGuideRun(workspace.tripId, guideResult.runId, workspace.version, placements);
      setGuideResult(null);
      await refreshWorkspace(workspace.tripId);
      setNotice("已将选中的攻略条目加入行程");
    } catch (error) {
      setNotice(`应用攻略候选失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const openFeature = async (label: string, targetWorkspace = workspace) => {
    if (label === "上次的对话") {
      await openRecentAgentChat();
      return;
    }
    if (!targetWorkspace) return;
    if (targetWorkspace.status === "finished" && label === "攻略导入") {
      showArchivedActionNotice();
      return;
    }
    if (label === "和 Agent 聊聊") {
      await openAgentChat(targetWorkspace.tripId);
      return;
    }
    if (label === "攻略导入") {
      setGuideOpen(true);
      return;
    }
    if (label === "旅行手帐") {
      setJournalSheet({ workspace: targetWorkspace, highlights: [] });
      setDataLoading(true);
      try {
        const highlights = await api.highlights.list(targetWorkspace.tripId, { pageSize: 200 });
        setJournalSheet({ workspace: targetWorkspace, highlights });
      } catch (error) {
        setJournalSheet(null);
        setNotice(`读取旅行手帐失败：${(error as Error).message}`);
      } finally {
        setDataLoading(false);
      }
      return;
    }
    if (label === "行程版本") {
      setRevisionSheet([]);
      setDataLoading(true);
      try {
        setRevisionSheet(await api.trips.revisions(targetWorkspace.tripId, { pageSize: 200 }));
      } catch (error) {
        setRevisionSheet(null);
        setNotice(`读取历史记录失败：${(error as Error).message}`);
      } finally {
        setDataLoading(false);
      }
      return;
    }
    setDataSheet({ title: label, rows: [] });
    setDataLoading(true);
    try {
      if (label === "行程版本") {
        const revisions = await api.trips.revisions(targetWorkspace.tripId);
        setDataSheet({ title: label, rows: revisions.map((item) => ({ title: `第 ${item.version} 版 · ${item.action}`, description: item.summary ?? `${item.resource_type} 发生变化`, meta: new Date(item.created_at).toLocaleString("zh-CN") })) });
      } else if (label === "记账与分账") {
        const [expenses, transfers] = await Promise.all([api.expenses.list(targetWorkspace.tripId), api.expenses.settlement(targetWorkspace.tripId)]);
        const rows: DataRow[] = expenses.map((item) => {
          const activity = targetWorkspace.activities.find((candidate) => candidate.id === item.activity_id);
          return { title: `${item.title} · ¥${item.amount}`, description: `${item.payer_nickname} 付款 · ${item.is_settled ? "已结算" : "待结算"}`, meta: activity ? `关联活动：${activity.title}` : "旅行公共账单" };
        });
        rows.push(...transfers.map((item) => ({ title: `${item.from_nickname} → ${item.to_nickname} ¥${item.amount}`, description: "系统根据未结算账单计算的建议转账" })));
        setDataSheet({ title: label, rows });
      } else if (label === "记忆簿") {
        const memories = await api.memories.list();
        setDataSheet({ title: label, rows: memories.map((item) => ({ title: item.title, description: item.content, meta: item.visibility === "shared" ? "已授权共享" : "仅自己可见" })) });
      } else if (label === "设置") {
        const settings = await api.users.settings();
        setDataSheet({ title: label, rows: [{ title: "记忆使用", description: settings.memory_enabled ? "Agent 可以使用已授权记忆" : "Agent 不使用记忆" }, { title: "Agent 偏好", description: Object.keys(settings.agent_preferences).length ? JSON.stringify(settings.agent_preferences) : "尚未设置" }] });
      } else {
        setDataSheet(null);
        setNotice("该入口将在下一步界面重构中补充");
      }
    } catch (error) {
      setDataSheet(null);
      setNotice(`读取${label}失败：${(error as Error).message}`);
    } finally {
      setDataLoading(false);
    }
  };

  const handleUploadAvatar = async (file: File) => {
    if (!new Set(["image/jpeg", "image/png", "image/webp"]).has(file.type)) {
      setNotice("头像仅支持 JPEG、PNG 和 WebP 图片");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setNotice("头像不能超过 5MB");
      return;
    }
    setLoading(true);
    try {
      const user = await api.users.uploadAvatar(file);
      setAuthUser(user);
      if (workspace) await refreshWorkspace(workspace.tripId);
      setNotice("头像已更新");
    } catch (error) {
      setNotice(`上传头像失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async (currentPassword: string, newPassword: string) => {
    setLoading(true);
    try {
      await api.users.changePassword(currentPassword, newPassword);
      api.auth.logout();
      localStorage.removeItem("travel-agent-selected-trip");
      localStorage.removeItem(CACHED_USER_KEY);
      setPasswordOpen(false);
      setWorkspace(null);
      setTrips([]);
      setAuthUser(null);
      setAuthOpen(true);
      setAuthMode("login");
      setNotice("密码已修改，请使用新密码重新登录");
    } catch (error) {
      setNotice(`修改密码失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    if (tab === "world") setTripDetailOpen(false);
    if (tab === "lobby") setLobbyDetailOpen(false);
  };

  const handleConflictRetry = async () => {
    if (!conflict) return;
    const retry = conflict.retry;
    setConflict(null);
    setLoading(true);
    try {
      await retry();
    } catch (error) {
      setNotice(`重试失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const inviteOptions = inviteUsers.filter((user) => user.can_invite).map((user) => ({ ...user, description: user.username }));

  const noSelectedTrip = <div className="page empty-workspace-page"><section className="itinerary-empty"><h1>请先选择行程</h1><p>前往行程列表选择或新建一场旅行。</p><button className="primary-button" onClick={() => { setActiveTab("world"); setTripDetailOpen(false); }}>查看行程列表</button></section></div>;
  const currentPage = authUser
    ? activeTab === "world"
      ? tripDetailOpen && workspace
        ? <WorldPage workspace={workspace} currentUserId={authUser?.id ?? null} canManageMembers={!isTripArchived && isTripOwner} canEditItinerary={canEditItinerary} onArchivedAction={() => setArchivedActionNoticeOpen(true)} onInviteMember={() => setInviteOpen(true)} onChangeMemberRole={handleChangeMemberRole} onReorderActivities={handleReorderActivities} onBack={() => setTripDetailOpen(false)} onSettings={() => setTripSettingsOpen(true)} onReplan={setReplanActivity} onGenerate={openGenerateFlow} onRevise={() => setReviseOpen(true)} onOpenVersions={() => void openFeature("行程版本")} onAddActivity={(day) => setActivityEditor({ day })} onEditActivity={(activity) => setActivityEditor({ activity, day: activity.day })} onDeleteActivity={(activity) => void handleDeleteActivity(activity)} onAddExpense={(activity) => setExpenseActivity(activity)} onAddRecord={(activity) => setRecordActivity(activity)} />
        : <TripListPage trips={trips} onCreate={() => setCreateTripOpen(true)} onOpenTrip={(tripId) => void handleSelectTrip(tripId)} onOpenHistory={(tripId) => void handleOpenHistory(tripId)} />
      : activeTab === "lobby"
        ? lobbyDetailOpen && workspace
          ? <LobbyPage workspace={workspace} tripNote={tripNote} onBack={() => setLobbyDetailOpen(false)} onInvite={() => setInviteOpen(true)} onOpenLobby={() => void openLobby()} lobbyUnread={lobbyUnread} onPrivateChat={() => void openAgentChat()} onOpenTripNotes={() => setTripNotesOpen(true)} />
          : <LobbyListPage trips={trips} previews={lobbyPreviews} loading={lobbyListLoading} onOpenChat={(tripId) => void handleOpenTripChat(tripId)} onManage={(tripId) => void handleManageLobby(tripId)} />
        : activeTab === "functions"
          ? workspace
            ? <FunctionsPage workspace={workspace} onOpen={(label) => void openFeature(label)} onArchivedAction={showArchivedActionNotice} onCreateExpense={() => setExpenseActivity(null)} onCreateRecord={() => setRecordActivity(null)} />
            : noSelectedTrip
          : <HomePage user={authUser} loading={loading} personalPreferences={personalPreferences} onOpen={(label) => void openFeature(label)} onOpenPreferences={() => { setPersonalPreferences(readSavedText(personalPreferencesKey(authUser.id))); setPersonalPreferencesOpen(true); }} onUploadAvatar={(file) => void handleUploadAvatar(file)} onChangePassword={() => setPasswordOpen(true)} onLogout={handleLogout} />
    : <div className="page empty-workspace-page"><section className="itinerary-empty"><h1>请先登录</h1><p>登录后读取你的真实行程和协作数据。</p><button className="primary-button" onClick={() => setAuthOpen(true)}>登录或注册</button></section></div>;

  return (
    <AppShell activeTab={activeTab} onTabChange={handleTabChange}>
      {currentPage}
      {syncIndicatorVisible && <div className="sync-indicator">正在同步后端…</div>}
      {notice && <div className="toast" role="status">{notice}</div>}
      {archivedActionNoticeOpen && <ModalSheet title="温馨提示" onClose={() => setArchivedActionNoticeOpen(false)}>
        <p className="sheet-intro">已经结束的旅行不能修改哦</p>
        <button className="primary-button full-button" onClick={() => setArchivedActionNoticeOpen(false)}>知道了</button>
      </ModalSheet>}
      {conflict && <ModalSheet title="检测到同行者刚刚修改了行程" onClose={() => setConflict(null)}>
        <p className="sheet-intro">你正在{conflict.action}，但服务器已有更新。{conflict.submittedVersion && conflict.currentVersion ? `你基于第 ${conflict.submittedVersion} 版操作，当前已是第 ${conflict.currentVersion} 版。` : "为避免覆盖同行者内容，请先选择处理方式。"}</p>
        <div className="conflict-actions"><button className="primary-button full-button" disabled={loading || replanLoading} onClick={() => void handleConflictRetry()}>同步最新版并重试我的修改</button><button className="secondary-button full-button" onClick={() => { const tripId = workspace?.tripId; setConflict(null); if (tripId) void refreshWorkspace(tripId); }}>保留服务器最新版</button></div>
      </ModalSheet>}
      {workspace && tripSettingsOpen && <TripSettingsSheet tripTitle={workspace.title} isOwner={isTripOwner} archived={workspace.status === "finished"} loading={loading} onArchive={() => void handleArchiveTrip()} onDelete={() => void handleDeleteTrip()} onLeave={() => void handleLeaveTrip()} onClose={() => setTripSettingsOpen(false)} />}
      {workspace && inviteOpen && <ModalSheet title="邀请同行者" onClose={() => setInviteOpen(false)}>
        <div className="sheet-intro">搜索已有用户直接添加，或复制带有效期的分享链接。</div>
        <div className="invite-role-picker" aria-label="新成员权限">
          <button className={inviteRole === "editor" ? "is-active" : ""} onClick={() => setInviteRole("editor")}><strong>可编辑</strong><small>可共同调整行程</small></button>
          <button className={inviteRole === "viewer" ? "is-active" : ""} onClick={() => setInviteRole("viewer")}><strong>仅查看</strong><small>只能查看行程</small></button>
        </div>
        <input className="text-input search-input" value={inviteQuery} onChange={(event) => void searchInviteUsers(event.target.value)} placeholder="搜索用户名或昵称" />
        <div className="friend-list">{inviteOptions.map((friend) => <button key={friend.id} className="friend-row" onClick={() => void handleInvite(friend.id)} disabled={inviteLoading}><span className="friend-avatar">{friend.avatar_url ? <img src={apiAssetUrl(friend.avatar_url)} alt="" /> : friend.nickname.slice(0, 1)}</span><span><strong>{friend.nickname}</strong><small>{friend.description}</small></span><span className="friend-action">添加</span></button>)}</div>
        {inviteQuery && !inviteOptions.length && <div className="empty-chat">{inviteLoading ? "搜索中…" : "没有可添加的用户"}</div>}
        <button className="secondary-button full-button" onClick={() => void handleCopyInvite()}>复制邀请链接</button>
        <small className="invite-link-note">通过链接加入的成员默认为“可编辑”，加入后可在头像处调整。</small>
      </ModalSheet>}
      {workspace && generateOpen && <GenerationInputSheet questions={clarifyQuestions} loading={replanLoading} processingSteps={generationSteps} processingStep={generationStep} onRecognize={handleRecognizeGuideImage} onSubmit={(answer, guideText) => void handlePrepareGeneration(answer, guideText)} onClose={() => setGenerateOpen(false)} />}
      {workspace && reviseOpen && <TextActionSheet title="整体调整行程" label="你希望怎样修改？" placeholder="例如：降低预算，并把第二天下午改为室内活动" loading={replanLoading} submitText="生成调整候选" onSubmit={(value) => void handleRevise(value)} onClose={() => setReviseOpen(false)} required />}
      {replanActivity && <TextActionSheet title={`调整：${replanActivity.title}`} label="调整要求" placeholder="说明希望保留和改变的内容" loading={replanLoading} submitText="生成局部调整候选" onSubmit={(value) => void handleReplan(value)} onClose={() => setReplanActivity(null)} required />}
      {workspace && tripNotesOpen && <SaveTextSheet title="同行者的想法" intro="同一行程的成员都可以查看、编辑和保存；这些内容不会作为 Agent 的输入。" label="想法与备注" placeholder="例如：不赶早，留出拍照时间；周六中午想吃杭帮菜。" value={tripNote} onSave={handleSaveTripNote} onClose={() => setTripNotesOpen(false)} readOnly={isTripArchived} />}
      {workspace && guideOpen && <GuideImportSheet loading={loading} onRecognize={handleRecognizeGuideImage} onSubmit={(value) => void handleImportGuide(value)} onClose={() => setGuideOpen(false)} />}
      {workspace && activityEditor && <ActivityEditorSheet activity={activityEditor.activity} defaultDay={activityEditor.day} defaultOrder={Math.max(0, ...workspace.activities.filter((item) => item.day === activityEditor.day).map((item) => item.order)) + 1} loading={loading} onSubmit={(values) => void handleSaveActivity(values)} onClose={() => setActivityEditor(null)} />}
      {workspace && expenseActivity !== undefined && authUser && <ExpenseSheet activity={expenseActivity ?? undefined} members={workspace.members} currentUserId={authUser.id} loading={loading} onSubmit={(values) => void handleCreateExpense(values)} onClose={() => setExpenseActivity(undefined)} />}
      {workspace && recordActivity !== undefined && <HighlightSheet activity={recordActivity ?? undefined} loading={loading} onSubmit={(title, content, files) => void handleCreateRecord(title, content, files)} onClose={() => setRecordActivity(undefined)} />}
      {workspace && guideResult && <GuideCandidateSheet candidates={guideResult.candidates} dayCount={Math.max(1, Math.round((new Date(workspace.endDate).getTime() - new Date(workspace.startDate).getTime()) / 86400000) + 1)} activityCounts={workspace.activities.reduce<Record<number, number>>((counts, activity) => ({ ...counts, [activity.day]: (counts[activity.day] ?? 0) + 1 }), {})} loading={loading} onVerify={handleVerifyGuide} onApply={(placements) => void handleApplyGuide(placements)} onClose={() => setGuideResult(null)} />}
      {dataSheet && <DataSheet title={dataSheet.title} rows={dataSheet.rows} loading={dataLoading} onClose={() => setDataSheet(null)} />}
      {revisionSheet && <RevisionSheet revisions={revisionSheet} loading={dataLoading} onClose={() => setRevisionSheet(null)} />}
      {journalSheet && <TravelJournalSheet workspace={journalSheet.workspace} highlights={journalSheet.highlights} loading={dataLoading} onClose={() => setJournalSheet(null)} />}
      {chatMode && authUser && <ChatSheet mode={chatMode} title={chatMode === "lobby" && workspace ? workspace.title : workspace ? `${workspace.title} · Agent` : undefined} lobbyMessages={lobbyMessages} agentMessages={agentMessages} loading={chatLoading} currentUser={authUser} readOnly={isTripArchived} onSend={(content) => void handleChatSend(content)} onRetry={(message) => void handleLobbyRetry(message)} onRefresh={() => void (chatMode === "lobby" ? openLobby() : openAgentChat(workspace?.tripId))} onOpenCandidate={(data) => setReplanResult(candidateFromResponse(data as JsonObject))} onClose={() => setChatMode(null)} />}
      {replanResult && <CandidateSheet result={replanResult} loading={replanLoading} canApply={canEditItinerary} onApply={() => void handleApplyCandidate()} onDiscuss={() => { setReplanResult(null); void openAgentChat(workspace?.tripId); }} onClose={() => setReplanResult(null)} />}
      {passwordOpen && <PasswordSheet loading={loading} onSubmit={(currentPassword, newPassword) => void handleChangePassword(currentPassword, newPassword)} onClose={() => setPasswordOpen(false)} />}
      {personalPreferencesOpen && <SaveTextSheet title="旅行备忘录" intro="保存你想留下的旅行备忘内容，方便自己查看。" label="备忘内容" placeholder="例如：喜欢自然景观、少走路、不能吃辣、常用高铁出行。" value={personalPreferences} onSave={handleSavePersonalPreferences} onClose={() => setPersonalPreferencesOpen(false)} />}
      {authOpen && <AuthSheet mode={authMode} loading={authLoading} error={authError} onSubmit={(values) => void handleAuth(values)} onForgotPassword={handleForgotPassword} onToggle={() => { setAuthMode((mode) => mode === "login" ? "register" : "login"); setAuthError(""); }} />}
      {createTripOpen && authUser && <CreateTripSheet title={workspace ? "新建旅行" : "创建第一场旅行"} closable={Boolean(workspace)} onClose={() => setCreateTripOpen(false)} onSubmit={(values) => void handleCreateTrip(values)} />}
      <footer className="build-note">API：{apiConfig.baseUrl}{workspace ? ` · 行程 v${workspace.version}` : ""}</footer>
    </AppShell>
  );
}

function TextActionSheet({ title, label, placeholder, loading, processingSteps, processingStep = 0, submitText, required = false, onSubmit, onClose }: { title: string; label: string; placeholder: string; loading: boolean; processingSteps?: string[]; processingStep?: number; submitText: string; required?: boolean; onSubmit: (value: string) => void; onClose: () => void }) {
  const [value, setValue] = useState("");
  return <ModalSheet title={title} onClose={onClose} wide><form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit(value.trim()); }}><label className="field-label">{label}<textarea className="text-area" value={value} onChange={(event) => setValue(event.target.value)} placeholder={placeholder} required={required} /></label><button className="primary-button full-button" disabled={loading || (required && !value.trim())}>{loading ? <ProcessingLabel /> : submitText}</button>{processingSteps && loading && <ProcessingSteps steps={processingSteps} activeStep={processingStep} />}</form></ModalSheet>;
}

export default App;
