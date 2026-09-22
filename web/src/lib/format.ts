/** Format integer minor units (e.g. cents) as a decimal amount with its currency. */
export function money(minor: number, currency: string): string {
  return `${currency} ${(minor / 100).toFixed(2)}`;
}

/** Sum integer minor units per currency, then format each total with `money`. */
export function moneyByCurrency(entries: { amount_minor: number; currency: string }[]): string {
  const totals = new Map<string, number>();
  for (const entry of entries) {
    totals.set(entry.currency, (totals.get(entry.currency) ?? 0) + entry.amount_minor);
  }
  if (totals.size === 0) return "—";
  return [...totals.entries()].map(([currency, total]) => money(total, currency)).join(" · ");
}

/** Format an ISO date/datetime string as a short local date (dd/mm/yyyy). */
export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR");
}
