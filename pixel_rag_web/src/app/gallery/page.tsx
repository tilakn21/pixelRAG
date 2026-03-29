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
    <div className="bento-container" style={{ display: "grid", gap: "20px", gridTemplateColumns: "repeat(12, 1fr)", padding: "20px 0" }}>
      {/* Gallery Hero */}
      <article className="panel animate-reveal stagger-1" style={{ gridColumn: "span 9", background: "var(--electric-purple)", color: "#fff", minHeight: "360px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div className="title-block">
          <span className="eyebrow" style={{ fontFamily: "var(--font-pixel)", color: "var(--sun-yellow)" }}>[ CURATED_CHANNELS ]</span>
          <h1 className="page-title" style={{ fontFamily: "var(--font-pixel)", fontSize: "var(--text-3xl)", textTransform: "uppercase" }}>GALLERY_HUB</h1>
          <p className="page-subtitle" style={{ fontSize: "var(--text-lg)", maxWidth: "540px", opacity: 0.9 }}>
            Experience the archive through focused collections. Each plate represents a thematic resolution pass.
          </p>
        </div>
      </article>

      {/* Dynamic Asset Grid - Character or Abstraction */}
      <article className="panel animate-reveal stagger-2 video-panel" style={{ gridColumn: "span 3", background: "var(--obsidian)", display: "flex", alignItems: "center", justifyContent: "center", padding: "0", overflow: "hidden", minHeight: "360px" }}>
         <video autoPlay loop muted playsInline style={{ width: "100%", height: "100%", objectFit: "cover", opacity: 0.8 }}>
            <source src="/animations gifs/From KlickPin CF By Antonin Waterkeyn _ Code design graphics.mp4" type="video/mp4" />
         </video>
         <div className="video-overlay" style={{ alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontFamily: "var(--font-pixel)", fontSize: "0.6rem", background: "var(--sun-yellow)", color: "#000", padding: "2px 6px" }}>MAPPING_ACTIVE</span>
         </div>
      </article>

      {/* Gallery Layout */}
      <div style={{ gridColumn: "span 12", display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: "24px" }}>
        {CHAPTERS.map((chapter, index) => (
          <Link 
            key={chapter.id} 
            href={chapter.link} 
            className={`panel animate-reveal stagger-${(index % 3) + 3}`}
            style={{ 
              textDecoration: "none", 
              display: "flex",
              flexDirection: "column",
              gap: "12px",
              background: index % 3 === 0 ? "var(--sun-yellow)" : index % 3 === 1 ? "var(--electric-blue)" : "var(--obsidian)",
              color: index % 3 === 0 ? "#000" : "#fff",
              minHeight: "280px",
              justifyContent: "space-between"
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <span style={{ fontFamily: "var(--font-pixel)", fontSize: "2rem" }}>{chapter.mark}</span>
              <span style={{ fontFamily: "var(--font-pixel)", fontSize: "0.8rem", opacity: 0.6 }}>[ CHAPTER_{chapter.id.toUpperCase()} ]</span>
            </div>
            <div>
              <h3 style={{ fontFamily: "var(--font-pixel)", fontSize: "1.8rem", textTransform: "uppercase", margin: "0 0 8px 0" }}>{chapter.title}</h3>
              <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem", lineHeight: "1.4", opacity: 0.9 }}>{chapter.description}</p>
            </div>
            <div style={{ alignSelf: "flex-end", fontFamily: "var(--font-pixel)", fontSize: "1rem" }}>
              ENTER_ROUTE &gt;&gt;
            </div>
          </Link>
        ))}
      </div>

      {/* Marquee Ticker */}
      <article className="panel" style={{ gridColumn: "span 12", background: "var(--obsidian)", color: "#fff", padding: "0", display: "flex", alignItems: "center", overflow: "hidden", height: "60px" }}>
        <div className="marquee" style={{ whiteSpace: "nowrap", fontSize: "1.5rem", fontFamily: "var(--font-pixel)" }}>
          <div className="marquee-content" style={{ display: "inline-block", paddingLeft: "100%", animation: "marquee 35s linear infinite" }}>
            CURATED ROUTES ACTIVE • EXHIBITION COMPONENT LOADED • VISUAL NARRATIVE SYNCED • PIXELRAG V1.0 • 
          </div>
        </div>
      </article>
    </div>
  );
}
