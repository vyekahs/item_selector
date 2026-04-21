/**
 * Shared formatting helpers. Outputs are locale-stable (`ko-KR`) and
 * never throw on null/undefined — they return a placeholder instead so
 * UI cells stay aligned.
 */

const KRW = new Intl.NumberFormat('ko-KR', {
  style: 'currency',
  currency: 'KRW',
  maximumFractionDigits: 0,
});

const PCT = new Intl.NumberFormat('ko-KR', {
  style: 'percent',
  maximumFractionDigits: 1,
});

const NUM = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 });

const FLOAT1 = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 });

const PLACEHOLDER = '—';

export function formatKrw(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return PLACEHOLDER;
  return KRW.format(Math.round(value));
}

export function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return PLACEHOLDER;
  return NUM.format(Math.round(value));
}

/** Accepts a 0-1 ratio (e.g. 0.19) and renders as `+19%` / `-3%`. */
export function formatRatioPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return PLACEHOLDER;
  const sign = value > 0 ? '+' : '';
  return `${sign}${PCT.format(value)}`;
}

/** Accepts a percentage (e.g. 64) and renders as `64%` / `-3.5%`. */
export function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return PLACEHOLDER;
  return `${FLOAT1.format(value)}%`;
}

/** Accepts a decimal (e.g. 0.055) and renders as `5.5%`. No leading sign. */
export function formatDecimalPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return PLACEHOLDER;
  return `${FLOAT1.format(value * 100)}%`;
}

/** Compact thousand-scale counts, e.g. 28000 -> "28K". */
export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return PLACEHOLDER;
  if (Math.abs(value) >= 1_000_000) return `${FLOAT1.format(value / 1_000_000)}M`;
  if (Math.abs(value) >= 1_000) return `${FLOAT1.format(value / 1_000)}K`;
  return NUM.format(value);
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return PLACEHOLDER;
  return FLOAT1.format(value);
}
