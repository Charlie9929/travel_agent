import { BookOpenText, Camera, ChevronRight, Clock3, Plus, Receipt, WalletCards } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { StatusBar } from "../components/StatusBar";
import type { Workspace } from "../types";

const icons = [Clock3, WalletCards, Camera, BookOpenText];

export function FunctionsPage({ workspace, onOpen, onCreateExpense, onCreateRecord }: { workspace: Workspace; onOpen: (label: string) => void; onCreateExpense: () => void; onCreateRecord: () => void }) {
  const rows = [
    ["行程版本", `当前第 ${workspace.version} 版 · 查看真实记录`],
    ["记账与分账", "查看账单和成员分摊"],
    ["旅行手帐", "查看本次旅行的照片与文字记录"],
    ["攻略导入", "从攻略文本提取行程候选"],
  ] as const;
  return (
    <div className="page page-functions">
      <StatusBar />
      <PageHeader title="旅行工具" />
      <section className="trip-overview"><small>本次旅行</small><strong>{workspace.city}</strong><span>{workspace.startDate}—{workspace.endDate} · {workspace.travelerCount}人</span><b>{workspace.status === "finished" ? "已结束" : workspace.status === "ongoing" ? "旅行中" : "规划中"}</b></section>
      <section className="tool-quick-actions" aria-label="快捷记录">
        <button onClick={onCreateExpense}><span><Receipt size={19} /></span><strong>新增账单</strong><small>记录公共或活动费用</small><Plus size={16} /></button>
        <button onClick={onCreateRecord}><span><Camera size={19} /></span><strong>新增手帐</strong><small>写文字并上传最多 3 张图</small><Plus size={16} /></button>
      </section>
      <div className="function-list">
        {rows.map(([title, description], index) => {
          const Icon = icons[index];
          return <button key={title} className="list-row function-row" onClick={() => onOpen(title)}><Icon size={22} /><span><strong>{title}</strong><small>{description}</small></span><ChevronRight size={20} /></button>;
        })}
      </div>
      <section className="closed-feature"><strong>当前数据来自真实行程</strong><span>账单、手帐和版本记录会随行程持续更新</span></section>
    </div>
  );
}
