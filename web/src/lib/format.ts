// Number formatting shared by every page, so a rate reads the same everywhere.

export function pct(share: number | null | undefined, digits = 1): string {
  if (share === null || share === undefined || Number.isNaN(share)) return "n/a";
  return `${(share * 100).toFixed(digits)}%`;
}

export function points(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "n/a";
  return `${value.toFixed(digits)} pts`;
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  return Math.round(value).toLocaleString("en-US");
}

export function month(iso: string): string {
  const [y, m] = iso.slice(0, 7).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function day(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}
