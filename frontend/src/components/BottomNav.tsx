import { Grid2x2, Home, Map, UsersRound } from "lucide-react";
import type { Tab } from "../types";

const items: { id: Tab; label: string; icon: typeof Home }[] = [
  { id: "world", label: "行程", icon: Map },
  { id: "lobby", label: "协作大厅", icon: Home },
  { id: "functions", label: "旅行工具", icon: Grid2x2 },
  { id: "home", label: "我的", icon: UsersRound },
];

export function BottomNav({ activeTab, onChange }: { activeTab: Tab; onChange: (tab: Tab) => void }) {
  return (
    <nav className="bottom-nav" aria-label="一级导航">
      {items.map(({ id, label, icon: Icon }) => {
        const active = id === activeTab;
        return (
          <button key={id} className={`nav-item ${active ? "is-active" : ""}`} onClick={() => onChange(id)}>
            <span className="nav-pill"><Icon size={22} strokeWidth={1.7} /></span>
            <span>{label}</span>
          </button>
        );
      })}
    </nav>
  );
}
