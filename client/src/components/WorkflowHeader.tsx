import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface Step {
  id: string;
  label: string;
  completed: boolean;
  active: boolean;
}

interface WorkflowHeaderProps {
  steps: Step[];
  title: string;
  description: string;
}

export function WorkflowHeader({ steps, title, description }: WorkflowHeaderProps) {
  return (
    <div className="border-b border-border bg-card px-6 py-4">
      <div className="flex items-center gap-2 mb-3">
        {steps.map((step, index) => (
          <div key={step.id} className="flex items-center gap-2">
            <div
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-colors",
                step.active && "bg-primary text-primary-foreground",
                step.completed && !step.active && "bg-success/10 text-success",
                !step.active && !step.completed && "bg-muted text-muted-foreground"
              )}
            >
              <span
                className={cn(
                  "flex h-5 w-5 items-center justify-center rounded-full text-xs",
                  step.active && "bg-primary-foreground/20 text-primary-foreground",
                  step.completed && !step.active && "bg-success text-success-foreground",
                  !step.active && !step.completed && "bg-muted-foreground/20 text-muted-foreground"
                )}
              >
                {step.completed && !step.active ? (
                  <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none">
                    <path d="M2 6l3 3 5-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : (
                  index + 1
                )}
              </span>
              {step.label}
            </div>
            {index < steps.length - 1 && (
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            )}
          </div>
        ))}
      </div>
      <h1 className="text-2xl font-bold text-foreground">{title}</h1>
      <p className="text-muted-foreground mt-1">{description}</p>
    </div>
  );
}
