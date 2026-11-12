import { useState } from "react";
import { ModalSheet } from "./ModalSheet";

type AuthMode = "login" | "register";

export function AuthSheet({
  mode,
  loading,
  error,
  onSubmit,
  onToggle,
}: {
  mode: AuthMode;
  loading: boolean;
  error: string;
  onSubmit: (values: { username: string; password: string; nickname: string }) => void;
  onToggle: () => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");

  return (
    <ModalSheet title={mode === "login" ? "登录山行" : "创建山行账号"} onClose={() => undefined} closable={false}>
      <p className="sheet-intro">登录后才能读取真实行程、群聊和 Agent 私聊数据。</p>
      <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ username, password, nickname }); }}>
        {mode === "register" && <label className="field-label">昵称<input className="text-input" value={nickname} onChange={(event) => setNickname(event.target.value)} required minLength={1} /></label>}
        <label className="field-label">用户名<input className="text-input" value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} /></label>
        <label className="field-label">密码<input className="text-input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} /></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary-button full-button" disabled={loading}>{loading ? "处理中…" : mode === "login" ? "登录" : "注册并登录"}</button>
      </form>
      <button className="text-button" onClick={onToggle}>{mode === "login" ? "还没有账号？创建一个" : "已有账号？返回登录"}</button>
    </ModalSheet>
  );
}
