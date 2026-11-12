import { useState } from "react";
import { ModalSheet } from "./ModalSheet";

export function CreateTripSheet({ title = "创建第一场旅行", closable = false, onClose, onSubmit }: { title?: string; closable?: boolean; onClose?: () => void; onSubmit: (values: { title: string; city: string; start_date: string; end_date: string }) => void }) {
  const [tripTitle, setTripTitle] = useState("杭州周末旅行");
  const [city, setCity] = useState("杭州");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  return (
    <ModalSheet title={title} onClose={onClose ?? (() => undefined)} closable={closable}>
      <p className="sheet-intro">先建立一个真实行程，之后就可以邀请同行者并和 Agent 协作。</p>
      <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ title: tripTitle, city, start_date: startDate, end_date: endDate }); }}>
        <label className="field-label">旅行名称<input className="text-input" value={tripTitle} onChange={(event) => setTripTitle(event.target.value)} required /></label>
        <label className="field-label">城市<input className="text-input" value={city} onChange={(event) => setCity(event.target.value)} required /></label>
        <div className="date-fields"><label className="field-label">开始日期<input className="text-input" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required /></label><label className="field-label">结束日期<input className="text-input" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} required /></label></div>
        <button className="primary-button full-button">创建行程</button>
      </form>
    </ModalSheet>
  );
}
