import type { ReplanResult } from "../types";
import { ModalSheet } from "./ModalSheet";

function itemText(item: unknown) {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    const record = item as Record<string, unknown>;
    return String(record.title ?? record.summary ?? record.name ?? JSON.stringify(item));
  }
  return String(item);
}

export function CandidateSheet({ result, loading, onApply, onClose }: { result: ReplanResult; loading: boolean; onApply: () => void; onClose: () => void }) {
  const changedItems = result.changedItems?.length ? result.changedItems : result.diff?.ops ?? [];
  return (
    <ModalSheet title="调整建议" onClose={onClose} wide>
      <div className="candidate-summary"><small>Agent 建议</small><strong>{result.summary}</strong><span>基于行程第 {result.baseVersion} 版生成，确认后才会写入行程。</span></div>
      <section className="candidate-section"><h3>将要变化</h3>{changedItems.length ? <ul>{changedItems.slice(0, 6).map((item, index) => <li key={index}>{itemText(item)}</li>)}</ul> : <p>Agent 返回了候选方案，请确认是否应用。</p>}</section>
      {!!result.keptItems?.length && <section className="candidate-section"><h3>保持不变</h3><ul>{result.keptItems.slice(0, 6).map((item, index) => <li key={index}>{itemText(item)}</li>)}</ul></section>}
      <div className="replan-actions"><button className="secondary-button" onClick={onClose}>保留原计划</button><button className="primary-button" onClick={onApply} disabled={loading}>{loading ? "应用中…" : "确认并应用"}</button></div>
    </ModalSheet>
  );
}
