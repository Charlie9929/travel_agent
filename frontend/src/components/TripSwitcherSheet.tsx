import { CalendarDays, ChevronRight, Plus } from "lucide-react";
import { ModalSheet } from "./ModalSheet";

export type TripOption = {
  id: number;
  title: string;
  city: string;
  startDate: string;
  endDate: string;
  status?: string;
};

export function TripSwitcherSheet({ trips, currentTripId, onSelect, onCreate, onSettings, onClose }: { trips: TripOption[]; currentTripId: number; onSelect: (tripId: number) => void; onCreate: () => void; onSettings: () => void; onClose: () => void }) {
  return (
    <ModalSheet title="我的旅行" onClose={onClose} wide>
      <p className="sheet-intro">切换当前旅行，或创建一场新的旅行。</p>
      <div className="trip-switcher-list">
        {trips.map((trip) => <button className={`trip-switcher-card ${trip.id === currentTripId ? "is-current" : ""}`} key={trip.id} onClick={() => onSelect(trip.id)}><span className="trip-switcher-icon"><CalendarDays size={21} /></span><span className="trip-switcher-content"><strong>{trip.title}</strong><small>{trip.city} · {trip.startDate}—{trip.endDate}</small>{trip.status && <em>{trip.status}</em>}</span><ChevronRight size={18} /></button>)}
      </div>
      <button className="secondary-button full-button create-trip-button" onClick={onSettings}>旅行设置</button>
      <button className="primary-button full-button create-trip-button" onClick={onCreate}><Plus size={18} />新建旅行</button>
    </ModalSheet>
  );
}
