import { useState } from "react";
import type { Activity } from "../types";
import { ModalSheet } from "./ModalSheet";

export type ActivityFormValues = {
  day_number: number;
  order_index: number;
  title: string;
  type: Activity["type"];
  start_time?: string;
  duration_min?: number;
  location_name?: string;
  price_estimated?: number;
  description?: string;
};

export function ActivityEditorSheet({ activity, defaultDay, defaultOrder, loading, onSubmit, onClose }: { activity?: Activity; defaultDay: number; defaultOrder: number; loading: boolean; onSubmit: (values: ActivityFormValues) => void; onClose: () => void }) {
  const [day, setDay] = useState(String(activity?.day ?? defaultDay));
  const [order, setOrder] = useState(String(activity?.order ?? defaultOrder));
  const [title, setTitle] = useState(activity?.title ?? "");
  const [type, setType] = useState<Activity["type"]>(activity?.type ?? "sight");
  const [time, setTime] = useState(activity?.time === "待定" ? "" : activity?.time ?? "");
  const [duration, setDuration] = useState("");
  const [location, setLocation] = useState(activity?.location === "地点待定" ? "" : activity?.location ?? "");
  const [price, setPrice] = useState(activity?.estimatedPrice == null ? "" : String(activity.estimatedPrice));
  const [description, setDescription] = useState(activity?.detail === "暂无活动说明" ? "" : activity?.detail ?? "");

  return <ModalSheet title={activity ? "编辑活动" : "新增活动"} onClose={onClose} wide>
    <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ day_number: Number(day), order_index: Number(order), title: title.trim(), type, start_time: time || undefined, duration_min: duration ? Number(duration) : undefined, location_name: location.trim() || undefined, price_estimated: price ? Number(price) : undefined, description: description.trim() || undefined }); }}>
      <div className="date-fields"><label className="field-label">第几天<input className="text-input" type="number" min="1" value={day} onChange={(event) => setDay(event.target.value)} required /></label><label className="field-label">当天顺序<input className="text-input" type="number" min="1" value={order} onChange={(event) => setOrder(event.target.value)} required /></label></div>
      <label className="field-label">活动名称<input className="text-input" value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
      <div className="date-fields"><label className="field-label">类型<select className="text-input" value={type} onChange={(event) => setType(event.target.value as Activity["type"])}><option value="sight">景点</option><option value="food">餐饮</option><option value="hotel">住宿</option><option value="transport">交通</option><option value="other">其他</option></select></label><label className="field-label">开始时间<input className="text-input" type="time" value={time} onChange={(event) => setTime(event.target.value)} /></label></div>
      <div className="date-fields"><label className="field-label">时长（分钟）<input className="text-input" type="number" min="1" value={duration} onChange={(event) => setDuration(event.target.value)} /></label><label className="field-label">预计费用<input className="text-input" type="number" min="0" step="0.01" value={price} onChange={(event) => setPrice(event.target.value)} /></label></div>
      <label className="field-label">地点<input className="text-input" value={location} onChange={(event) => setLocation(event.target.value)} /></label>
      <label className="field-label">说明<textarea className="text-area compact-text-area" value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      <button className="primary-button full-button" disabled={loading}>{loading ? "保存中…" : "保存活动"}</button>
    </form>
  </ModalSheet>;
}
