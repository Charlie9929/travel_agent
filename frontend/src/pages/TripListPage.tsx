import { CalendarDays, ChevronRight, MapPinned, Plus, Sparkles } from "lucide-react";
import type { ApiTrip } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";

function statusLabel(trip: ApiTrip) {
  if (trip.status === "finished") return "旅行手帐";
  if (trip.status === "ongoing") return "旅行中";
  return "待出发";
}

function TripCard({ trip, onOpen }: { trip: ApiTrip; onOpen: () => void }) {
  return <button className={`trip-list-card ${trip.status === "finished" ? "is-history" : ""}`} onClick={onOpen}>
    <span className="trip-list-icon">{trip.status === "finished" ? <CalendarDays size={21} /> : <MapPinned size={21} />}</span>
    <span className="trip-list-copy"><strong>{trip.title}</strong><small>{trip.city} · {trip.start_date} 至 {trip.end_date} · {trip.traveler_count ?? 0}人</small><em>{statusLabel(trip)}</em></span>
    <ChevronRight size={19} />
  </button>;
}

export function TripListPage({ trips, onCreate, onOpenTrip, onOpenHistory }: { trips: ApiTrip[]; onCreate: () => void; onOpenTrip: (tripId: number) => void; onOpenHistory: (tripId: number) => void }) {
  const currentTrips = trips.filter((trip) => trip.status !== "finished");
  const historyTrips = trips.filter((trip) => trip.status === "finished");
  return <div className="page page-trip-list">
    <StatusBar />
    <PageHeader title="我的行程" subtitle="选择一场旅行，或让 Agent 规划新的旅程" action={<button className="icon-button" onClick={onCreate} aria-label="新建行程"><Plus size={23} /></button>} />
    {!trips.length ? <section className="itinerary-empty"><Sparkles size={30} /><h2>还没有行程</h2><p>创建旅行后，Agent 会根据日期、预算和同行者需求生成路线。</p><button className="primary-button" onClick={onCreate}>新建第一场旅行</button></section> : <>
      <section className="trip-list-section"><h2>当前行程</h2>{currentTrips.length ? currentTrips.map((trip) => <TripCard key={trip.id} trip={trip} onOpen={() => onOpenTrip(trip.id)} />) : <p className="trip-list-empty">暂时没有进行中或待出发的旅行。</p>}</section>
      {!!historyTrips.length && <section className="trip-list-section history-trip-section"><h2>历史旅行</h2><p>点击后直接打开该次旅行的旅行手帐</p>{historyTrips.map((trip) => <TripCard key={trip.id} trip={trip} onOpen={() => onOpenHistory(trip.id)} />)}</section>}
    </>}
  </div>;
}
