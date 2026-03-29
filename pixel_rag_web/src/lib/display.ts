const CATEGORY_LABELS: Record<string, string> = {
  people: "People",
  landscape: "Landscape",
  food: "Food",
  architecture: "Architecture",
  document: "Document",
  other: "Other",
};

export function formatCompactNumber(value: number | null | undefined): string {
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: value && value < 1000 ? 0 : 1,
  }).format(value ?? 0);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "Undated";

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Unknown time";

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatLocation(parts: Array<string | null | undefined>): string {
  const value = parts.filter(Boolean).join(", ");
  return value || "No location data";
}

export function formatSceneCategory(category: string | null | undefined): string {
  if (!category) return "Unclassified";
  return CATEGORY_LABELS[category] ?? category;
}

export function formatLibraryLabel(path: string | null | undefined): string {
  if (!path) return "No folder connected";
  const segments = path.split("/").filter(Boolean);
  return segments.at(-1) ?? path;
}

export function formatPurityScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "Unscored";

  const normalized = score <= 1 ? score * 100 : score;
  return `${Math.round(normalized)}% purity`;
}
