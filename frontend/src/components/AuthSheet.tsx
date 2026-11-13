import { useEffect, useState } from "react";
import beachVideo from "../assets/auth/beach.mp4";
import hikingVideo from "../assets/auth/hiking.mp4";
import mountainVideo from "../assets/auth/mountains.mp4";

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
  const [activeScene, setActiveScene] = useState(0);
  const scenes = [mountainVideo, beachVideo, hikingVideo];

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => setActiveScene((current) => (current + 1) % scenes.length), 9000);
    return () => window.clearInterval(timer);
  }, [scenes.length]);

  return (
    <section className="auth-screen" aria-label={mode === "login" ? "登录" : "注册"}>
      <div className="auth-scenes" aria-hidden="true">
        {scenes.map((scene, index) => <video key={scene} className={index === activeScene ? "is-active" : ""} src={scene} autoPlay muted loop playsInline preload={index === 0 ? "auto" : "metadata"} />)}
      </div>
      <div className="auth-shade" />
      <div className="auth-card">
        <div className="auth-brand"><span>行伴</span><small>和喜欢的人，一起把旅途想清楚</small></div>
        <header><h1>{mode === "login" ? "欢迎回来" : "创建账号"}</h1><p>登录后即可查看真实行程、群聊与每段旅程的 Agent 私聊。</p></header>
        <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ username, password, nickname }); }}>
          {mode === "register" && <label className="field-label">昵称<input className="text-input" value={nickname} onChange={(event) => setNickname(event.target.value)} required minLength={1} autoComplete="nickname" /></label>}
          <label className="field-label">用户名<input className="text-input" value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} autoComplete="username" /></label>
          <label className="field-label">密码<input className="text-input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button full-button" disabled={loading}>{loading ? "处理中…" : mode === "login" ? "登录" : "注册并登录"}</button>
        </form>
        <button className="text-button auth-toggle" onClick={onToggle}>{mode === "login" ? "还没有账号？创建一个" : "已有账号？返回登录"}</button>
        <div className="auth-scene-dots" aria-hidden="true">{scenes.map((_, index) => <i key={index} className={index === activeScene ? "is-active" : ""} />)}</div>
      </div>
    </section>
  );
}
