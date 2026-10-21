/** Currency amount for display, e.g. €13.00 (en) or 13,00 € (it). */
export function formatPrice(amount: number, currency = "EUR", locale = "en"): string {
  try {
    return new Intl.NumberFormat(locale, { style: "currency", currency }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}
