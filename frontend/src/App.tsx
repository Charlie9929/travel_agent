import { useEffect, useState } from "react";
import { AppShell } from "./components/AppShell";
import { ModalSheet } from "./components/ModalSheet";
import { api, apiConfig, mapApiWorkspace } from "./api/client";
import { mockWorkspace } from "./mocks/data";
import { FunctionsPage } from "./pages/FunctionsPage";
import { HomePage } from "./pages/HomePage";
import { LobbyPage } from "./pages/LobbyPage";
import { WorldPage } from "./pages/WorldPage";
import type { Activity, Tab, Workspace } from "./types";

const friends = [
  { id: 21, name: "乔乔", description: "杭州同行者" },
  { id: 22, name: "阿澈", description: "已在本次旅行" },
  { id: 23, name: "小满", description: "最近联系" },
];

function formatDateRange(start: string, end: string) {
  return `${start.slice(5).replace("-", "月")}日—${end.slice(5).replace("-", "月")}日`;
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>("lobby");
  const [workspace, setWorkspace] = useState<Workspace>(mockWorkspace);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [replanActivity, setReplanActivity] = useState<Activity | null>(null);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const hasToken = localStorage.getItem("travel-agent-token") || import.meta.env.VITE_ACCESS_TOKEN;
    if (apiConfig.useMocks || !hasToken) return;
    setLoading(true);
    api.trips.list()
      .then(async ({ items }) => {
        if (!items[0]) return;
        const [detail, members] = await Promise.all([api.trips.get(items[0].id), api.members.list(items[0].id)]);
        setWorkspace(mapApiWorkspace(detail, members, mockWorkspace.members));
        setNotice("已读取后端行程数据");
      })
      .catch((error: Error) => setNotice(`后端连接失败，继续使用 Mock：${error.message}`))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const handleInvite = async (friendId: number) => {
    if (apiConfig.useMocks) {
      setNotice("已发送邀请（Mock）");
      return;
    }
    try {
      await api.members.invite(workspace.tripId, friendId);
      setNotice("邀请已发送");
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
      setNotice("已生成调整建议（Mock）");
      setReplanActivity(null);
      return;
    }
    try {
      await api.ai.replan({ trip_id: workspace.tripId, day_number: replanActivity.day, adjustment_requirements: instruction, trip_version: workspace.version, after_time: replanActivity.time });
      setNotice("调整建议已生成，请在后端返回后确认应用");
      setReplanActivity(null);
    } catch (error) {
      setNotice(`生成调整建议失败：${(error as Error).message}`);
    }
  };

  const page = activeTab === "lobby"
    ? <LobbyPage workspace={workspace} onInvite={() => setInviteOpen(true)} onPrivateChat={() => setNotice("私聊页面待后端聊天接口确认")} />
    : activeTab === "world"
      ? <WorldPage workspace={workspace} onReplan={setReplanActivity} />
      : activeTab === "functions"
        ? <FunctionsPage workspace={workspace} onOpen={(label) => setNotice(`${label} 页面待后端接口确认`)} />
        : <HomePage onOpen={(label) => setNotice(`${label} 页面待后端接口确认`)} />;

  return (
    <AppShell activeTab={activeTab} onTabChange={setActiveTab}>
      {page}
      {loading && <div className="sync-indicator">正在同步后端…</div>}
      {notice && <div className="toast" role="status">{notice}</div>}
      {inviteOpen && <ModalSheet title="邀请同行者" onClose={() => setInviteOpen(false)}>
        <div className="sheet-intro">选择好友或复制邀请链接，让真实同行者加入本次旅行。</div>
        <div className="friend-list">{friends.map((friend) => <button key={friend.id} className="friend-row" onClick={() => void handleInvite(friend.id)}><span className="friend-avatar">{friend.name.slice(0, 1)}</span><span><strong>{friend.name}</strong><small>{friend.description}</small></span><span className="friend-action">邀请</span></button>)}</div>
        <button className="secondary-button full-button" onClick={() => void handleCopyInvite()}>复制邀请链接</button>
        <button className="primary-button full-button" onClick={() => setInviteOpen(false)}>完成</button>
      </ModalSheet>}
      {replanActivity && <ModalSheet title="调整下午安排" onClose={() => setReplanActivity(null)} wide>
        <div className="replan-summary"><small>当前活动</small><strong>{replanActivity.time} · {replanActivity.title}</strong><p>房主已确认林妈妈希望少走路，其他行程尽量保持不变。</p></div>
        <label className="field-label" htmlFor="replan-input">调整需求</label>
        <textarea id="replan-input" className="text-area" defaultValue="一次尽量别走超过20分钟，保留湖边休息时间。" />
        <div className="replan-actions"><button className="secondary-button" onClick={() => setReplanActivity(null)}>保留原计划</button><button className="primary-button" onClick={(event) => { const input = (event.currentTarget.parentElement?.previousElementSibling as HTMLTextAreaElement | null); void handleReplan(input?.value ?? ""); }}>生成调整建议</button></div>
      </ModalSheet>}
      <footer className="build-note">{apiConfig.useMocks ? "Mock 数据模式" : `API：${apiConfig.baseUrl}`} · {formatDateRange(workspace.startDate, workspace.endDate)}</footer>
    </AppShell>
  );
}

export default App;
