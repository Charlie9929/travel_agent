import { useState } from "react";
import type { Activity } from "../types";
import { ModalSheet } from "./ModalSheet";

const MAX_FILES = 3;
const MAX_BYTES = 8 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export function HighlightSheet({ activity, loading, onSubmit, onClose }: { activity?: Activity; loading: boolean; onSubmit: (title: string, content: string, files: File[]) => void; onClose: () => void }) {
  const [title, setTitle] = useState(activity?.title ?? "");
  const [content, setContent] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState("");

  const selectFiles = (list: FileList | null) => {
    const selected = Array.from(list ?? []);
    if (selected.length > MAX_FILES) {
      setError(`每条记录最多上传 ${MAX_FILES} 张图片`);
      return;
    }
    const invalidType = selected.find((file) => !ALLOWED_TYPES.has(file.type));
    if (invalidType) {
      setError("仅支持 JPEG、PNG 和 WebP 图片");
      return;
    }
    const oversized = selected.find((file) => file.size > MAX_BYTES);
    if (oversized) {
      setError(`“${oversized.name}”超过 8MB`);
      return;
    }
    setError("");
    setFiles(selected);
  };

  return <ModalSheet title={activity ? `记录 · ${activity.title}` : "新增旅行记录"} onClose={onClose} wide>
    <form className="auth-form" onSubmit={(event) => { event.preventDefault(); if (!error) onSubmit(title.trim(), content.trim(), files); }}>
      <label className="field-label">标题<input className="text-input" value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
      <label className="field-label">文字记录<textarea className="text-area" value={content} onChange={(event) => setContent(event.target.value)} placeholder="写下这项活动值得记住的瞬间" /></label>
      <label className="field-label">照片（可选）<input className="text-input file-input" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => selectFiles(event.target.files)} /><small>最多 3 张，单张不超过 8MB</small></label>
      {!!files.length && <div className="selected-files">{files.map((file) => <span key={`${file.name}-${file.size}`}>{file.name} · {(file.size / 1024 / 1024).toFixed(1)}MB</span>)}</div>}
      {error && <p className="form-error">{error}</p>}
      <button className="primary-button full-button" disabled={loading || Boolean(error)}>{loading ? "保存与上传中…" : "保存旅行记录"}</button>
    </form>
  </ModalSheet>;
}
