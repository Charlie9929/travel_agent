import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";

type PageHeaderProps = {
  title: ReactNode;
  subtitle?: string;
  action?: ReactNode;
  onBack?: () => void;
};

export function PageHeader({ title, subtitle, action, onBack }: PageHeaderProps) {
  return (
    <header className={`page-header ${onBack ? "has-back" : ""}`}>
      {onBack && <button className="page-back-button" onClick={onBack} aria-label="返回"><ArrowLeft size={22} /></button>}
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {action}
    </header>
  );
}
