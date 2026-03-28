// pixel_rag_web/src/components/CategoryPills.tsx
"use client";

const CATEGORIES = [
  { key: "all", emoji: "✨", label: "All" },
  { key: "people", emoji: "👤", label: "People" },
  { key: "landscape", emoji: "🏞️", label: "Landscape" },
  { key: "food", emoji: "🍽️", label: "Food" },
  { key: "architecture", emoji: "🏛️", label: "Architecture" },
  { key: "document", emoji: "📄", label: "Documents" },
  { key: "other", emoji: "📦", label: "Other" },
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
    <div className="pills-row-wrapper">
      <div className="pills-row">
        {CATEGORIES.map((cat) => {
          const isActive = cat.key === "all" ? active === null : active === cat.key;
          const count = cat.key === "all" ? undefined : counts?.[cat.key];
          return (
            <button
              key={cat.key}
              className={`pill ${isActive ? "pill--active" : ""}`}
              onClick={() => onSelect(cat.key === "all" ? null : cat.key)}
            >
              {cat.emoji} {cat.label}
              {count !== undefined && ` (${count})`}
            </button>
          );
        })}
      </div>
    </div>
  );
}
