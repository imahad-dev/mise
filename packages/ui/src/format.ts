/** Currency amount for display, e.g. €13.00 (en), 13,00 € (it) or Rs 2,100 (PKR, whole rupees). */
export function formatPrice(amount: number, currency = "EUR", locale = "en"): string {
  try {
    if (currency === "PKR") {
      const text = new Intl.NumberFormat("en-PK", {
        style: "currency",
        currency: "PKR",
        currencyDisplay: "symbol",
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(amount);
      // shortcut: ICU data varies; drop when en-PK symbol is stable
      return text.replace(/^PKR\s*/, "Rs ");
    }
    return new Intl.NumberFormat(locale, { style: "currency", currency }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}
