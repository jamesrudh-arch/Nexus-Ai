/**
 * Formatting for values the backend sends as exact decimal strings.
 *
 * The obvious implementation — `Number(value).toFixed(2)` — is not used, and the reason is worth
 * stating because it looks like pedantry until it costs money: a double cannot represent most
 * decimals exactly, so `0.1 + 0.2` is `0.30000000000000004` and a price of `1.005` rounds to `1.00`
 * rather than `1.01`. On a screen whose entire job is to be believed about money, that is not an
 * acceptable error, and it is invisible in every test that uses round numbers.
 *
 * So rounding and grouping here are done on the digits, as strings. It is slower and longer than the
 * one-liner. It is also correct for every value the API can produce, including the ones with eight
 * decimal places that the fill model quantizes to.
 */

/** Sign of an exact decimal string, without converting it to a float. */
export function signOf(value: string | null | undefined): -1 | 0 | 1 {
  if (value === null || value === undefined) return 0;
  const trimmed = value.trim();
  if (trimmed === "" || trimmed === "-" || trimmed === "+") return 0;
  const negative = trimmed.startsWith("-");
  const digits = trimmed.replace(/^[+-]/, "").replace(/^0+(?=\d)/, "");
  const isZero = /^0*\.?0*$/.test(digits);
  if (isZero) return 0;
  return negative ? -1 : 1;
}

interface DecimalParts {
  negative: boolean;
  integer: string;
  fraction: string;
}

function split(value: string): DecimalParts {
  const trimmed = value.trim();
  const negative = trimmed.startsWith("-");
  const unsigned = trimmed.replace(/^[+-]/, "");
  const [integer = "0", fraction = ""] = unsigned.split(".");
  return { negative, integer: integer || "0", fraction };
}

/**
 * Round an exact decimal string to `digits` places, half away from zero.
 *
 * Half-away-from-zero matches what the backend's `Decimal.quantize` does with ROUND_HALF_UP on a
 * positive value, and it is the convention a finance screen is expected to follow: a half cent is
 * not silently dropped, because dropping it always in one direction is a slow leak.
 */
export function roundDecimal(value: string, digits: number): string {
  const { negative, integer, fraction } = split(value);
  if (fraction.length <= digits) {
    const padded = fraction.padEnd(digits, "0");
    return `${negative ? "-" : ""}${integer}${padded ? `.${padded}` : ""}`;
  }
  const kept = fraction.slice(0, digits);
  const nextDigit = Number(fraction[digits]);
  let carried = kept;
  let intPart = integer;
  if (nextDigit >= 5) {
    // Add one to the last kept digit, propagating through any run of 9s and into the integer part.
    const digitsOut = kept.split("");
    let index = digitsOut.length - 1;
    while (index >= 0) {
      if (digitsOut[index] === "9") {
        digitsOut[index] = "0";
        index -= 1;
      } else {
        digitsOut[index] = String(Number(digitsOut[index]) + 1);
        break;
      }
    }
    if (index < 0) {
      // Every kept digit was a 9: the carry reaches the integer part.
      intPart = addOne(integer);
      carried = "0".repeat(digits);
    } else {
      carried = digitsOut.join("");
    }
  }
  const body = `${intPart}${carried ? `.${carried}` : ""}`;
  const isZero = /^0*\.?0*$/.test(body);
  return `${negative && !isZero ? "-" : ""}${body}`;
}

function addOne(integer: string): string {
  const out = integer.split("");
  for (let index = out.length - 1; index >= 0; index -= 1) {
    if (out[index] === "9") {
      out[index] = "0";
    } else {
      out[index] = String(Number(out[index]) + 1);
      return out.join("");
    }
  }
  return `1${out.join("")}`;
}

/** Insert thousands separators into the integer part only. */
function group(integer: string): string {
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

export interface MoneyFormatOptions {
  digits?: number;
  /** Prefix a `+` on positive values. P&L is signed; a balance is not. */
  signed?: boolean;
  symbol?: string;
}

/** Format an exact decimal string as money. Never loses a digit to binary floating point. */
export function formatMoney(value: string | null | undefined, options: MoneyFormatOptions = {}): string {
  const { digits = 2, signed = false, symbol = "" } = options;
  if (value === null || value === undefined || value === "") return "—";
  const rounded = roundDecimal(value, digits);
  const { negative, integer, fraction } = split(rounded);
  const sign = negative ? "−" : signed ? "+" : "";
  const body = `${group(integer)}${fraction ? `.${fraction}` : ""}`;
  return `${sign}${symbol}${body}`;
}

/**
 * A P&L value with its direction glyph.
 *
 * §3.3: colour is never the sole signal, so the sign and the arrow travel with the number. A
 * reader who cannot see the colour, or who is looking at a printed page, still gets the right
 * answer.
 */
export function formatPnl(value: string | null | undefined, symbol = ""): string {
  const sign = signOf(value);
  const glyph = sign > 0 ? "▲" : sign < 0 ? "▼" : "•";
  return `${glyph} ${formatMoney(value, { digits: 2, signed: true, symbol })}`;
}

export function pnlTone(value: string | null | undefined): "positive" | "negative" | "neutral" {
  const sign = signOf(value);
  if (sign > 0) return "positive";
  if (sign < 0) return "negative";
  return "neutral";
}

export function formatPercent(value: string | null | undefined, digits = 2): string {
  if (value === null || value === undefined || value === "") return "—";
  return `${formatMoney(value, { digits, signed: true })}%`;
}

/** Quantities carry up to eight places from the fill model; trailing zeros are noise. */
export function formatQuantity(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const rounded = roundDecimal(value, 8);
  const trimmed = rounded.includes(".") ? rounded.replace(/0+$/, "").replace(/\.$/, "") : rounded;
  const { negative, integer, fraction } = split(trimmed || "0");
  return `${negative ? "−" : ""}${group(integer)}${fraction ? `.${fraction}` : ""}`;
}

export function formatPrice(value: string | null | undefined, currency?: string): string {
  if (value === null || value === undefined || value === "") return "—";
  // Prices keep enough places to show the slippage that was applied: rounding a fill price to two
  // decimals would hide the very cost the paper platform exists to measure.
  const digits = split(value).fraction.length > 4 ? 6 : 4;
  return formatMoney(value, { digits, symbol: currency ? `${currency} ` : "" });
}

export function formatBps(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return `${formatMoney(value, { digits: 2, signed: true })} bps`;
}

/** An ISO timestamp as a UTC clock time, labelled, because §3.5 requires the timezone to be shown. */
export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}:${get("second")} UTC`;
}

/** How long ago, for a staleness badge. Deliberately coarse: precision implies freshness it can't prove. */
export function formatAge(iso: string | null | undefined, nowMs = Date.now()): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const seconds = Math.max(0, Math.round((nowMs - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

/** `REASON:detail` is the backend's convention; split it so the UI can style the two halves. */
export function splitReason(reason: string): { code: string; detail: string } {
  const index = reason.indexOf(":");
  if (index < 0) return { code: reason, detail: "" };
  return { code: reason.slice(0, index), detail: reason.slice(index + 1) };
}
