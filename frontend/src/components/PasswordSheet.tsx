import { useState } from "react";
import { ModalSheet } from "./ModalSheet";

export function PasswordSheet({ loading, onSubmit, onClose }: { loading: boolean; onSubmit: (currentPassword: string, newPassword: string) => void; onClose: () => void }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const mismatch = Boolean(confirmPassword && newPassword !== confirmPassword);
  return <ModalSheet title="修改密码" onClose={onClose}>
    <form className="auth-form" onSubmit={(event) => { event.preventDefault(); if (!mismatch) onSubmit(currentPassword, newPassword); }}>
      <label className="field-label">当前密码<input className="text-input" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label>
      <label className="field-label">新密码<input className="text-input" type="password" autoComplete="new-password" minLength={8} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /><small>至少 8 个字符</small></label>
      <label className="field-label">确认新密码<input className="text-input" type="password" autoComplete="new-password" minLength={8} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required /></label>
      {mismatch && <p className="form-error">两次输入的新密码不一致</p>}
      <p className="sheet-intro">修改成功后，所有已登录设备都需要重新登录。</p>
      <button className="primary-button full-button" disabled={loading || mismatch}>{loading ? "修改中…" : "确认修改"}</button>
    </form>
  </ModalSheet>;
}
