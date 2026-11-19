import { Check } from "lucide-react";

export function ProcessingSteps({ steps, activeStep }: { steps: string[]; activeStep: number }) {
  return (
    <ol className="processing-steps" aria-live="polite" aria-label="处理进度">
      {steps.map((step, index) => {
        const completed = index < activeStep;
        const active = index === activeStep;
        return (
          <li className={completed ? "is-complete" : active ? "is-active" : ""} key={step}>
            <span className="processing-step-icon" aria-hidden="true">
              {completed ? <Check size={13} strokeWidth={3} /> : active ? <i className="processing-step-spinner" /> : <i className="processing-step-pending" />}
            </span>
            <span>{step}</span>
          </li>
        );
      })}
    </ol>
  );
}
