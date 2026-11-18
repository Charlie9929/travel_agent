import { useState } from "react";
import { ModalSheet } from "./ModalSheet";

export function SaveTextSheet({ title, intro, label, placeholder, value, onSave, onClose }: {
  title: string;
  intro: string;
  label: string;
  placeholder: string;
  value: string;
  onSave: (value: string) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(value);
  return (
    <ModalSheet title={title} onClose={onClose} wide>
      <p className="sheet-intro">{intro}</p>
      <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSave(draft.trim()); onClose(); }}>
        <label className="field-label" htmlFor="saved-text-input">{label}<textarea id="saved-text-input" className="text-area saved-text-area" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={placeholder} /></label>
        <p className="local-save-note">仅保存在当前浏览器并由前端展示，不会自动提交给 Agent。</p>
        <button className="primary-button full-button">保存</button>
      </form>
    </ModalSheet>
  );
}
