import { ChevronLeft, ChevronRight } from "lucide-react";

import { monthYearLabel, shiftMonth, type YearMonth } from "../../lib/format";

/** Steps through months one at a time: ‹ Outubro de 2026 ›. */
export function MonthNavigator({
  value,
  onChange,
  label = "Período",
}: {
  value: YearMonth;
  onChange: (value: YearMonth) => void;
  label?: string;
}) {
  const buttonClass =
    "flex h-11 w-11 items-center justify-center rounded-lg text-gray-600 transition-colors hover:bg-gray-100 active:bg-gray-200 sm:h-9 sm:w-9";
  return (
    <div role="group" aria-label={label} className="flex w-full items-center justify-between gap-1 rounded-lg border border-gray-200 bg-white p-0.5 sm:w-auto">
      <button
        type="button"
        aria-label="Mês anterior"
        onClick={() => onChange(shiftMonth(value, -1))}
        className={buttonClass}
      >
        <ChevronLeft className="h-5 w-5" />
      </button>
      <span
        aria-live="polite"
        className="min-w-[10.5rem] flex-1 text-center sm:flex-none text-sm font-medium text-gray-900"
      >
        {monthYearLabel(value)}
      </span>
      <button
        type="button"
        aria-label="Próximo mês"
        onClick={() => onChange(shiftMonth(value, 1))}
        className={buttonClass}
      >
        <ChevronRight className="h-5 w-5" />
      </button>
    </div>
  );
}
