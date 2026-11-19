export function ProcessingLabel({ label = "处理中" }: { label?: string }) {
  return (
    <span className="processing-label">
      <span>{label}</span>
      <span className="processing-dots" aria-hidden="true">
        {[0, 1, 2].map((index) => <i key={index} style={{ animationDelay: `${index * 0.14}s` }} />)}
      </span>
    </span>
  );
}
