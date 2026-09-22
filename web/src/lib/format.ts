/** Format integer minor units (e.g. cents) as a decimal amount with its currency. */
export function money(minor: number, currency: string): string {
  const amount = (minor / 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${currency} ${amount}`;
}

/** Parse a decimal amount (e.g. from a `type="number"` input) into integer minor units. */
export function parseMoneyInput(value: string): number {
  const amount = Number.parseFloat(value);
  return Number.isFinite(amount) ? Math.round(amount * 100) : 0;
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
