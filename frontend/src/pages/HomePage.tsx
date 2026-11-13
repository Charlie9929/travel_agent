import { BookOpen, Camera, ChevronRight, KeyRound, Settings } from "lucide-react";
import { useRef } from "react";
import { apiAssetUrl } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";
import type { AuthUser } from "../types";

export function HomePage({ user, loading, onOpen, onUploadAvatar, onChangePassword, onLogout }: { user: AuthUser; loading: boolean; onOpen: (label: string) => void; onUploadAvatar: (file: File) => void; onChangePassword: () => void; onLogout: () => void }) {
  const avatarInput = useRef<HTMLInputElement>(null);
  return (
    <div className="page page-home">
      <StatusBar />
      <PageHeader title={`${user.nickname}的主页`} subtitle={`账号：${user.username}`} action={<button className="icon-button" onClick={() => onOpen("设置")} aria-label="设置"><Settings size={23} /></button>} />
      <section className="profile-summary" aria-label="当前用户"><button className="profile-avatar avatar-upload-button" onClick={() => avatarInput.current?.click()} disabled={loading}>{user.avatarUrl ? <img src={apiAssetUrl(user.avatarUrl)} alt="当前头像" /> : user.nickname.slice(0, 1)}<span><Camera size={13} /></span></button><input ref={avatarInput} className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => { const file = event.target.files?.[0]; if (file) onUploadAvatar(file); event.target.value = ""; }} /><div><strong>{user.nickname}</strong><small>点击头像上传新图片 · JPEG/PNG/WebP，最大 5MB</small></div></section>
      <button className="conversation-card" onClick={() => onOpen("上次的对话")}><strong>上次的对话</strong><p>打开最近一次 Agent 私聊记录</p></button>
      <button className="list-row memory-row" onClick={() => onOpen("记忆簿")}><BookOpen size={22} /><strong>旅行偏好与常用信息</strong><ChevronRight size={18} /></button>
      <button className="list-row memory-row" onClick={onChangePassword}><KeyRound size={22} /><strong>修改密码</strong><ChevronRight size={18} /></button>
      <button className="secondary-button full-button logout-button" onClick={onLogout}>退出登录</button>
    </div>
  );
}
