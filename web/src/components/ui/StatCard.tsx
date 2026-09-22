export type StatTone = "default" | "good" | "critical";

const TONE_CLASSES: Record<StatTone, string> = {
  default: "text-gray-900",
  good: "text-green-700",
  critical: "text-red-600",
};

export function StatCard({
  label,
  value,
  tone = "default",
  hint,
}: {
  label: string;
  value: string;
  tone?: StatTone;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="text-sm text-gray-500">{label}</div>
      <div className={"mt-1 text-2xl font-semibold " + TONE_CLASSES[tone]}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-gray-400">{hint}</div>}
    </div>
  );
}
