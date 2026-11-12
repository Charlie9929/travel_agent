import { useState } from "react";
import { ModalSheet } from "./ModalSheet";

export type CreateTripValues = {
  title: string;
  city: string;
  origin_city?: string;
  start_date: string;
  end_date: string;
  traveler_count: number;
  total_budget?: number;
};

export function CreateTripSheet({ title = "创建第一场旅行", closable = false, onClose, onSubmit }: { title?: string; closable?: boolean; onClose?: () => void; onSubmit: (values: CreateTripValues) => void }) {
  const [tripTitle, setTripTitle] = useState("");
  const [city, setCity] = useState("");
  const [originCity, setOriginCity] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [travelerCount, setTravelerCount] = useState("1");
  const [budget, setBudget] = useState("");

  return (
    <ModalSheet title={title} onClose={onClose ?? (() => undefined)} closable={closable}>
      <p className="sheet-intro">先建立一个真实行程，之后就可以邀请同行者并和 Agent 协作。</p>
      <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ title: tripTitle, city, origin_city: originCity || undefined, start_date: startDate, end_date: endDate, traveler_count: Number(travelerCount), total_budget: budget ? Number(budget) : undefined }); }}>
        <label className="field-label">旅行名称<input className="text-input" value={tripTitle} onChange={(event) => setTripTitle(event.target.value)} placeholder="例如：成都三日游" required /></label>
        <label className="field-label">目的地<input className="text-input" value={city} onChange={(event) => setCity(event.target.value)} placeholder="例如：成都" required /></label>
        <label className="field-label">出发地<input className="text-input" value={originCity} onChange={(event) => setOriginCity(event.target.value)} placeholder="可选" /></label>
        <div className="date-fields"><label className="field-label">开始日期<input className="text-input" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required /></label><label className="field-label">结束日期<input className="text-input" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} required /></label></div>
        <div className="date-fields"><label className="field-label">人数<input className="text-input" type="number" min="1" value={travelerCount} onChange={(event) => setTravelerCount(event.target.value)} required /></label><label className="field-label">总预算<input className="text-input" type="number" min="0" step="0.01" value={budget} onChange={(event) => setBudget(event.target.value)} placeholder="可选" /></label></div>
        <button className="primary-button full-button">创建行程</button>
      </form>
    </ModalSheet>
  );
}
