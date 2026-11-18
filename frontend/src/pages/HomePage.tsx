import { Camera, ChevronRight, KeyRound, SlidersHorizontal } from "lucide-react";
import { useRef } from "react";
import { apiAssetUrl } from "../api/client";
import { StatusBar } from "../components/StatusBar";
import type { AuthUser } from "../types";

export function HomePage({ user, loading, personalPreferences, onOpen, onOpenPreferences, onUploadAvatar, onChangePassword, onLogout }: { user: AuthUser; loading: boolean; personalPreferences: string; onOpen: (label: string) => void; onOpenPreferences: () => void; onUploadAvatar: (file: File) => void; onChangePassword: () => void; onLogout: () => void }) {
  const avatarInput = useRef<HTMLInputElement>(null);
  return (
    <div className="page page-home">
      <StatusBar />
      <section className="profile-summary profile-summary-top" aria-label="当前用户"><button className="profile-avatar avatar-upload-button" onClick={() => avatarInput.current?.click()} disabled={loading}>{user.avatarUrl ? <img src={apiAssetUrl(user.avatarUrl)} alt="当前头像" /> : user.nickname.slice(0, 1)}<span><Camera size={13} /></span></button><input ref={avatarInput} className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => { const file = event.target.files?.[0]; if (file) onUploadAvatar(file); event.target.value = ""; }} /><div><strong>{user.nickname}</strong><small className="profile-account">账号：{user.username}</small><small>点击头像上传新图片 · JPEG/PNG/WebP，最大 5MB</small></div></section>
      <button className="conversation-card" onClick={() => onOpen("上次的对话")}><strong>上次的对话</strong><p>打开最近一次 Agent 私聊记录</p></button>
      <button className="list-row memory-row" onClick={onOpenPreferences}><SlidersHorizontal size={22} /><span><strong>旅行偏好与常用信息</strong><small>{personalPreferences || "仅保存并在前端展示"}</small></span><ChevronRight size={18} /></button>
      <button className="list-row memory-row" onClick={onChangePassword}><KeyRound size={22} /><strong>修改密码</strong><ChevronRight size={18} /></button>
      <button className="secondary-button full-button logout-button" onClick={onLogout}>退出登录</button>
    </div>
  );
}
