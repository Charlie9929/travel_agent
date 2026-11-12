import { useMemo, useState } from "react";
import type { Activity, Member } from "../types";
import { ModalSheet } from "./ModalSheet";

export type ExpenseFormValues = {
  title: string;
  amount: number;
  payer_id: number;
  activity_id?: number;
  split_type: "equal";
  participant_ids: number[];
};

export function ExpenseSheet({ activity, members, currentUserId, loading, onSubmit, onClose }: { activity?: Activity; members: Member[]; currentUserId: number; loading: boolean; onSubmit: (values: ExpenseFormValues) => void; onClose: () => void }) {
  const memberIds = useMemo(() => members.map((member) => member.id), [members]);
  const [title, setTitle] = useState(activity?.title ?? "");
  const [amount, setAmount] = useState("");
  const [payerId, setPayerId] = useState(String(members.some((member) => member.id === currentUserId) ? currentUserId : members[0]?.id ?? ""));
  const [participants, setParticipants] = useState<number[]>(memberIds);

  const toggleParticipant = (userId: number) => setParticipants((items) => items.includes(userId) ? items.filter((item) => item !== userId) : [...items, userId]);

  return <ModalSheet title={activity ? `记一笔 · ${activity.title}` : "新增旅行账单"} onClose={onClose} wide>
    <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ title: title.trim(), amount: Number(amount), payer_id: Number(payerId), activity_id: activity?.id, split_type: "equal", participant_ids: participants }); }}>
      <label className="field-label">账单名称<input className="text-input" value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
      <label className="field-label">金额<input className="text-input" type="number" min="0.01" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} required /></label>
      <label className="field-label">付款人<select className="text-input" value={payerId} onChange={(event) => setPayerId(event.target.value)} required>{members.map((member) => <option value={member.id} key={member.id}>{member.name}</option>)}</select></label>
      <fieldset className="member-checklist"><legend>参与均摊的成员</legend>{members.map((member) => <label key={member.id}><input type="checkbox" checked={participants.includes(member.id)} onChange={() => toggleParticipant(member.id)} /><span>{member.name}</span></label>)}</fieldset>
      <p className="sheet-intro">系统只计算“谁应付给谁多少钱”，不会发起真实付款。</p>
      <button className="primary-button full-button" disabled={loading || !participants.length}>{loading ? "保存中…" : "保存账单"}</button>
    </form>
  </ModalSheet>;
}
