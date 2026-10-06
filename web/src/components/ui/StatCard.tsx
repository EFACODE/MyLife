import type { ComponentType } from "react";

export type StatTone = "default" | "good" | "critical" | "warning";

const VALUE_CLASSES: Record<StatTone, string> = {
  default: "text-gray-900",
  good: "text-green-700",
  critical: "text-red-600",
  warning: "text-amber-600",
};

const ICON_CLASSES: Record<StatTone, string> = {
  default: "bg-blue-50 text-blue-600",
  good: "bg-green-50 text-green-600",
  critical: "bg-red-50 text-red-600",
  warning: "bg-amber-50 text-amber-600",
};

export function StatCard({
  label,
  value,
  tone = "default",
  hint,
  icon: Icon,
}: {
  label: string;
  value: string;
  tone?: StatTone;
  hint?: string;
  icon?: ComponentType<{ className?: string }>;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm sm:p-4 transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs text-gray-500 sm:text-sm">{label}</div>
          <div className={"mt-1 text-lg font-semibold [overflow-wrap:anywhere] sm:text-2xl " + VALUE_CLASSES[tone]}>{value}</div>
          {hint && <div className="mt-0.5 text-xs text-gray-400 [overflow-wrap:anywhere]">{hint}</div>}
        </div>
        {Icon && (
          <span className={"hidden h-9 w-9 shrink-0 sm:flex items-center justify-center rounded-lg " + ICON_CLASSES[tone]}>
            <Icon className="h-4 w-4" />
          </span>
        )}
      </div>
    </div>
  );
}
