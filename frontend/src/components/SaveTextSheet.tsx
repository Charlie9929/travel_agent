import { useState } from "react";
import { ModalSheet } from "./ModalSheet";

export function SaveTextSheet({ title, intro, label, placeholder, value, onSave, onClose, readOnly = false }: {
  title: string;
  intro: string;
  label: string;
  placeholder: string;
  value: string;
  onSave: (value: string) => void | Promise<void>;
  onClose: () => void;
  readOnly?: boolean;
}) {
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  return (
    <ModalSheet title={title} onClose={onClose} wide>
      <p className="sheet-intro">{intro}</p>
      <form className="auth-form" onSubmit={(event) => { event.preventDefault(); if (readOnly) { onClose(); return; } setSaving(true); setError(""); Promise.resolve(onSave(draft.trim())).then(onClose).catch((reason: Error) => setError(reason.message)).finally(() => setSaving(false)); }}>
        <label className="field-label" htmlFor="saved-text-input">{label}<textarea id="saved-text-input" className="text-area saved-text-area" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={placeholder} readOnly={readOnly} /></label>
        {error && <p className="form-error">{error}</p>}
        <button className={readOnly ? "secondary-button full-button" : "primary-button full-button"} disabled={saving}>{readOnly ? "关闭" : saving ? "保存中…" : "保存"}</button>
      </form>
    </ModalSheet>
  );
}
