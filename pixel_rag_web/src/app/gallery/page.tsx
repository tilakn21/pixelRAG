// pixel_rag_web/src/app/gallery/page.tsx
"use client";

import Link from "next/link";

const CATEGORIES = [
  { id: "all", name: "All Photos", icon: "🖼️", desc: "View your entire collection uncategorized.", color: "var(--cat-other)", link: "/photos" },
  { id: "people", name: "People", icon: "👤", desc: "View all identified individuals.", color: "var(--cat-people)", link: "/people" },
  { id: "landscape", name: "Landscapes", icon: "🏞️", desc: "Nature, mountains, and outdoors.", color: "var(--cat-landscape)", link: "/photos?category=landscape" },
  { id: "food", name: "Food & Drink", icon: "🍔", desc: "Meals, dining, and ingredients.", color: "var(--cat-food)", link: "/photos?category=food" },
  { id: "architecture", name: "Architecture", icon: "🏛️", desc: "Buildings, cities, and indoor scenes.", color: "var(--cat-architecture)", link: "/photos?category=architecture" },
  { id: "document", name: "Documents", icon: "📄", desc: "Screenshots, receipts, and text.", color: "var(--cat-document)", link: "/photos?category=document" },
];

export default function GalleryHubPage() {
  return (
    <div style={{ paddingTop: "var(--space-6)" }}>
      <h1 className="page-title">Gallery</h1>
      <p className="page-subtitle">Choose a category to explore your collection</p>

      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: "var(--space-4)",
        marginTop: "var(--space-6)"
      }}>
        {CATEGORIES.map((cat) => (
          <Link key={cat.id} href={cat.link} className="category-card" style={{ borderTop: `4px solid ${cat.color}` }}>
            <div className="category-card__icon">{cat.icon}</div>
            <div className="category-card__title">{cat.name}</div>
            <div className="category-card__desc">{cat.desc}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
