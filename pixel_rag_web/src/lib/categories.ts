// pixel_rag_web/src/lib/categories.ts
//
// SINGLE SOURCE OF TRUTH for scene categories.
//
// These must stay in step with CATEGORY_PROMPTS in
// pixel_rag_core/indexing/scene_classifier.py. They previously drifted badly:
// the classifier produced 14 categories while the UI exposed only 6 pills, so
// ~8,000 correctly-sorted photos (screenshot, night, vehicle, art, event,
// object, map_chart, animal) had no way to be reached by clicking. Anything
// that renders or filters categories should import from here.

export const SCENE_CATEGORIES = [
  "people",
  "document",
  "screenshot",
  "landscape",
  "architecture",
  "food",
  "vehicle",
  "animal",
  "art",
  "event",
  "night",
  "object",
  "map_chart",
  "other",
] as const;

export type SceneCategory = (typeof SCENE_CATEGORIES)[number];

// `unsorted` is the low-confidence review bucket written by the classifier when
// nothing clears the threshold. It is deliberately NOT in SCENE_CATEGORIES —
// it is a workflow state, not a subject — but it still needs a pill so those
// photos are reachable instead of invisible.
export const UNSORTED = "unsorted";

export const CATEGORY_LABELS: Record<string, string> = {
  people: "People",
  document: "Documents",
  screenshot: "Screenshots",
  landscape: "Landscape",
  architecture: "Architecture",
  food: "Food",
  vehicle: "Vehicles",
  animal: "Animals",
  art: "Art",
  event: "Events",
  night: "Night",
  object: "Objects",
  map_chart: "Maps & Charts",
  other: "Other",
  [UNSORTED]: "Unsorted",
};

// Two-digit marks preserve the existing pixel-terminal design language.
export const CATEGORY_MARKS: Record<string, string> = Object.fromEntries(
  ["all", ...SCENE_CATEGORIES, UNSORTED].map((k, i) => [
    k,
    String(i).padStart(2, "0"),
  ])
);

export function formatSceneCategory(category: string | null | undefined): string {
  if (!category) return "Unclassified";
  return CATEGORY_LABELS[category] ?? category;
}
