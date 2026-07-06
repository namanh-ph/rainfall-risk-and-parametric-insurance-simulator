/**
 * Display-layer formatters. Pure and side-effect free.
 * Locale defaults to en-AU (Australian / British English conventions)
 */

const audFormatter = new Intl.NumberFormat("en-AU", {
  style: "currency",
  currency: "AUD",
  maximumFractionDigits: 0,
});

const integerFormatter = new Intl.NumberFormat("en-AU");

const decimalFormatter = new Intl.NumberFormat("en-AU", {
  maximumFractionDigits: 2,
});

const dateFormatter = new Intl.DateTimeFormat("en-AU", {
  year: "numeric",
  month: "short",
  day: "2-digit",
});

const dateTimeFormatter = new Intl.DateTimeFormat("en-AU", {
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return audFormatter.format(value);
}

// Backwards-compatible alias
export const formatCurrencyAud = formatCurrency;

export function formatNumber(
  value: number | null | undefined,
  decimals = 0,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  if (decimals <= 0) return integerFormatter.format(value);
  return new Intl.NumberFormat("en-AU", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  }).format(value);
}

export function formatPercent(
  ratio: number | null | undefined,
  decimals = 1,
): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return "-";
  return new Intl.NumberFormat("en-AU", {
    style: "percent",
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  }).format(ratio);
}

export const percent = formatPercent;
export const integer = (v: number | null | undefined) => formatNumber(v, 0);
export const decimal = (v: number | null | undefined) => formatNumber(v, 2);

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "-";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "-";
  return dateFormatter.format(date);
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "-";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "-";
  return dateTimeFormatter.format(date);
}

export function formatMm(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${decimalFormatter.format(value)} mm`;
}

// Backwards-compatible alias
export const formatMillimetres = formatMm;

export function formatDistanceKm(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${decimalFormatter.format(value)} km`;
}

export const formatKilometres = formatDistanceKm;

export function formatRiskScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return decimalFormatter.format(value);
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}
