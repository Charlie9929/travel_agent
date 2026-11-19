import { useEffect, useRef, useState } from "react";
import grasslandVideo from "../assets/auth/grassland-hd.mp4";
import mountainVideo from "../assets/auth/mountains-hd.mp4";
import oceanVideo from "../assets/auth/ocean-hd.mp4";
import { ProcessingLabel } from "./ProcessingLabel";

type AuthMode = "login" | "register";

// Free stock footage: Pexels videos 15462304, 8346814, and 9305918.
const scenes = [oceanVideo, mountainVideo, grasslandVideo];

export function AuthSheet({
  mode,
  loading,
  error,
  onSubmit,
  onToggle,
  onForgotPassword,
}: {
  mode: AuthMode;
  loading: boolean;
  error: string;
  onSubmit: (values: { username: string; password: string; nickname: string }) => void;
  onToggle: () => void;
  onForgotPassword: (values: { username: string; nickname: string; newPassword: string }) => Promise<boolean>;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [forgotOpen, setForgotOpen] = useState(false);
  const [forgotNickname, setForgotNickname] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [forgotError, setForgotError] = useState("");
  const [activeScene, setActiveScene] = useState(0);
  const videoRefs = useRef<Array<HTMLVideoElement | null>>([]);

  useEffect(() => {
    videoRefs.current.forEach((video, index) => {
      if (!video) return;
      if (index === activeScene) {
        video.currentTime = 0;
        void video.play().catch(() => undefined);
      } else {
        video.pause();
        video.currentTime = 0;
      }
    });
  }, [activeScene]);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(
      () => setActiveScene((current) => (current + 1) % scenes.length),
      9000,
    );
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section className="auth-screen" aria-label={forgotOpen ? "找回密码" : mode === "login" ? "登录" : "注册"}>
      <div className="auth-scenes" aria-hidden="true">
        {scenes.map((scene, index) => (
          <video
            key={scene}
            ref={(element) => { videoRefs.current[index] = element; }}
            className={index === activeScene ? "is-active" : ""}
            src={scene}
            muted
            loop
            playsInline
            preload="auto"
          />
        ))}
      </div>
      <div className="auth-card">
        <div className="auth-brand"><span>行伴</span><small>和喜欢的人，一起把旅途想清楚</small></div>
        <header><h1>{forgotOpen ? "找回密码" : mode === "login" ? "欢迎回来" : "创建账号"}</h1><p>{forgotOpen ? "请输入注册时的用户名和昵称，设置一个新密码。" : "登录后即可查看真实行程、群聊与每段旅程的 Agent 私聊。"}</p></header>
        {forgotOpen ? (
          <form className="auth-form" onSubmit={async (event) => {
            event.preventDefault();
            if (newPassword !== confirmPassword) {
              setForgotError("两次输入的新密码不一致");
              return;
            }
            setForgotError("");
            const success = await onForgotPassword({ username, nickname: forgotNickname, newPassword });
            if (success) {
              setForgotOpen(false);
              setForgotNickname("");
              setNewPassword("");
              setConfirmPassword("");
            }
          }}>
            <label className="field-label">用户名<input className="text-input" value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} autoComplete="username" /></label>
            <label className="field-label">注册时的昵称<input className="text-input" value={forgotNickname} onChange={(event) => setForgotNickname(event.target.value)} required minLength={1} autoComplete="nickname" /></label>
            <label className="field-label">新密码<input className="text-input" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required minLength={8} autoComplete="new-password" /></label>
            <label className="field-label">确认新密码<input className="text-input" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required minLength={8} autoComplete="new-password" /></label>
            {(error || forgotError) && <p className="form-error" role="alert">{forgotError || error}</p>}
            <button className="primary-button full-button" disabled={loading}>{loading ? <ProcessingLabel /> : "重置密码"}</button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ username, password, nickname }); }}>
            {mode === "register" && <label className="field-label">昵称<input className="text-input" value={nickname} onChange={(event) => setNickname(event.target.value)} required minLength={1} autoComplete="nickname" /></label>}
            <label className="field-label">用户名<input className="text-input" value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} autoComplete="username" /></label>
            <label className="field-label">密码<input className="text-input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="primary-button full-button" disabled={loading}>{loading ? <ProcessingLabel /> : mode === "login" ? "登录" : "注册并登录"}</button>
          </form>
        )}
        {forgotOpen ? <button className="text-button auth-toggle" onClick={() => { setForgotOpen(false); setForgotError(""); }}>返回登录</button> : <>
          {mode === "login" && <button className="text-button auth-toggle" onClick={() => { setForgotOpen(true); setForgotError(""); }}>忘记密码？</button>}
          <button className="text-button auth-toggle" onClick={onToggle}>{mode === "login" ? "还没有账号？创建一个" : "已有账号？返回登录"}</button>
        </>}
        <div className="auth-scene-dots" aria-hidden="true">
          {scenes.map((_, index) => <i key={index} className={index === activeScene ? "is-active" : ""} />)}
        </div>
      </div>
    </section>
  );
}
