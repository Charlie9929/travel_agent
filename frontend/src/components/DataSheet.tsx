import { ModalSheet } from "./ModalSheet";

export type DataRow = {
  title: string;
  description?: string;
  meta?: string;
};

export function DataSheet({ title, rows, loading, onClose }: { title: string; rows: DataRow[]; loading: boolean; onClose: () => void }) {
  return (
    <ModalSheet title={title} onClose={onClose}>
      {loading && <div className="empty-chat">正在读取真实数据…</div>}
      {!loading && !rows.length && <div className="empty-chat">暂无数据</div>}
      {!loading && <div className="data-list">{rows.map((row, index) => <article className="data-row" key={`${row.title}-${index}`}><strong>{row.title}</strong>{row.description && <p>{row.description}</p>}{row.meta && <small>{row.meta}</small>}</article>)}</div>}
    </ModalSheet>
  );
}
