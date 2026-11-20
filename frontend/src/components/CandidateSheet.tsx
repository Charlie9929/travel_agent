import type { ReplanResult } from "../types";
import { ModalSheet } from "./ModalSheet";

export function CandidateSheet({ result, loading, canApply = true, onApply, onDiscuss, onClose }: { result: ReplanResult; loading: boolean; canApply?: boolean; onApply: () => void; onDiscuss?: () => void; onClose: () => void }) {
  return (
    <ModalSheet title="调整建议" onClose={onClose} wide>
      <div className="candidate-summary"><small>Agent 建议</small><strong>{result.summary || "Agent 已生成一版调整候选"}</strong><span>确认后才会写入行程。</span></div>
      <div className="replan-actions"><button className="secondary-button" onClick={onDiscuss ?? onClose}>{onDiscuss ? "继续和 Agent 讨论" : "关闭"}</button>{canApply && <button className="primary-button" onClick={onApply} disabled={loading}>{loading ? "应用中…" : "确认并应用"}</button>}</div>
      {!canApply && <p className="candidate-permission-note">你可以查看这版候选；需要由“房主”或“可编辑”成员确认应用。</p>}
    </ModalSheet>
  );
}
