import { useMemo, useState } from "react";
import type { Activity, Member } from "../types";
import { ModalSheet } from "./ModalSheet";

export type ExpenseFormValues = {
  title: string;
  amount: number;
  payer_id: number;
  activity_id?: number;
  split_type: "equal" | "ratio";
  participant_ids: number[];
  splits: { user_id: number; ratio: number }[];
};

export function ExpenseSheet({ activity, members, currentUserId, loading, onSubmit, onClose }: { activity?: Activity; members: Member[]; currentUserId: number; loading: boolean; onSubmit: (values: ExpenseFormValues) => void; onClose: () => void }) {
  const memberIds = useMemo(() => members.map((member) => member.id), [members]);
  const [title, setTitle] = useState(activity?.title ?? "");
  const [amount, setAmount] = useState("");
  const [payerId, setPayerId] = useState(String(members.some((member) => member.id === currentUserId) ? currentUserId : members[0]?.id ?? ""));
  const [participants, setParticipants] = useState<number[]>(memberIds);
  const [splitType, setSplitType] = useState<"equal" | "ratio">("equal");
  const [weights, setWeights] = useState<Record<number, string>>(() => Object.fromEntries(memberIds.map((id) => [id, "1"])));

  const toggleParticipant = (userId: number) => setParticipants((items) => items.includes(userId) ? items.filter((item) => item !== userId) : [...items, userId]);

  const selectedWeights = participants.map((userId) => ({ userId, weight: Number(weights[userId] || 0) }));
  const weightTotal = selectedWeights.reduce((total, item) => total + item.weight, 0);
  const normalizedSplits = weightTotal > 0 ? selectedWeights.map((item, index) => ({
    user_id: item.userId,
    ratio: index === selectedWeights.length - 1
      ? Number((1 - selectedWeights.slice(0, -1).reduce((total, entry) => total + entry.weight / weightTotal, 0)).toFixed(4))
      : Number((item.weight / weightTotal).toFixed(4)),
  })) : [];

  return <ModalSheet title={activity ? `记一笔 · ${activity.title}` : "新增旅行账单"} onClose={onClose} wide>
    <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ title: title.trim(), amount: Number(amount), payer_id: Number(payerId), activity_id: activity?.id, split_type: splitType, participant_ids: splitType === "equal" ? participants : [], splits: splitType === "ratio" ? normalizedSplits : [] }); }}>
      <label className="field-label">账单名称<input className="text-input" value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
      <label className="field-label">金额<input className="text-input" type="number" min="0.01" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} required /></label>
      <label className="field-label">付款人<select className="text-input" value={payerId} onChange={(event) => setPayerId(event.target.value)} required>{members.map((member) => <option value={member.id} key={member.id}>{member.name}</option>)}</select></label>
      <label className="field-label">分摊方式<select className="text-input" value={splitType} onChange={(event) => setSplitType(event.target.value as "equal" | "ratio")}><option value="equal">参与成员均摊</option><option value="ratio">按自定义权重分摊</option></select></label>
      <fieldset className="member-checklist expense-member-checklist"><legend>参与分摊的成员</legend>{members.map((member) => { const selected = participants.includes(member.id); return <label key={member.id}><input type="checkbox" checked={selected} onChange={() => toggleParticipant(member.id)} /><span>{member.name}</span>{splitType === "ratio" && selected && <input className="weight-input" aria-label={`${member.name}的分摊权重`} type="number" min="0.01" step="0.01" value={weights[member.id] ?? "1"} onChange={(event) => setWeights((current) => ({ ...current, [member.id]: event.target.value }))} />}</label>; })}</fieldset>
      {splitType === "ratio" && <div className="ratio-preview"><strong>预计比例</strong>{normalizedSplits.map((item) => <span key={item.user_id}>{members.find((member) => member.id === item.user_id)?.name}：{(item.ratio * 100).toFixed(1)}%</span>)}</div>}
      <p className="sheet-intro">系统只计算“谁应付给谁多少钱”，不会发起真实付款。</p>
      <button className="primary-button full-button" disabled={loading || !participants.length || (splitType === "ratio" && weightTotal <= 0)}>{loading ? "保存中…" : "保存账单"}</button>
    </form>
  </ModalSheet>;
}
