import { useEffect, useMemo, useState } from "react";
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
        <div className="date-fields date-range-picker">
          <label className="field-label">开始日期<input className="text-input" type="date" value={startDate} max={endDate || undefined} onChange={(event) => setStartDate(event.target.value)} required /></label>
          <label className="field-label">结束日期<input className="text-input" type="date" value={endDate} min={startDate || undefined} onChange={(event) => setEndDate(event.target.value)} required /></label>
          <div className={`date-range-band ${startDate && endDate && !invalidDateRange ? "is-active" : ""}`} aria-hidden="true"><span /></div>
        </div>
        {invalidDateRange && <p className="form-error">结束日期不能早于开始日期，请重新选择。</p>}
        <div className="date-fields"><label className="field-label">人数<input className="text-input" type="number" min="1" value={travelerCount} onChange={(event) => setTravelerCount(event.target.value)} required /></label><label className="field-label">总预算<input className="text-input" type="number" min="0" step="0.01" value={budget} onChange={(event) => setBudget(event.target.value)} placeholder="可选" /></label></div>
        <button className="primary-button full-button" disabled={districtLoading || Boolean(districtError) || invalidDateRange}>创建行程</button>
      </form>
    </ModalSheet>
  );
}
