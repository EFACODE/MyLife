/** Format integer minor units (e.g. cents) as a decimal amount with its currency. */
export function money(minor: number, currency: string): string {
  return `${currency} ${(minor / 100).toFixed(2)}`;
}
