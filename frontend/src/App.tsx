import { useCallback, useEffect, useState } from "react";
import { AppShell } from "./components/AppShell";
import { AuthSheet } from "./components/AuthSheet";
import { CandidateSheet } from "./components/CandidateSheet";
import { ChatSheet } from "./components/ChatSheet";
import { CreateTripSheet } from "./components/CreateTripSheet";
import { DataSheet, type DataRow } from "./components/DataSheet";
import { ModalSheet } from "./components/ModalSheet";
import { TripSettingsSheet } from "./components/TripSettingsSheet";
import { TripSwitcherSheet, type TripOption } from "./components/TripSwitcherSheet";
import { api, apiConfig, mapApiWorkspace, type ApiTrip, type ApiUserSearch } from "./api/client";
import { mockWorkspace } from "./mocks/data";
import { FunctionsPage } from "./pages/FunctionsPage";
import { HomePage } from "./pages/HomePage";
import { LobbyPage } from "./pages/LobbyPage";
import { WorldPage } from "./pages/WorldPage";
import type { Activity, AgentMessage, AuthUser, LobbyMessage, ReplanResult, Tab, Workspace } from "./types";

const friends = [
  { id: 21, name: "乔乔", description: "杭州同行者" },
  { id: 22, name: "阿澈", description: "已在本次旅行" },
  { id: 23, name: "小满", description: "最近联系" },
];

const mockLobbyMessages: LobbyMessage[] = [
  { id: 1, tripId: 1, senderId: 2, senderNickname: "阿澈", content: "周六中午要不要在西湖附近吃？", kind: "user", visibility: "trip", replyToId: null, createdAt: new Date().toISOString() },
  { id: 2, tripId: 1, senderId: null, senderNickname: null, content: "可以保留湖边午餐，我会根据大家的需求调整下午路线。", kind: "agent", visibility: "trip", replyToId: 1, createdAt: new Date().toISOString() },
];

const mockAgentMessages: AgentMessage[] = [
  { id: 1, conversationId: 1, role: "assistant", content: "你好，可以私下告诉我你的偏好和需要避开的事项。", status: "succeeded", createdAt: new Date().toISOString() },
];

function formatDateRange(start: string, end: string) {
  if (!start || !end) return "日期待定";
  return `${start.slice(5).replace("-", "月")}日—${end.slice(5).replace("-", "月")}日`;
}

function hasToken() {
  return Boolean(localStorage.getItem("travel-agent-token") || import.meta.env.VITE_ACCESS_TOKEN);
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>("lobby");
  const [workspace, setWorkspace] = useState<Workspace>(mockWorkspace);
  const [trips, setTrips] = useState<ApiTrip[]>([]);
  const [selectedTripId, setSelectedTripId] = useState<number>(() => Number(localStorage.getItem("travel-agent-selected-trip")) || mockWorkspace.tripId);
  const [hasWorkspace, setHasWorkspace] = useState(apiConfig.useMocks);
  const [authUser, setAuthUser] = useState<AuthUser | null>(apiConfig.useMocks ? { id: 1, username: "mock", nickname: "林予" } : null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authOpen, setAuthOpen] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [createTripOpen, setCreateTripOpen] = useState(false);
  const [tripSwitcherOpen, setTripSwitcherOpen] = useState(false);
  const [tripSettingsOpen, setTripSettingsOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteQuery, setInviteQuery] = useState("");
  const [inviteUsers, setInviteUsers] = useState<ApiUserSearch[]>([]);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [chatMode, setChatMode] = useState<"lobby" | "agent" | null>(null);
  const [lobbyMessages, setLobbyMessages] = useState<LobbyMessage[]>(apiConfig.useMocks ? mockLobbyMessages : []);
  const [lobbyUnread, setLobbyUnread] = useState(0);
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>(apiConfig.useMocks ? mockAgentMessages : []);
  const [agentConversationId, setAgentConversationId] = useState<number | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [replanActivity, setReplanActivity] = useState<Activity | null>(null);
  const [replanResult, setReplanResult] = useState<ReplanResult | null>(null);
  const [replanLoading, setReplanLoading] = useState(false);
  const [dataSheet, setDataSheet] = useState<{ title: string; rows: DataRow[] } | null>(null);
  const [dataLoading, setDataLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  const refreshWorkspace = useCallback(async (preferredTripId?: number) => {
    if (apiConfig.useMocks) return;
    setLoading(true);
    try {
      const user = await api.auth.me();
      setAuthUser(user);
      const { items } = await api.trips.list();
      setTrips(items);
      const requestedId = preferredTripId ?? (Number(localStorage.getItem("travel-agent-selected-trip")) || null);
      const selectedTrip = items.find((trip) => trip.id === requestedId) ?? items[0];
      if (!selectedTrip) {
        setHasWorkspace(false);
        setCreateTripOpen(true);
        return;
      }
      setSelectedTripId(selectedTrip.id);
      localStorage.setItem("travel-agent-selected-trip", String(selectedTrip.id));
      const [detail, members] = await Promise.all([api.trips.get(selectedTrip.id), api.members.list(selectedTrip.id)]);
      setWorkspace(mapApiWorkspace(detail, members, mockWorkspace.members));
      setHasWorkspace(true);
      setCreateTripOpen(false);
    } catch (error) {
      setNotice(`后端连接失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (apiConfig.useMocks) return;
    if (!hasToken()) {
      setAuthOpen(true);
      return;
    }
    void refreshWorkspace();
  }, [refreshWorkspace]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const handleAuth = async (values: { username: string; password: string; nickname: string }) => {
    setAuthLoading(true);
    setAuthError("");
    try {
      const result = authMode === "login"
        ? await api.auth.login(values.username, values.password)
        : await api.auth.register(values.username, values.password, values.nickname);
      setAuthUser(result.user);
      setAuthOpen(false);
      setNotice("登录成功，正在读取真实行程");
      await refreshWorkspace();
    } catch (error) {
      setAuthError((error as Error).message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleCreateTrip = async (values: { title: string; city: string; start_date: string; end_date: string }) => {
    setLoading(true);
    try {
      const createdTrip = await api.trips.create({ ...values, traveler_count: 1, preferences: {}, constraints: {} });
      setNotice("行程已创建");
      setCreateTripOpen(false);
      await refreshWorkspace(createdTrip.id);
    } catch (error) {
      setNotice(`创建行程失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectTrip = async (tripId: number) => {
    setSelectedTripId(tripId);
    localStorage.setItem("travel-agent-selected-trip", String(tripId));
    setTripSwitcherOpen(false);
    setActiveTab("lobby");
    await refreshWorkspace(tripId);
    setNotice("已切换旅行");
  };

  const isTripOwner = apiConfig.useMocks || workspace.members.some((member) => member.id === authUser?.id && member.role === "房主");

  const handleArchiveTrip = async () => {
    if (!window.confirm("结束后会保留旅行记录，确认归档这场旅行吗？")) return;
    if (apiConfig.useMocks) {
      setTripSettingsOpen(false);
      setNotice("Mock 模式未调用后端");
      return;
    }
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
    if (!window.confirm("删除后无法恢复，确认删除这场旅行吗？")) return;
    if (apiConfig.useMocks) {
      setTripSettingsOpen(false);
      setNotice("Mock 模式未调用后端");
      return;
    }
    setLoading(true);
    try {
      await api.trips.remove(workspace.tripId, workspace.version);
      localStorage.removeItem("travel-agent-selected-trip");
      setTripSettingsOpen(false);
      await refreshWorkspace();
      setNotice("旅行已删除");
    } catch (error) {
      setNotice(`删除旅行失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleLeaveTrip = async () => {
    if (isTripOwner) {
      setNotice("房主不能退出自己的旅行，请先结束或删除");
      return;
    }
    if (!window.confirm("退出后将无法继续查看这场旅行，确认退出吗？")) return;
    if (apiConfig.useMocks) {
      setTripSettingsOpen(false);
      setNotice("Mock 模式未调用后端");
      return;
    }
    setLoading(true);
    try {
      await api.members.leave(workspace.tripId);
      localStorage.removeItem("travel-agent-selected-trip");
      setTripSettingsOpen(false);
      await refreshWorkspace();
      setNotice("已退出旅行");
    } catch (error) {
      setNotice(`退出旅行失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const openLobby = async () => {
    setChatMode("lobby");
    if (apiConfig.useMocks || !hasWorkspace) return;
    setChatLoading(true);
    try {
      const result = await api.collaboration.lobby.list(workspace.tripId);
      setLobbyMessages(result.items);
      setLobbyUnread(result.unread_count);
      const latest = result.items.at(-1);
      if (latest) await api.collaboration.lobby.markRead(workspace.tripId, latest.id);
    } catch (error) {
      setNotice(`读取大厅消息失败：${(error as Error).message}`);
    } finally {
      setChatLoading(false);
    }
  };

  const openAgentChat = async () => {
    setChatMode("agent");
    if (apiConfig.useMocks || !hasWorkspace) return;
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
    if (!chatMode) return;
    if (apiConfig.useMocks) {
      const id = Date.now();
      if (chatMode === "lobby") {
        const userMessage: LobbyMessage = { id, tripId: workspace.tripId, senderId: 1, senderNickname: "我", content, kind: "user", visibility: "trip", replyToId: null, createdAt: new Date().toISOString() };
        setLobbyMessages((items) => [...items, userMessage, ...(content.includes("@Agent") ? [{ ...userMessage, id: id + 1, senderId: null, senderNickname: null, kind: "agent", content: "我会结合大家的需求给出一版调整建议。" }] : [])]);
      } else {
        setAgentMessages((items) => [...items, { id, conversationId: 1, role: "user", content, status: "succeeded", createdAt: new Date().toISOString() }, { id: id + 1, conversationId: 1, role: "assistant", content: "我记下了，会在需要公开建议时只发布必要的行程调整。", status: "succeeded", createdAt: new Date().toISOString() }]);
      }
      return;
    }
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
    if (apiConfig.useMocks || !query.trim()) return;
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
    if (apiConfig.useMocks) {
      setNotice("已发送邀请（Mock）");
      return;
    }
    try {
      await api.members.invite(workspace.tripId, userId);
      setNotice("邀请已发送");
      await refreshWorkspace();
    } catch (error) {
      setNotice(`邀请失败：${(error as Error).message}`);
    }
  };

  const handleCopyInvite = async () => {
    try {
      const code = apiConfig.useMocks ? "SHANXING-DEMO" : (await api.members.createShareCode(workspace.tripId)).share_code;
      await navigator.clipboard?.writeText(`${window.location.origin}/join/${code}`);
      setNotice("邀请链接已复制");
    } catch (error) {
      setNotice(`生成邀请链接失败：${(error as Error).message}`);
    }
  };

  const handleReplan = async (instruction: string) => {
    if (!replanActivity) return;
    if (apiConfig.useMocks) {
      setReplanActivity(null);
      setReplanResult({ aiRunId: 0, summary: "乘车去湖边喝茶，其他三站照旧。", baseVersion: workspace.version, changedItems: ["14:00 湖滨漫步 → 湖边喝茶", "减少连续步行时间"], keptItems: ["上午浙博孤山馆", "12:00 湖畔午餐", "18:30 晚餐"] });
      return;
    }
    setReplanLoading(true);
    try {
      const result = await api.ai.replan({ trip_id: workspace.tripId, day_number: replanActivity.day, adjustment_requirements: instruction, trip_version: workspace.version, after_time: replanActivity.time });
      setReplanActivity(null);
      setReplanResult(result);
    } catch (error) {
      setNotice(`生成调整建议失败：${(error as Error).message}`);
    } finally {
      setReplanLoading(false);
    }
  };

  const handleApplyReplan = async () => {
    if (!replanResult) return;
    if (apiConfig.useMocks || !replanResult.aiRunId) {
      setReplanResult(null);
      setNotice("已应用调整建议（Mock）");
      return;
    }
    setReplanLoading(true);
    try {
      await api.ai.applyRun(workspace.tripId, replanResult.aiRunId, workspace.version);
      setReplanResult(null);
      await refreshWorkspace();
      setNotice("调整已应用，行程已刷新");
    } catch (error) {
      setNotice(`应用调整失败：${(error as Error).message}`);
    } finally {
      setReplanLoading(false);
    }
  };

  const openFeature = async (label: string) => {
    if (label === "和 Agent 聊聊" || label === "上次的对话") {
      await openAgentChat();
      return;
    }
    if (apiConfig.useMocks) {
      setNotice(`${label} 当前使用 Mock 数据`);
      return;
    }
    setDataSheet({ title: label, rows: [] });
    setDataLoading(true);
    try {
      if (label === "行程版本") {
        const revisions = await api.trips.revisions(workspace.tripId);
        setDataSheet({ title: label, rows: revisions.map((revision) => ({ title: `第 ${String(revision.version)} 版 · ${String(revision.action)}`, description: String(revision.summary ?? "已记录一次行程变化"), meta: String(revision.created_at ?? "") })) });
      } else if (label === "记账与分账") {
        const expenses = await api.expenses.list(workspace.tripId);
        setDataSheet({ title: label, rows: expenses.map((expense) => ({ title: `${String(expense.title ?? "账单")} · ¥${String(expense.amount ?? "0")}`, description: `${String(expense.payer_nickname ?? "成员")} 付款 · ${expense.is_settled ? "已结算" : "待分摊"}`, meta: `${Array.isArray(expense.splits) ? expense.splits.length : 0} 位成员参与` })) });
      } else if (label === "旅行高光") {
        const highlights = await api.highlights.list(workspace.tripId);
        setDataSheet({ title: label, rows: highlights.map((highlight) => ({ title: String(highlight.title ?? "旅行高光"), description: String(highlight.content ?? "暂无描述"), meta: String(highlight.occurred_at ?? highlight.created_at ?? "") })) });
      } else if (label === "记忆簿") {
        const memories = await api.memories.list();
        setDataSheet({ title: label, rows: memories.map((memory) => ({ title: String(memory.title ?? "未命名记忆"), description: String(memory.content ?? ""), meta: String(memory.visibility ?? "private") === "shared" ? "已授权共享" : "仅自己可见" })) });
      } else if (label === "设置") {
        const settings = await api.users.settings();
        setDataSheet({ title: label, rows: [{ title: "记忆使用", description: settings.memory_enabled ? "Agent 可以使用已授权记忆" : "Agent 不使用记忆" }, { title: "Agent 偏好", description: JSON.stringify(settings.agent_preferences ?? {}) }] });
      } else {
        setDataSheet({ title: label, rows: [{ title: "暂未配置该数据视图", description: "后端接口已保留，前端将在对应交互确定后补充展示。" }] });
      }
    } catch (error) {
      setDataSheet(null);
      setNotice(`读取${label}失败：${(error as Error).message}`);
    } finally {
      setDataLoading(false);
    }
  };

  const currentPage = activeTab === "lobby"
    ? <LobbyPage workspace={workspace} onSwitchTrip={() => setTripSwitcherOpen(true)} onInvite={() => setInviteOpen(true)} onOpenLobby={() => void openLobby()} lobbyUnread={lobbyUnread} onPrivateChat={() => void openAgentChat()} />
    : activeTab === "world"
      ? <WorldPage workspace={workspace} onReplan={setReplanActivity} />
      : activeTab === "functions"
        ? <FunctionsPage workspace={workspace} onOpen={(label) => void openFeature(label)} />
        : <HomePage onOpen={(label) => void openFeature(label)} onPrivateChat={() => void openAgentChat()} />;

  const inviteOptions = apiConfig.useMocks
    ? friends.map((friend) => ({ id: friend.id, nickname: friend.name, username: friend.name, can_invite: true, description: friend.description }))
    : inviteUsers.filter((user) => user.can_invite).map((user) => ({ ...user, description: user.username }));

  const tripOptions: TripOption[] = apiConfig.useMocks
    ? [{ id: workspace.tripId, title: workspace.title, city: workspace.city, startDate: workspace.startDate, endDate: workspace.endDate, status: "当前旅行" }]
    : trips.map((trip) => ({ id: trip.id, title: trip.title, city: trip.city, startDate: trip.start_date, endDate: trip.end_date, status: trip.id === selectedTripId ? "当前旅行" : trip.status }));

  return (
    <AppShell activeTab={activeTab} onTabChange={setActiveTab}>
      {currentPage}
      {loading && <div className="sync-indicator">正在同步后端…</div>}
      {notice && <div className="toast" role="status">{notice}</div>}
      {tripSwitcherOpen && <TripSwitcherSheet trips={tripOptions} currentTripId={selectedTripId} onSelect={(tripId) => void handleSelectTrip(tripId)} onCreate={() => { setTripSwitcherOpen(false); setCreateTripOpen(true); }} onSettings={() => { setTripSwitcherOpen(false); setTripSettingsOpen(true); }} onClose={() => setTripSwitcherOpen(false)} />}
      {tripSettingsOpen && <TripSettingsSheet tripTitle={workspace.title} isOwner={isTripOwner} archived={trips.find((trip) => trip.id === workspace.tripId)?.status === "finished"} loading={loading} onArchive={() => void handleArchiveTrip()} onDelete={() => void handleDeleteTrip()} onLeave={() => void handleLeaveTrip()} onClose={() => setTripSettingsOpen(false)} />}
      {inviteOpen && <ModalSheet title="邀请同行者" onClose={() => setInviteOpen(false)}>
        <div className="sheet-intro">像微信拉群一样搜索用户并邀请加入本次旅行。</div>
        {!apiConfig.useMocks && <input className="text-input search-input" value={inviteQuery} onChange={(event) => void searchInviteUsers(event.target.value)} placeholder="搜索用户名或昵称" />}
        <div className="friend-list">{inviteOptions.map((friend) => <button key={friend.id} className="friend-row" onClick={() => void handleInvite(friend.id)} disabled={inviteLoading}><span className="friend-avatar">{friend.nickname.slice(0, 1)}</span><span><strong>{friend.nickname}</strong><small>{friend.description}</small></span><span className="friend-action">邀请</span></button>)}</div>
        {!apiConfig.useMocks && inviteQuery && !inviteOptions.length && <div className="empty-chat">{inviteLoading ? "搜索中…" : "没有可邀请的用户"}</div>}
        <button className="secondary-button full-button" onClick={() => void handleCopyInvite()}>复制邀请链接</button>
        <button className="primary-button full-button" onClick={() => setInviteOpen(false)}>完成</button>
      </ModalSheet>}
      {replanActivity && <ModalSheet title="调整下午安排" onClose={() => setReplanActivity(null)} wide>
        <div className="replan-summary"><small>当前活动</small><strong>{replanActivity.time} · {replanActivity.title}</strong><p>私聊中的个人需求只会用于生成必要的调整建议，不会直接公开隐私原因。</p></div>
        <label className="field-label" htmlFor="replan-input">调整需求</label>
        <textarea id="replan-input" className="text-area" defaultValue="一次尽量别走超过20分钟，保留湖边休息时间。" />
        <div className="replan-actions"><button className="secondary-button" onClick={() => setReplanActivity(null)}>保留原计划</button><button className="primary-button" onClick={(event) => { const input = (event.currentTarget.parentElement?.previousElementSibling as HTMLTextAreaElement | null); void handleReplan(input?.value ?? ""); }} disabled={replanLoading}>{replanLoading ? "生成中…" : "生成调整建议"}</button></div>
      </ModalSheet>}
      {replanResult && <CandidateSheet result={replanResult} loading={replanLoading} onApply={() => void handleApplyReplan()} onClose={() => setReplanResult(null)} />}
      {dataSheet && <DataSheet title={dataSheet.title} rows={dataSheet.rows} loading={dataLoading} onClose={() => setDataSheet(null)} />}
      {chatMode && <ChatSheet mode={chatMode} lobbyMessages={lobbyMessages} agentMessages={agentMessages} loading={chatLoading} onSend={(content) => void handleChatSend(content)} onRefresh={() => void (chatMode === "lobby" ? openLobby() : openAgentChat())} onClose={() => setChatMode(null)} />}
      {authOpen && !apiConfig.useMocks && <AuthSheet mode={authMode} loading={authLoading} error={authError} onSubmit={(values) => void handleAuth(values)} onToggle={() => { setAuthMode((mode) => mode === "login" ? "register" : "login"); setAuthError(""); }} />}
      {createTripOpen && !apiConfig.useMocks && authUser && <CreateTripSheet title={hasWorkspace ? "新建旅行" : "创建第一场旅行"} closable={hasWorkspace} onClose={() => setCreateTripOpen(false)} onSubmit={(values) => void handleCreateTrip(values)} />}
      <footer className="build-note">{apiConfig.useMocks ? "Mock 数据模式" : `API：${apiConfig.baseUrl}`} · {formatDateRange(workspace.startDate, workspace.endDate)}</footer>
    </AppShell>
  );
}

export default App;
