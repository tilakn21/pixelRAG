// pixel_rag_web/src/components/CategoryPills.tsx
"use client";

const CATEGORIES = [
  { key: "all", mark: "00", label: "All" },
  { key: "people", mark: "01", label: "People" },
  { key: "landscape", mark: "02", label: "Landscape" },
  { key: "food", mark: "03", label: "Food" },
  { key: "architecture", mark: "04", label: "Architecture" },
  { key: "document", mark: "05", label: "Documents" },
  { key: "other", mark: "06", label: "Other" },
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
          return (
            <button
              key={cat.key}
              className={`chip ${isActive ? "chip--active" : ""}`}
              onClick={() => onSelect(cat.key === "all" ? null : cat.key)}
              role="tab"
              aria-selected={isActive}
            >
              <span className="chip__mark">{cat.mark}</span>
              <span>{cat.label}</span>
              {count !== undefined ? <span className="chip__count">{count}</span> : null}
            </button>
          );
        })}
    </div>
  );
}
