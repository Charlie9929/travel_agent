import type { ApiRevision } from "../api/client";
import { ModalSheet } from "./ModalSheet";

const actionLabels: Record<string, string> = { create: "新增", update: "修改", delete: "删除", revise: "整体调整", replan: "局部调整", reorder: "顺序调整", guide_import: "攻略导入", constraint_change: "约束调整", replan_midtrip: "行程重排" };
const resourceLabels: Record<string, string> = { trip: "旅行信息", activity: "行程活动", member: "同行成员", expense: "账单", highlight: "旅行手帐", requirement: "旅行需求", ai_run: "Agent 调整" };

function labelFor(map: Record<string, string>, value: string) {
  return map[value] ?? value;
}

function RevisionCard({ revision }: { revision: ApiRevision }) {
  return (
    <article className="revision-card">
      <header className="revision-card-header"><div><strong>第 {revision.version} 版 · {labelFor(actionLabels, revision.action)}</strong><small>{labelFor(resourceLabels, revision.resource_type)} · {new Date(revision.created_at).toLocaleString("zh-CN")}</small></div></header>
      <p className="revision-summary">{revision.summary || `${labelFor(resourceLabels, revision.resource_type)}发生了变化`}</p>
      <small className="revision-operator">操作人：{revision.user_nickname || "未知成员"}</small>
    </article>
  );
}

export function RevisionSheet({ revisions, loading, onClose }: { revisions: ApiRevision[]; loading: boolean; onClose: () => void }) {
  return (
    <ModalSheet title="历史记录" onClose={onClose} wide>
      <p className="sheet-intro">只读查看行程、成员和 Agent 的操作记录。</p>
      {loading && <div className="empty-chat">正在读取详细历史记录…</div>}
      {!loading && !revisions.length && <div className="empty-chat">暂时没有历史记录</div>}
      {!loading && !!revisions.length && <div className="revision-list">{revisions.map((revision) => <RevisionCard key={revision.id} revision={revision} />)}</div>}
    </ModalSheet>
  );
}
