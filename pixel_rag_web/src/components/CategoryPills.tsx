// pixel_rag_web/src/components/CategoryPills.tsx
"use client";

import {
  CATEGORY_LABELS,
  CATEGORY_MARKS,
  SCENE_CATEGORIES,
  UNSORTED,
} from "@/lib/categories";

// Driven from lib/categories.ts so the pill list can never drift from what the
// classifier actually produces. Previously hard-coded to 6 entries while the
// backend wrote 14, leaving ~8,000 photos unreachable.
const CATEGORIES: { key: string; label: string; mark: string }[] = [
  { key: "all", label: "All", mark: CATEGORY_MARKS.all },
  ...SCENE_CATEGORIES.map((k) => ({
    key: k,
    label: CATEGORY_LABELS[k],
    mark: CATEGORY_MARKS[k],
  })),
  { key: UNSORTED, label: CATEGORY_LABELS[UNSORTED], mark: CATEGORY_MARKS[UNSORTED] },
];

interface CategoryPillsProps {
  active: string | null;
  counts?: Record<string, number>;
  onSelect: (category: string | null) => void;
}

export default function CategoryPills({
  active,
  counts,
  onSelect,
}: CategoryPillsProps) {
  return (
    <div className="chip-row" role="tablist" aria-label="Categories">
      {CATEGORIES.map((cat) => {
        const isActive = cat.key === "all" ? active === null : active === cat.key;
        const count = cat.key === "all" ? undefined : counts?.[cat.key];
        // Hide categories this library has none of, so the row stays scannable
        // instead of showing a dozen empty buckets. `all` and the active pill
        // always render.
        if (counts && count === 0 && !isActive && cat.key !== "all") return null;

        return (
          <button
            key={cat.key}
            className={`chip ${isActive ? "chip--active" : ""}`}
            style={{
              fontFamily: "var(--font-pixel)",
              textTransform: "uppercase",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "8px 16px",
              borderRadius: "99px",
              border: "var(--border-thick)",
              background: isActive
                ? "var(--electric-blue)"
                : cat.key === UNSORTED
                  ? "var(--sun-yellow)"
                  : "#fff",
              color: isActive ? "#fff" : "var(--obsidian)",
              cursor: "pointer",
              transition: "all 0.1s",
              whiteSpace: "nowrap",
            }}
            onClick={() => onSelect(cat.key === "all" ? null : cat.key)}
            role="tab"
            aria-selected={isActive}
            title={
              cat.key === UNSORTED
                ? "Photos the classifier was not confident about — review these"
                : undefined
            }
          >
            <span style={{ opacity: 0.6 }}>{cat.mark}</span>
            <span>{cat.label}</span>
            {count !== undefined ? (
              <span
                style={{
                  background: isActive
                    ? "rgba(255,255,255,0.2)"
                    : "rgba(0,0,0,0.05)",
                  padding: "0 6px",
                  borderRadius: "4px",
                  fontSize: "0.7rem",
                }}
              >
                {count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
