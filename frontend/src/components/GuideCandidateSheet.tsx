import { useMemo, useState } from "react";
import { ModalSheet } from "./ModalSheet";
import type { JsonObject } from "../api/client";

export type GuidePlacement = { candidate_id: string; day_number: number; order_index: number };

export function GuideCandidateSheet({ candidates, dayCount, activityCounts, loading, onVerify, onApply, onClose }: {
  candidates: JsonObject[];
  dayCount: number;
  activityCounts: Record<number, number>;
  loading: boolean;
  onVerify: (placements: GuidePlacement[]) => Promise<JsonObject[]>;
  onApply: (placements: GuidePlacement[]) => void;
  onClose: () => void;
}) {
  const [placements, setPlacements] = useState<Record<string, GuidePlacement>>({});
  const [verified, setVerified] = useState<JsonObject[] | null>(null);
  const selected = useMemo(() => Object.values(placements), [placements]);
  const change = (id: string, patch?: Partial<GuidePlacement>) => {
    setVerified(null);
    setPlacements((current) => {
      if (!patch) { const next = { ...current }; delete next[id]; return next; }
      const nextOrder = Math.max(
        (activityCounts[1] ?? 0) + 1,
        ...Object.values(current).filter((item) => item.day_number === 1).map((item) => item.order_index + 1),
      );
      return { ...current, [id]: { ...(current[id] ?? { candidate_id: id, day_number: 1, order_index: nextOrder }), ...patch } };
    });
  };
  return <ModalSheet title={verified ? "确认攻略活动" : "选择攻略候选"} onClose={onClose} wide>
    {!verified ? <>
      <p className="sheet-intro">选择想加入的地点，并明确它要插入哪一天、第几个。下一步会先用高德核对地点，不会立刻修改行程。</p>
      <div className="candidate-choice-list">{candidates.map((candidate) => {
        const id = String(candidate.candidate_id ?? "");
        const placement = placements[id];
        return <div className="candidate-choice guide-candidate" key={id}>
          <label><input type="checkbox" checked={Boolean(placement)} onChange={() => change(id, placement ? undefined : {})} /><span><strong>{String(candidate.title ?? "未命名候选")}</strong><small>{String(candidate.excerpt ?? "")}</small></span></label>
          {placement && <div className="guide-placement-fields"><label>日期<select className="text-input" value={placement.day_number} onChange={(event) => { const day = Number(event.target.value); const nextOrder = Math.max((activityCounts[day] ?? 0) + 1, ...selected.filter((item) => item.candidate_id !== id && item.day_number === day).map((item) => item.order_index + 1)); change(id, { day_number: day, order_index: nextOrder }); }}>{Array.from({ length: dayCount }, (_, index) => <option key={index + 1} value={index + 1}>第 {index + 1} 天</option>)}</select></label><label>插入序号<input className="text-input" type="number" min="1" max={(activityCounts[placement.day_number] ?? 0) + selected.filter((item) => item.day_number === placement.day_number).length} value={placement.order_index} onChange={(event) => change(id, { order_index: Number(event.target.value) })} /></label></div>}
        </div>;
      })}</div>
      <button className="primary-button full-button" disabled={!selected.length || loading} onClick={() => void onVerify(selected).then(setVerified)}>{loading ? "正在高德校验…" : "校验并预览"}</button>
    </> : <>
      <p className="sheet-intro">以下地点已经通过高德校验。确认后才会插入指定位置，并顺延当天后续活动。</p>
      <div className="candidate-choice-list">{verified.map((candidate) => { const id = String(candidate.candidate_id ?? ""); const location = candidate.location as JsonObject | undefined; const placement = placements[id]; return <div className="candidate-choice verified-guide" key={id}><span><strong>{String(location?.name ?? candidate.title)}</strong><small>{String(location?.address ?? "高德地点已确认")}</small><small>第 {placement.day_number} 天 · 插入为第 {placement.order_index} 个活动</small></span></div>; })}</div>
      <div className="sheet-actions"><button className="secondary-button" disabled={loading} onClick={() => setVerified(null)}>返回修改</button><button className="primary-button" disabled={loading} onClick={() => onApply(selected)}>{loading ? "正在加入…" : "确认加入行程"}</button></div>
    </>}
  </ModalSheet>;
}
