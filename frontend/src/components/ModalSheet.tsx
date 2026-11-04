import { X } from "lucide-react";
import type { ReactNode } from "react";

export function ModalSheet({ title, children, onClose, wide = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className={`modal-sheet ${wide ? "modal-sheet-wide" : ""}`} role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <div className="sheet-handle" />
        <div className="sheet-header">
          <h2>{title}</h2>
          <button className="icon-button icon-button-small" onClick={onClose} aria-label="关闭"><X size={22} /></button>
        </div>
        {children}
      </section>
    </div>
  );
}
