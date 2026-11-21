import { ChevronLeft, ChevronRight, CalendarDays } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type ApiDistrictProvince } from "../api/client";
import { ModalSheet } from "./ModalSheet";

export type CreateTripValues = {
  title: string;
  city: string;
  city_adcode: string;
  origin_city: string;
  origin_city_adcode: string;
  start_date: string;
  end_date: string;
  traveler_count: number;
  total_budget?: number;
};

type DateField = "start" | "end";

function parseDateValue(value: string) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  return Number.isFinite(year) && Number.isFinite(month) && Number.isFinite(day)
    ? new Date(year, month - 1, day)
    : null;
}

function dateValue(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function displayDate(value: string) {
  return value ? value.replaceAll("-", "/") : "请选择日期";
}

function calendarDays(month: Date) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const mondayOffset = (first.getDay() + 6) % 7;
  return Array.from({ length: 42 }, (_, index) => new Date(month.getFullYear(), month.getMonth(), index - mondayOffset + 1));
}

function DateRangePicker({
  startDate,
  endDate,
  onStartChange,
  onEndChange,
}: {
  startDate: string;
  endDate: string;
  onStartChange: (value: string) => void;
  onEndChange: (value: string) => void;
}) {
  const pickerRef = useRef<HTMLDivElement>(null);
  const [openField, setOpenField] = useState<DateField | null>(null);
  const [calendarMonth, setCalendarMonth] = useState(() => new Date());
  const start = parseDateValue(startDate);
  const end = parseDateValue(endDate);
  const monthLabel = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long" }).format(calendarMonth);

  useEffect(() => {
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (openField && pickerRef.current && !pickerRef.current.contains(event.target as Node)) setOpenField(null);
    };
    window.addEventListener("pointerdown", closeOnOutsideClick);
    return () => window.removeEventListener("pointerdown", closeOnOutsideClick);
  }, [openField]);

  const openCalendar = (field: DateField) => {
    const selected = parseDateValue(field === "start" ? startDate : endDate);
    const fallback = parseDateValue(field === "end" ? startDate : endDate);
    const target = selected ?? fallback ?? new Date();
    setCalendarMonth(new Date(target.getFullYear(), target.getMonth(), 1));
    setOpenField(field);
  };

  const selectDate = (date: Date) => {
    const value = dateValue(date);
    if (openField === "end" && startDate && value < startDate) return;
    if (openField === "start") {
      onStartChange(value);
      if (endDate && value > endDate) {
        onEndChange("");
        setOpenField("end");
        setCalendarMonth(new Date(date.getFullYear(), date.getMonth(), 1));
      } else if (!endDate) {
        setOpenField("end");
      } else {
        setOpenField(null);
      }
      return;
    }
    if (openField === "end") {
      if (!startDate) {
        onStartChange(value);
        setOpenField("end");
        return;
      }
      onEndChange(value);
      setOpenField(null);
    }
  };

  return (
    <div className="date-range-picker" ref={pickerRef}>
      <label className="field-label">开始日期
        <button type="button" className={`date-input-button ${openField === "start" ? "is-open" : ""}`} onClick={() => openCalendar("start")}>
          <span>{displayDate(startDate)}</span><CalendarDays size={19} />
        </button>
      </label>
      <label className="field-label">结束日期
        <button type="button" className={`date-input-button ${openField === "end" ? "is-open" : ""}`} onClick={() => openCalendar("end")}>
          <span>{displayDate(endDate)}</span><CalendarDays size={19} />
        </button>
      </label>
      {openField && <div className="date-calendar-popover" role="dialog" aria-label="选择旅行日期范围">
        <div className="date-calendar-header">
          <button type="button" className="date-calendar-nav" aria-label="上一个月" onClick={() => setCalendarMonth((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1))}><ChevronLeft size={19} /></button>
          <strong>{monthLabel}</strong>
          <button type="button" className="date-calendar-nav" aria-label="下一个月" onClick={() => setCalendarMonth((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1))}><ChevronRight size={19} /></button>
        </div>
        <div className="date-calendar-weekdays">{["一", "二", "三", "四", "五", "六", "日"].map((day) => <span key={day}>{day}</span>)}</div>
        <div className="date-calendar-grid">
          {calendarDays(calendarMonth).map((day) => {
            const value = dateValue(day);
            const outsideMonth = day.getMonth() !== calendarMonth.getMonth();
            const beforeStart = openField === "end" && Boolean(startDate) && value < startDate;
            const isStart = value === startDate;
            const isEnd = value === endDate;
            const isInRange = Boolean(startDate && endDate && value > startDate && value < endDate);
            return <button
              type="button"
              key={value}
              className={`date-calendar-day ${outsideMonth ? "is-outside" : ""} ${beforeStart ? "is-disabled" : ""} ${isInRange ? "is-in-range" : ""} ${isStart ? "is-start" : ""} ${isEnd ? "is-end" : ""}`}
              disabled={outsideMonth || beforeStart}
              onClick={() => selectDate(day)}
            >{day.getDate()}</button>;
          })}
        </div>
        <small className="date-calendar-hint">{openField === "start" ? "请选择开始日期" : "请选择结束日期"}</small>
      </div>}
    </div>
  );
}

export function CreateTripSheet({ title = "创建第一场旅行", closable = false, onClose, onSubmit }: { title?: string; closable?: boolean; onClose?: () => void; onSubmit: (values: CreateTripValues) => void }) {
  const [tripTitle, setTripTitle] = useState("");
  const [provinces, setProvinces] = useState<ApiDistrictProvince[]>([]);
  const [districtLoading, setDistrictLoading] = useState(true);
  const [districtError, setDistrictError] = useState("");
  const [destinationProvince, setDestinationProvince] = useState("");
  const [destinationCity, setDestinationCity] = useState("");
  const [originProvince, setOriginProvince] = useState("");
  const [originCity, setOriginCity] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [travelerCount, setTravelerCount] = useState("1");
  const [budget, setBudget] = useState("");

  const invalidDateRange = Boolean(startDate && endDate && endDate < startDate);

  useEffect(() => {
    let active = true;
    setDistrictLoading(true);
    api.map.districts()
      .then((result) => {
        if (!active) return;
        setProvinces(result.items);
        setDistrictError("");
      })
      .catch((error: Error) => {
        if (active) setDistrictError(error.message);
      })
      .finally(() => {
        if (active) setDistrictLoading(false);
      });
    return () => { active = false; };
  }, []);

  const destinationCities = useMemo(
    () => provinces.find((province) => province.adcode === destinationProvince)?.cities ?? [],
    [destinationProvince, provinces],
  );
  const originCities = useMemo(
    () => provinces.find((province) => province.adcode === originProvince)?.cities ?? [],
    [originProvince, provinces],
  );

  return (
    <ModalSheet title={title} onClose={onClose ?? (() => undefined)} closable={closable}>
      <p className="sheet-intro">先建立一个真实行程，之后就可以邀请同行者并和 Agent 协作。</p>
      <form className="auth-form" onSubmit={(event) => {
        event.preventDefault();
        if (invalidDateRange) return;
        const destination = destinationCities.find((city) => city.adcode === destinationCity);
        const origin = originCities.find((city) => city.adcode === originCity);
        if (!destination || !origin) return;
        onSubmit({
          title: tripTitle,
          city: destination.name,
          city_adcode: destination.adcode,
          origin_city: origin.name,
          origin_city_adcode: origin.adcode,
          start_date: startDate,
          end_date: endDate,
          traveler_count: Number(travelerCount),
          total_budget: budget ? Number(budget) : undefined,
        });
      }}>
        <label className="field-label">旅行名称<input className="text-input" value={tripTitle} onChange={(event) => setTripTitle(event.target.value)} placeholder="例如：成都三日游" required /></label>
        <fieldset className="location-fieldset">
          <legend>目的地</legend>
          <div className="date-fields">
            <label className="field-label">省级区域
              <select className="text-input" value={destinationProvince} onChange={(event) => { setDestinationProvince(event.target.value); setDestinationCity(""); }} required disabled={districtLoading}>
                <option value="">{districtLoading ? "正在加载…" : "请选择"}</option>
                {provinces.map((province) => <option key={province.adcode} value={province.adcode}>{province.name}</option>)}
              </select>
            </label>
            <label className="field-label">城市/地区
              <select className="text-input" value={destinationCity} onChange={(event) => setDestinationCity(event.target.value)} required disabled={!destinationProvince}>
                <option value="">请选择</option>
                {destinationCities.map((city) => <option key={city.adcode} value={city.adcode}>{city.name}</option>)}
              </select>
            </label>
          </div>
        </fieldset>
        <fieldset className="location-fieldset">
          <legend>出发地</legend>
          <div className="date-fields">
            <label className="field-label">省级区域
              <select className="text-input" value={originProvince} onChange={(event) => { setOriginProvince(event.target.value); setOriginCity(""); }} required disabled={districtLoading}>
                <option value="">{districtLoading ? "正在加载…" : "请选择"}</option>
                {provinces.map((province) => <option key={province.adcode} value={province.adcode}>{province.name}</option>)}
              </select>
            </label>
            <label className="field-label">城市/地区
              <select className="text-input" value={originCity} onChange={(event) => setOriginCity(event.target.value)} required disabled={!originProvince}>
                <option value="">请选择</option>
                {originCities.map((city) => <option key={city.adcode} value={city.adcode}>{city.name}</option>)}
              </select>
            </label>
          </div>
        </fieldset>
        {districtError && <p className="form-error">城市列表加载失败：{districtError}</p>}
        <p className="field-hint">想重点游玩某个区，可在下一步的旅行偏好中说明。</p>
        <DateRangePicker startDate={startDate} endDate={endDate} onStartChange={setStartDate} onEndChange={setEndDate} />
        {invalidDateRange && <p className="form-error">结束日期不能早于开始日期，请重新选择。</p>}
        <div className="date-fields"><label className="field-label">人数<input className="text-input" type="number" min="1" value={travelerCount} onChange={(event) => setTravelerCount(event.target.value)} required /></label><label className="field-label">总预算<input className="text-input" type="number" min="0" step="0.01" value={budget} onChange={(event) => setBudget(event.target.value)} placeholder="可选" /></label></div>
        <button className="primary-button full-button" disabled={districtLoading || Boolean(districtError) || invalidDateRange}>创建行程</button>
      </form>
    </ModalSheet>
  );
}
