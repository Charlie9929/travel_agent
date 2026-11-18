import { ChevronDown, Eye } from "lucide-react";
import type { ApiRevision } from "../api/client";
import { ModalSheet } from "./ModalSheet";

const actionLabels: Record<string, string> = { create: "新增", update: "修改", delete: "删除", guide_import: "攻略导入", constraint_change: "约束调整", replan_midtrip: "行程重排" };
const resourceLabels: Record<string, string> = { trip: "旅行信息", activity: "行程活动", member: "同行成员", expense: "账单", highlight: "旅行手帐", requirement: "旅行需求", ai_run: "Agent 调整" };

function labelFor(map: Record<string, string>, value: string) {
  return map[value] ?? value;
}

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.length ? value.map(valueText).join("、") : "空列表";
  if (typeof value === "object") return Object.entries(value as Record<string, unknown>).slice(0, 5).map(([key, item]) => `${key}：${valueText(item)}`).join("；") || "空对象";
  return String(value);
}

function changeRows(revision: ApiRevision) {
  if (revision.changes?.length) return revision.changes;
  const before = revision.before && typeof revision.before === "object" ? revision.before as Record<string, unknown> : {};
  const after = revision.after && typeof revision.after === "object" ? revision.after as Record<string, unknown> : {};
  return Object.keys({ ...before, ...after }).filter((field) => before[field] !== after[field]).map((field) => ({ field, before: before[field], after: after[field] }));
}

function RevisionCard({ revision }: { revision: ApiRevision }) {
  const changes = changeRows(revision);
  const fallback = Object.entries(revision.diff_content ?? {}).filter(([key]) => !["before", "after"].includes(key)).map(([field, after]) => ({ field, before: undefined, after }));
  const details = changes.length ? changes : fallback;
  return (
    <article className="revision-card">
      <header className="revision-card-header"><div><strong>第 {revision.version} 版 · {labelFor(actionLabels, revision.action)}</strong><small>{labelFor(resourceLabels, revision.resource_type)} · {new Date(revision.created_at).toLocaleString("zh-CN")}</small></div><span className="revision-eye"><Eye size={16} /></span></header>
      <p className="revision-summary">{revision.summary || `由用户 #${revision.user_id} 产生了${labelFor(resourceLabels, revision.resource_type)}变化`}</p>
      <small className="revision-operator">操作人：用户 #{revision.user_id}{revision.resource_id ? ` · 对象 #${revision.resource_id}` : ""}</small>
      {!!details.length && <details className="revision-details"><summary>查看具体变化<ChevronDown size={15} /></summary><div className="revision-change-list">{details.slice(0, 12).map((change, index) => <div className="revision-change" key={`${String(change.field)}-${index}`}><strong>{String(change.field)}</strong><span>{valueText(change.before)}</span><b>→</b><span>{valueText(change.after)}</span></div>)}</div></details>}
    </article>
  );
}

export function RevisionSheet({ revisions, loading, onClose }: { revisions: ApiRevision[]; loading: boolean; onClose: () => void }) {
  return (
    <ModalSheet title="历史记录" onClose={onClose} wide>
      <p className="sheet-intro">只读查看行程、成员和 Agent 操作记录，不提供历史版本恢复。</p>
      {loading && <div className="empty-chat">正在读取详细历史记录…</div>}
      {!loading && !revisions.length && <div className="empty-chat">暂时没有历史记录</div>}
      {!loading && !!revisions.length && <div className="revision-list">{revisions.map((revision) => <RevisionCard key={revision.id} revision={revision} />)}</div>}
    </ModalSheet>
  );
}
