import type { ReactNode } from "react";
import type { Tab } from "../types";
import { BottomNav } from "./BottomNav";

export function AppShell({ activeTab, onTabChange, children }: { activeTab: Tab; onTabChange: (tab: Tab) => void; children: ReactNode }) {
  return (
    <main className="app-frame">
      {children}
      <BottomNav activeTab={activeTab} onChange={onTabChange} />
    </main>
  );
}
