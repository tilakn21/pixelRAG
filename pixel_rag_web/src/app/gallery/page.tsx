"use client";

import Link from "next/link";
import AsciiField from "@/components/AsciiField";

const CHAPTERS = [
  {
    id: "all",
    mark: "00",
    title: "All Photos",
    description: "The full archive, presented as a quiet scroll with minimal chrome.",
    link: "/photos",
  },
  {
    id: "people",
    mark: "01",
    title: "People",
    description: "A face-led chapter for reviewing identity clusters and human patterns.",
    link: "/people",
  },
  {
    id: "landscape",
    mark: "02",
    title: "Landscapes",
    description: "Open air, topography, weather, and atmosphere.",
    link: "/photos?category=landscape",
  },
  {
    id: "food",
    mark: "03",
    title: "Food & Drink",
    description: "Meals, tables, ingredients, and convivial still life.",
    link: "/photos?category=food",
  },
  {
    id: "architecture",
    mark: "04",
    title: "Architecture",
    description: "Civic geometry, interiors, facades, and quiet structure.",
    link: "/photos?category=architecture",
  },
  {
    id: "document",
    mark: "05",
    title: "Documents",
    description: "Text-rich frames, receipts, notes, screenshots, and paper memory.",
    link: "/photos?category=document",
  },
];

export default function GalleryHubPage() {
  return (
    <div className="route">
      <section className="route-hero route-hero--split">
        <div className="title-block">
          <span className="eyebrow">Curated Exhibition</span>
          <h1 className="page-title">Move through the archive in chapters.</h1>
          <p className="page-subtitle">
            The gallery shifts PixelRAG away from dashboard categories and toward composed routes through the collection.
          </p>
        </div>

        <AsciiField
          className="hero-ascii"
          variant="horizon"
          tone="silver"
          caption="Chapter breaks / negative space"
          scale="hero"
        />
      </section>

      <section className="gallery-layout">
        <aside className="gallery-rail">
          <div className="panel panel--quiet">
            <span className="panel__title">Chapter Rail</span>
            <div className="gallery-rail__nav">
              {CHAPTERS.map((chapter) => (
                <a key={chapter.id} href={`#${chapter.id}`} className="gallery-rail__link">
                  <span>{chapter.title}</span>
                  <span className="mono">{chapter.mark}</span>
                </a>
              ))}
            </div>
          </div>

          <div className="panel panel--quiet">
            <span className="panel__title">Curation Note</span>
            <p>
              Each route keeps the imagery dominant while navigation and metadata stay restrained and low-noise.
            </p>
          </div>
        </aside>

        <div className="chapter-grid">
          {CHAPTERS.map((chapter) => (
            <Link key={chapter.id} id={chapter.id} href={chapter.link} className="category-plate">
              <span className="category-plate__mark">{chapter.mark}</span>
              <h3>{chapter.title}</h3>
              <p>{chapter.description}</p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
