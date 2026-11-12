import { useCallback, useEffect, useState } from "react";
import { AppShell } from "./components/AppShell";
import { ActivityEditorSheet, type ActivityFormValues } from "./components/ActivityEditorSheet";
import { AuthSheet } from "./components/AuthSheet";
import { CandidateSheet } from "./components/CandidateSheet";
import { ChatSheet } from "./components/ChatSheet";
import { CreateTripSheet, type CreateTripValues } from "./components/CreateTripSheet";
import { DataSheet, type DataRow } from "./components/DataSheet";
import { ExpenseSheet, type ExpenseFormValues } from "./components/ExpenseSheet";
import { HighlightSheet } from "./components/HighlightSheet";
import { ModalSheet } from "./components/ModalSheet";
import { PasswordSheet } from "./components/PasswordSheet";
import { TripSettingsSheet } from "./components/TripSettingsSheet";
import {
  ApiError,
  api,
  apiConfig,
  mapApiWorkspace,
  type ApiRequirement,
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

function shareCodeFromPath() {
  const match = window.location.pathname.match(/^\/join\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
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

function App() {
  const [activeTab, setActiveTab] = useState<Tab>("world");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [requirements, setRequirements] = useState<ApiRequirement[]>([]);
  const [trips, setTrips] = useState<ApiTrip[]>([]);
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authOpen, setAuthOpen] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [createTripOpen, setCreateTripOpen] = useState(false);
  const [tripDetailOpen, setTripDetailOpen] = useState(false);
  const [lobbyDetailOpen, setLobbyDetailOpen] = useState(false);
  const [tripSettingsOpen, setTripSettingsOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteQuery, setInviteQuery] = useState("");
  const [inviteUsers, setInviteUsers] = useState<ApiUserSearch[]>([]);
  const [inviteLoading, setInviteLoading] = useState(false);
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
  const [reviseOpen, setReviseOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideResult, setGuideResult] = useState<{ runId: number; candidates: JsonObject[]; selected: string[] } | null>(null);
  const [requirementsOpen, setRequirementsOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [dataSheet, setDataSheet] = useState<{ title: string; rows: DataRow[] } | null>(null);
  const [dataLoading, setDataLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  const handleUnauthorized = useCallback(() => {
    api.auth.logout();
    localStorage.removeItem("travel-agent-selected-trip");
    setAuthUser(null);
    setWorkspace(null);
    setTrips([]);
    setAuthOpen(true);
  }, []);

  const refreshWorkspace = useCallback(async (preferredTripId?: number) => {
    setLoading(true);
    try {
      const user = await api.auth.me();
      setAuthUser(user);
      let joinedTripId: number | undefined;
      const shareCode = shareCodeFromPath();
      if (shareCode) {
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
      const { items } = await api.trips.list({ pageSize: 100 });
      setTrips(items);
      const requestedId = joinedTripId ?? preferredTripId ?? (Number(localStorage.getItem("travel-agent-selected-trip")) || 0);
      const selectedTrip = items.find((trip) => trip.id === requestedId) ?? items.find((trip) => trip.status !== "finished") ?? items[0];
      if (!selectedTrip) {
        setWorkspace(null);
        setRequirements([]);
        return null;
      }
      localStorage.setItem("travel-agent-selected-trip", String(selectedTrip.id));
      const [detail, members, requirementItems] = await Promise.all([
        api.trips.get(selectedTrip.id),
        api.members.list(selectedTrip.id),
        api.requirements.list(selectedTrip.id),
      ]);
      setRequirements(requirementItems);
      const mappedWorkspace = mapApiWorkspace(detail, members, requirementItems, items.filter((trip) => trip.status === "finished" && trip.id !== selectedTrip.id));
      setWorkspace(mappedWorkspace);
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
    if (activeTab !== "lobby" || !authUser || !trips.length) {
      if (!trips.length) setLobbyPreviews([]);
      return;
    }
    let cancelled = false;
    setLobbyListLoading(true);
    void Promise.all(trips.map(async (trip) => {
      try {
        const result = await api.collaboration.lobby.list(trip.id);
        const latest = result.items.at(-1);
        return { tripId: trip.id, lastMessage: latest?.content ?? "", lastAt: latest?.createdAt ?? null, unread: result.unread_count } satisfies LobbyPreview;
      } catch {
        return { tripId: trip.id, lastMessage: "消息暂时无法读取", lastAt: null, unread: 0 } satisfies LobbyPreview;
      }
    })).then((items) => {
      if (!cancelled) setLobbyPreviews(items);
    }).finally(() => {
      if (!cancelled) setLobbyListLoading(false);
    });
    return () => { cancelled = true; };
  }, [activeTab, authUser, trips]);

  const handleAuth = async (values: { username: string; password: string; nickname: string }) => {
    setAuthLoading(true);
    setAuthError("");
    try {
      const result = authMode === "login" ? await api.auth.login(values.username, values.password) : await api.auth.register(values.username, values.password, values.nickname);
      setAuthUser(result.user);
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

  const handleLogout = () => {
    api.auth.logout();
    localStorage.removeItem("travel-agent-selected-trip");
    setWorkspace(null);
    setTrips([]);
    setAuthUser(null);
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
      setActiveTab("world");
      setTripDetailOpen(true);
      setNotice("行程已创建，请补充要求后让 Agent 生成路线");
    } catch (error) {
      setNotice(`创建行程失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectTrip = async (tripId: number) => {
    setActiveTab("world");
    await refreshWorkspace(tripId);
    setTripDetailOpen(true);
    setNotice("已切换旅行");
  };

  const handleOpenHistory = async (tripId: number) => {
    const selectedWorkspace = await refreshWorkspace(tripId);
    if (!selectedWorkspace) return;
    setTripDetailOpen(false);
    setActiveTab("functions");
    await openFeature("旅行手帐", selectedWorkspace);
  };

  const isTripOwner = Boolean(workspace && workspace.members.some((member) => member.id === authUser?.id && member.role === "房主"));

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

  const openAgentChat = async () => {
    if (!workspace) return;
    setChatMode("agent");
    setChatLoading(true);
    try {
      const conversation = await api.collaboration.agent.conversation(workspace.tripId);
      setAgentConversationId(conversation.id);
      setAgentMessages(await api.collaboration.agent.messages(conversation.id));
    } catch (error) {
      setNotice(`读取 Agent 私聊失败：${(error as Error).message}`);
    } finally {
      setChatLoading(false);
    }
  };

  const handleChatSend = async (content: string) => {
    if (!chatMode || !workspace) return;
    setChatLoading(true);
    try {
      if (chatMode === "lobby") {
        const created = await api.collaboration.lobby.send(workspace.tripId, content, content.includes("@Agent"));
        setLobbyMessages((items) => [...items, ...created]);
      } else if (agentConversationId) {
        const result = await api.collaboration.agent.send(agentConversationId, content);
        setAgentMessages((items) => [...items, result.userMessage, result.agentMessage]);
      }
    } catch (error) {
      setNotice(`发送失败：${(error as Error).message}`);
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
      await api.members.invite(workspace.tripId, userId);
      setNotice("成员已加入旅行");
      await refreshWorkspace(workspace.tripId);
    } catch (error) {
      setNotice(`邀请失败：${(error as Error).message}`);
    }
  };

  const handleCopyInvite = async () => {
    if (!workspace) return;
    try {
      const result = await api.members.createShareCode(workspace.tripId);
      await navigator.clipboard.writeText(`${window.location.origin}/join/${result.share_code}`);
      setNotice(`邀请链接已复制，有效期至 ${new Date(result.expires_at).toLocaleString("zh-CN")}`);
    } catch (error) {
      setNotice(`生成邀请链接失败：${(error as Error).message}`);
    }
  };

  const handleGenerate = async (requirementsText: string) => {
    if (!workspace) return;
    setReplanLoading(true);
    try {
      await api.ai.generate(workspace.tripId, requirementsText || undefined);
      setGenerateOpen(false);
      await refreshWorkspace(workspace.tripId);
      setNotice("Agent 已生成并保存初始行程");
    } catch (error) {
      setNotice(`生成行程失败：${(error as Error).message}`);
    } finally {
      setReplanLoading(false);
    }
  };

  const handleRevise = async (instruction: string) => {
    if (!workspace) return;
    setReplanLoading(true);
    try {
      const result = await api.ai.revise({ trip_id: workspace.tripId, changed_constraints: {}, user_instruction: instruction, trip_version: workspace.version });
      setReviseOpen(false);
      setReplanResult(candidateFromResponse(result));
    } catch (error) {
      setNotice(`生成整体修订失败：${(error as Error).message}`);
    } finally {
      setReplanLoading(false);
    }
  };

  const handleReplan = async (instruction: string) => {
    if (!replanActivity || !workspace) return;
    setReplanLoading(true);
    try {
      const result = await api.ai.replan({ trip_id: workspace.tripId, day_number: replanActivity.day, adjustment_requirements: instruction, trip_version: workspace.version, after_time: replanActivity.time === "待定" ? undefined : replanActivity.time });
      setReplanActivity(null);
      setReplanResult(result);
    } catch (error) {
      setNotice(`生成调整建议失败：${(error as Error).message}`);
    } finally {
      setReplanLoading(false);
    }
  };

  const handleApplyCandidate = async () => {
    if (!replanResult || !workspace) return;
    setReplanLoading(true);
    try {
      await api.ai.applyRun(workspace.tripId, replanResult.aiRunId, workspace.version);
      setReplanResult(null);
      await refreshWorkspace(workspace.tripId);
      setNotice("调整已应用，行程已刷新");
    } catch (error) {
      setNotice(`应用调整失败：${(error as Error).message}`);
    } finally {
      setReplanLoading(false);
    }
  };

  const handleSaveActivity = async (values: ActivityFormValues) => {
    if (!workspace || !activityEditor) return;
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
      setNotice(`保存活动失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteActivity = async (activity: Activity) => {
    if (!workspace || !window.confirm(`确认删除“${activity.title}”吗？该操作会生成版本记录。`)) return;
    setLoading(true);
    try {
      await api.activities.remove(workspace.tripId, activity.id, workspace.version);
      await refreshWorkspace(workspace.tripId);
      setNotice("活动已删除");
    } catch (error) {
      setNotice(`删除活动失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateExpense = async (values: ExpenseFormValues) => {
    if (!workspace) return;
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
    if (!workspace) return;
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

  const handleSaveRequirement = async (contentText: string, sharedSummary: string) => {
    if (!workspace) return;
    setLoading(true);
    try {
      await api.requirements.saveMine(workspace.tripId, { notes: contentText });
      if (sharedSummary.trim()) await api.requirements.shareMine(workspace.tripId, sharedSummary.trim());
      else await api.requirements.unshareMine(workspace.tripId);
      setRequirementsOpen(false);
      await refreshWorkspace(workspace.tripId);
      setNotice("旅行需求已保存");
    } catch (error) {
      setNotice(`保存需求失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleImportGuide = async (text: string) => {
    if (!workspace) return;
    setLoading(true);
    try {
      const result = await api.ai.importGuide(workspace.tripId, text);
      const candidates = Array.isArray(result.candidates) ? result.candidates as JsonObject[] : [];
      setGuideOpen(false);
      setGuideResult({ runId: Number(result.ai_run_id), candidates, selected: [] });
    } catch (error) {
      setNotice(`攻略导入失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyGuide = async () => {
    if (!workspace || !guideResult?.selected.length) return;
    setLoading(true);
    try {
      await api.ai.applyGuideRun(workspace.tripId, guideResult.runId, workspace.version, guideResult.selected);
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
    if (!targetWorkspace) return;
    if (label === "和 Agent 聊聊" || label === "上次的对话") {
      await openAgentChat();
      return;
    }
    if (label === "攻略导入") {
      setGuideOpen(true);
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
      } else if (label === "旅行手帐") {
        const highlights = await api.highlights.list(targetWorkspace.tripId);
        const rows: DataRow[] = [{ title: targetWorkspace.title, description: `${targetWorkspace.city} · ${targetWorkspace.startDate} 至 ${targetWorkspace.endDate}`, meta: `${targetWorkspace.travelerCount} 人 · ${targetWorkspace.activities.length} 项活动` }];
        rows.push(...highlights.map((item) => {
          const activity = targetWorkspace.activities.find((candidate) => candidate.id === item.activity_id);
          const source = activity ? `关联活动：${activity.title}` : "旅行公共记录";
          return { title: item.title, description: item.content ?? "暂无文字记录", meta: `${source} · ${item.images.length} 张图片 · ${new Date(item.occurred_at ?? item.created_at).toLocaleString("zh-CN")}` };
        }));
        setDataSheet({ title: `旅行手帐 · ${targetWorkspace.title}`, rows });
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

  const currentRequirement = requirements.find((item) => item.user_id === authUser?.id);
  const inviteOptions = inviteUsers.filter((user) => user.can_invite).map((user) => ({ ...user, description: user.username }));

  const noSelectedTrip = <div className="page empty-workspace-page"><section className="itinerary-empty"><h1>请先选择行程</h1><p>前往行程列表选择或新建一场旅行。</p><button className="primary-button" onClick={() => { setActiveTab("world"); setTripDetailOpen(false); }}>查看行程列表</button></section></div>;
  const currentPage = authUser
    ? activeTab === "world"
      ? tripDetailOpen && workspace
        ? <WorldPage workspace={workspace} onBack={() => setTripDetailOpen(false)} onSettings={() => setTripSettingsOpen(true)} onReplan={setReplanActivity} onGenerate={() => setGenerateOpen(true)} onRevise={() => setReviseOpen(true)} onOpenVersions={() => void openFeature("行程版本")} onAddActivity={(day) => setActivityEditor({ day })} onEditActivity={(activity) => setActivityEditor({ activity, day: activity.day })} onDeleteActivity={(activity) => void handleDeleteActivity(activity)} onAddExpense={(activity) => setExpenseActivity(activity)} onAddRecord={(activity) => setRecordActivity(activity)} />
        : <TripListPage trips={trips} onCreate={() => setCreateTripOpen(true)} onOpenTrip={(tripId) => void handleSelectTrip(tripId)} onOpenHistory={(tripId) => void handleOpenHistory(tripId)} />
      : activeTab === "lobby"
        ? lobbyDetailOpen && workspace
          ? <LobbyPage workspace={workspace} onBack={() => setLobbyDetailOpen(false)} onInvite={() => setInviteOpen(true)} onOpenLobby={() => void openLobby()} lobbyUnread={lobbyUnread} onPrivateChat={() => void openAgentChat()} onOpenRequirements={() => setRequirementsOpen(true)} />
          : <LobbyListPage trips={trips} previews={lobbyPreviews} loading={lobbyListLoading} onOpenChat={(tripId) => void handleOpenTripChat(tripId)} onManage={(tripId) => void handleManageLobby(tripId)} />
        : activeTab === "functions"
          ? workspace
            ? <FunctionsPage workspace={workspace} onOpen={(label) => void openFeature(label)} onCreateExpense={() => setExpenseActivity(null)} onCreateRecord={() => setRecordActivity(null)} />
            : noSelectedTrip
          : <HomePage user={authUser} loading={loading} onOpen={(label) => void openFeature(label)} onPrivateChat={() => void openAgentChat()} onUploadAvatar={(file) => void handleUploadAvatar(file)} onChangePassword={() => setPasswordOpen(true)} onLogout={handleLogout} />
    : <div className="page empty-workspace-page"><section className="itinerary-empty"><h1>请先登录</h1><p>登录后读取你的真实行程和协作数据。</p><button className="primary-button" onClick={() => setAuthOpen(true)}>登录或注册</button></section></div>;

  return (
    <AppShell activeTab={activeTab} onTabChange={handleTabChange}>
      {currentPage}
      {loading && <div className="sync-indicator">正在同步后端…</div>}
      {notice && <div className="toast" role="status">{notice}</div>}
      {workspace && tripSettingsOpen && <TripSettingsSheet tripTitle={workspace.title} isOwner={isTripOwner} archived={workspace.status === "finished"} loading={loading} onArchive={() => void handleArchiveTrip()} onDelete={() => void handleDeleteTrip()} onLeave={() => void handleLeaveTrip()} onClose={() => setTripSettingsOpen(false)} />}
      {workspace && inviteOpen && <ModalSheet title="邀请同行者" onClose={() => setInviteOpen(false)}>
        <div className="sheet-intro">搜索已有用户直接添加，或复制带有效期的分享链接。</div>
        <input className="text-input search-input" value={inviteQuery} onChange={(event) => void searchInviteUsers(event.target.value)} placeholder="搜索用户名或昵称" />
        <div className="friend-list">{inviteOptions.map((friend) => <button key={friend.id} className="friend-row" onClick={() => void handleInvite(friend.id)} disabled={inviteLoading}><span className="friend-avatar">{friend.nickname.slice(0, 1)}</span><span><strong>{friend.nickname}</strong><small>{friend.description}</small></span><span className="friend-action">添加</span></button>)}</div>
        {inviteQuery && !inviteOptions.length && <div className="empty-chat">{inviteLoading ? "搜索中…" : "没有可添加的用户"}</div>}
        <button className="secondary-button full-button" onClick={() => void handleCopyInvite()}>复制分享链接</button>
      </ModalSheet>}
      {workspace && generateOpen && <TextActionSheet title="让 Agent 生成行程" label="补充要求（可选）" placeholder="例如：不赶早、喜欢博物馆、每天步行不超过两小时" loading={replanLoading} submitText="生成并保存初始行程" onSubmit={(value) => void handleGenerate(value)} onClose={() => setGenerateOpen(false)} />}
      {workspace && reviseOpen && <TextActionSheet title="整体调整行程" label="你希望怎样修改？" placeholder="例如：降低预算，并把第二天下午改为室内活动" loading={replanLoading} submitText="生成调整候选" onSubmit={(value) => void handleRevise(value)} onClose={() => setReviseOpen(false)} required />}
      {replanActivity && <TextActionSheet title={`调整：${replanActivity.title}`} label="调整要求" placeholder="说明希望保留和改变的内容" loading={replanLoading} submitText="生成局部调整候选" onSubmit={(value) => void handleReplan(value)} onClose={() => setReplanActivity(null)} required />}
      {workspace && requirementsOpen && <RequirementSheet initialContent={String(currentRequirement?.content?.notes ?? "")} initialSummary={currentRequirement?.shared_summary ?? ""} loading={loading} onSubmit={(content, summary) => void handleSaveRequirement(content, summary)} onClose={() => setRequirementsOpen(false)} />}
      {workspace && guideOpen && <TextActionSheet title="导入攻略" label="粘贴攻略文字" placeholder="粘贴文章、笔记或推荐清单，Agent 会提取候选活动" loading={loading} submitText="提取候选活动" onSubmit={(value) => void handleImportGuide(value)} onClose={() => setGuideOpen(false)} required />}
      {workspace && activityEditor && <ActivityEditorSheet activity={activityEditor.activity} defaultDay={activityEditor.day} defaultOrder={Math.max(0, ...workspace.activities.filter((item) => item.day === activityEditor.day).map((item) => item.order)) + 1} loading={loading} onSubmit={(values) => void handleSaveActivity(values)} onClose={() => setActivityEditor(null)} />}
      {workspace && expenseActivity !== undefined && authUser && <ExpenseSheet activity={expenseActivity ?? undefined} members={workspace.members} currentUserId={authUser.id} loading={loading} onSubmit={(values) => void handleCreateExpense(values)} onClose={() => setExpenseActivity(undefined)} />}
      {workspace && recordActivity !== undefined && <HighlightSheet activity={recordActivity ?? undefined} loading={loading} onSubmit={(title, content, files) => void handleCreateRecord(title, content, files)} onClose={() => setRecordActivity(undefined)} />}
      {workspace && guideResult && <ModalSheet title="选择攻略候选" onClose={() => setGuideResult(null)} wide><div className="candidate-choice-list">{guideResult.candidates.map((candidate) => { const id = String(candidate.candidate_id ?? ""); const checked = guideResult.selected.includes(id); return <label className="candidate-choice" key={id}><input type="checkbox" checked={checked} onChange={() => setGuideResult((current) => current ? { ...current, selected: checked ? current.selected.filter((item) => item !== id) : [...current.selected, id] } : null)} /><span><strong>{String(candidate.title ?? "未命名候选")}</strong><small>{String(candidate.excerpt ?? "")}</small></span></label>; })}</div><button className="primary-button full-button" disabled={!guideResult.selected.length || loading} onClick={() => void handleApplyGuide()}>加入选中的活动</button></ModalSheet>}
      {replanResult && <CandidateSheet result={replanResult} loading={replanLoading} onApply={() => void handleApplyCandidate()} onClose={() => setReplanResult(null)} />}
      {dataSheet && <DataSheet title={dataSheet.title} rows={dataSheet.rows} loading={dataLoading} onClose={() => setDataSheet(null)} />}
      {chatMode && <ChatSheet mode={chatMode} title={chatMode === "lobby" && workspace ? workspace.title : undefined} lobbyMessages={lobbyMessages} agentMessages={agentMessages} loading={chatLoading} onSend={(content) => void handleChatSend(content)} onRefresh={() => void (chatMode === "lobby" ? openLobby() : openAgentChat())} onClose={() => setChatMode(null)} />}
      {passwordOpen && <PasswordSheet loading={loading} onSubmit={(currentPassword, newPassword) => void handleChangePassword(currentPassword, newPassword)} onClose={() => setPasswordOpen(false)} />}
      {authOpen && <AuthSheet mode={authMode} loading={authLoading} error={authError} onSubmit={(values) => void handleAuth(values)} onToggle={() => { setAuthMode((mode) => mode === "login" ? "register" : "login"); setAuthError(""); }} />}
      {createTripOpen && authUser && <CreateTripSheet title={workspace ? "新建旅行" : "创建第一场旅行"} closable={Boolean(workspace)} onClose={() => setCreateTripOpen(false)} onSubmit={(values) => void handleCreateTrip(values)} />}
      <footer className="build-note">API：{apiConfig.baseUrl}{workspace ? ` · 行程 v${workspace.version}` : ""}</footer>
    </AppShell>
  );
}

function TextActionSheet({ title, label, placeholder, loading, submitText, required = false, onSubmit, onClose }: { title: string; label: string; placeholder: string; loading: boolean; submitText: string; required?: boolean; onSubmit: (value: string) => void; onClose: () => void }) {
  const [value, setValue] = useState("");
  return <ModalSheet title={title} onClose={onClose} wide><form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit(value.trim()); }}><label className="field-label">{label}<textarea className="text-area" value={value} onChange={(event) => setValue(event.target.value)} placeholder={placeholder} required={required} /></label><button className="primary-button full-button" disabled={loading || (required && !value.trim())}>{loading ? "处理中…" : submitText}</button></form></ModalSheet>;
}

function RequirementSheet({ initialContent, initialSummary, loading, onSubmit, onClose }: { initialContent: string; initialSummary: string; loading: boolean; onSubmit: (content: string, summary: string) => void; onClose: () => void }) {
  const [content, setContent] = useState(initialContent);
  const [summary, setSummary] = useState(initialSummary);
  return <ModalSheet title="我的旅行需求" onClose={onClose} wide><form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit(content.trim(), summary.trim()); }}><p className="sheet-intro">完整需求仅你本人和代填者可见；只有下方共享摘要会展示给同行者。</p><label className="field-label">私密需求<textarea className="text-area" value={content} onChange={(event) => setContent(event.target.value)} placeholder="饮食、体力、作息及其他个人要求" required /></label><label className="field-label">共享摘要<textarea className="text-area compact-text-area" value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="可选；留空代表不向同行者共享" /></label><button className="primary-button full-button" disabled={loading}>{loading ? "保存中…" : "保存需求"}</button></form></ModalSheet>;
}

export default App;
