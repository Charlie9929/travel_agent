import { useState } from "react";
import type { Activity } from "../types";
import { ModalSheet } from "./ModalSheet";

function addMinutes(start: string, duration: number | null) {
  if (!start || duration == null) return "";
  const [hours, minutes] = start.split(":").map(Number);
  const total = hours * 60 + minutes + duration;
  return `${String(Math.floor(total / 60) % 24).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function durationBetween(start: string, end: string) {
  if (!start || !end) return undefined;
  const [startHour, startMinute] = start.split(":").map(Number);
  const [endHour, endMinute] = end.split(":").map(Number);
  const duration = endHour * 60 + endMinute - (startHour * 60 + startMinute);
  return duration > 0 ? duration : undefined;
}

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
  const [endTime, setEndTime] = useState(
    activity?.endTime === "待定"
      ? addMinutes(time, activity?.durationMinutes ?? null)
      : activity?.endTime ?? "",
  );
  const [timeError, setTimeError] = useState("");
  const [location, setLocation] = useState(activity?.location === "地点待定" ? "" : activity?.location ?? "");
  const [price, setPrice] = useState(activity?.estimatedPrice == null ? "" : String(activity.estimatedPrice));
  const [description, setDescription] = useState(activity?.detail === "暂无活动说明" ? "" : activity?.detail ?? "");

  return <ModalSheet title={activity ? "编辑活动" : "新增活动"} onClose={onClose} wide>
    <form className="auth-form" onSubmit={(event) => {
      event.preventDefault();
      const duration = durationBetween(time, endTime);
      if ((time || endTime) && (!time || !endTime || duration == null)) {
        setTimeError("请填写有效的起止时间，结束时间需晚于开始时间");
        return;
      }
      setTimeError("");
      onSubmit({ day_number: Number(day), order_index: Number(order), title: title.trim(), type, start_time: time || undefined, duration_min: duration, location_name: location.trim() || undefined, price_estimated: price ? Number(price) : undefined, description: description.trim() || undefined });
    }}>
      <div className={activity ? "" : "date-fields"}>
        <label className="field-label">第几天<input className="text-input" type="number" min="1" value={day} onChange={(event) => setDay(event.target.value)} required /></label>
        {!activity && <label className="field-label">插入到第几项<input className="text-input" type="number" min="1" max={defaultOrder} value={order} onChange={(event) => setOrder(event.target.value)} required /></label>}
      </div>
      {activity ? <small className="form-help">活动顺序请回到行程页，拖动卡片右上角的排序图标调整。</small> : <small className="form-help">插入后，原来位于该序号及后面的活动会自动向后顺延。</small>}
      <label className="field-label">活动名称<input className="text-input" value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
      <label className="field-label">类型<select className="text-input" value={type} onChange={(event) => setType(event.target.value as Activity["type"])}><option value="sight">景点</option><option value="food">餐饮</option><option value="hotel">住宿</option><option value="transport">交通</option><option value="other">其他</option></select></label>
      <div className="date-fields"><label className="field-label">开始时间<input className="text-input" type="time" value={time} onChange={(event) => {
        const nextStart = event.target.value;
        const currentDuration = durationBetween(time, endTime) ?? activity?.durationMinutes ?? null;
        setTime(nextStart);
        setEndTime(nextStart ? addMinutes(nextStart, currentDuration) : "");
        setTimeError("");
      }} /></label><label className="field-label">结束时间<input className="text-input" type="time" value={endTime} onChange={(event) => { setEndTime(event.target.value); setTimeError(""); }} /></label></div>
      {timeError && <small className="inline-error">{timeError}</small>}
      <label className="field-label">预计费用<input className="text-input" type="number" min="0" step="0.01" value={price} onChange={(event) => setPrice(event.target.value)} /></label>
      <label className="field-label">地点<input className="text-input" value={location} onChange={(event) => setLocation(event.target.value)} /></label>
      <label className="field-label">说明<textarea className="text-area compact-text-area" value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      <button className="primary-button full-button" disabled={loading}>{loading ? "保存中…" : "保存活动"}</button>
    </form>
  </ModalSheet>;
}
