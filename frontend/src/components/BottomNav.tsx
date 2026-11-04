import { Grid2x2, Home, Map, UsersRound } from "lucide-react";
import type { Tab } from "../types";

const items: { id: Tab; label: string; icon: typeof Home }[] = [
  { id: "lobby", label: "大厅", icon: Home },
  { id: "world", label: "旅行世界", icon: Map },
  { id: "functions", label: "功能", icon: Grid2x2 },
  { id: "home", label: "私人小家", icon: UsersRound },
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
