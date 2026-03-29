"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import SearchBar from "@/components/SearchBar";
import { fetchHealth, setLibraryPath } from "@/lib/api";
import { formatCompactNumber } from "@/lib/display";
import type { HealthResponse } from "@/lib/types";

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSwitched, setIsSwitched] = useState(false);
  const [libraryInput, setLibraryInput] = useState("");
  const [setupSaving, setSetupSaving] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (url.searchParams.get("switched") === "true") {
        setIsSwitched(true);
        window.history.replaceState({}, "", "/");
      }
    }

    fetchHealth()
      .then(setHealth)
      .catch(() => {
        setError("PixelRAG could not reach the backend. Start the FastAPI service, then refresh.");
      });
  }, []);

  const handleSetup = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!libraryInput.trim()) return;

    setSetupSaving(true);
    setError(null);
    try {
      await setLibraryPath(libraryInput.trim());
      window.location.href = "/?switched=true";
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Failed to connect this folder.");
    } finally {
      setSetupSaving(false);
    }
  };

  return (
    <div className="bento-container" style={{ display: "grid", gap: "20px", gridTemplateColumns: "repeat(12, 1fr)", padding: "20px 0" }}>
      {/* Hero Section */}
      <article className="panel animate-reveal stagger-1" style={{ gridColumn: "span 9", background: "var(--electric-purple)", color: "#fff", minHeight: "420px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div className="title-block">
          <span className="eyebrow" style={{ color: "var(--sun-yellow)", fontFamily: "var(--font-pixel)" }}>[ ARCHIVE_INITIATED ]</span>
          <h1 className="page-title" style={{ fontFamily: "var(--font-pixel)", fontSize: "var(--text-3xl)", textTransform: "uppercase" }}>STUNNING_MEMORIES</h1>
          <p className="page-subtitle" style={{ color: "rgba(255,255,255,0.9)", fontSize: "var(--text-lg)", maxWidth: "540px" }}>
            PixelRAG is a high-end archival engine that transforms raw local photos into a structured, searchable, and beautiful visual library.
          </p>
        </div>
        <div style={{ marginTop: "40px", display: "flex", gap: "16px" }}>
          <Link href="/photos" className="button button--secondary" style={{ borderRadius: "12px" }}>ENTER_ARCHIVE</Link>
          <Link href="/search" className="button button--secondary" style={{ background: "transparent", color: "#fff", borderRadius: "12px" }}>SEARCH_LATTICE</Link>
        </div>
      </article>

      {/* Character Card 1 */}
      <div className="char-box animate-reveal stagger-2 char-glow" style={{ gridColumn: "span 3" }}>
        <img src="/characters/7fc1b1df319deb84abba4ca60d4c6b0d.jpg" alt="Pixel Character" className="animate-float" />
      </div>

      {/* Marquee Bar */}
      <article className="panel animate-reveal stagger-3" style={{ gridColumn: "span 12", background: "var(--obsidian)", color: "#fff", padding: "0", display: "flex", alignItems: "center", overflow: "hidden", height: "64px" }}>
        <div className="marquee">
          <div className="marquee-content" style={{ fontFamily: "var(--font-pixel)", fontSize: "1.2rem", animationDuration: "25s" }}>
            MAPPING_VISUAL_CLUSTERS • EXTRACTING_METADATA • IDENTITY_PASS_ACTIVE • PIXELRAG_V1.0 • SYSTEM_HEALTH_STABLE •
          </div>
        </div>
      </article>

      {/* Stats Cards */}
      <article className="panel animate-reveal stagger-4" style={{ gridColumn: "span 4", background: "var(--sun-yellow)", color: "#000", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center" }}>
        <span style={{ fontFamily: "var(--font-pixel)", fontSize: "0.8rem" }}>[ TOTAL_NODES ]</span>
        <div style={{ fontFamily: "var(--font-pixel)", fontSize: "4rem", margin: "10px 0" }}>{health?.photo_count ?? "---"}</div>
        <p style={{ fontFamily: "var(--font-pixel)", fontSize: "0.7rem", opacity: 0.6 }}>IMAGES_ONLINE</p>
      </article>

      <article className="panel animate-reveal stagger-5" style={{ gridColumn: "span 4", background: "var(--electric-blue)", color: "#fff", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center" }}>
        <span style={{ fontFamily: "var(--font-pixel)", fontSize: "0.8rem" }}>[ IDENTITIES ]</span>
        <div style={{ fontFamily: "var(--font-pixel)", fontSize: "4rem", margin: "10px 0" }}>{health?.person_count ?? "---"}</div>
        <p style={{ fontFamily: "var(--font-pixel)", fontSize: "0.7rem", opacity: 0.6 }}>HUMAN_CLUSTERS</p>
      </article>

      {/* Character Card 2 */}
      <div className="char-box animate-reveal stagger-6 char-glow" style={{ gridColumn: "span 4" }}>
        <img src="/characters/e87333084ab6bd5d1ed069a8206c904a.jpg" alt="Pixel Avatar" className="animate-float" style={{ animationDelay: "1s" }} />
      </div>

      {/* Search & Metadata Section */}
      <article className="panel animate-reveal stagger-2" style={{ gridColumn: "span 6", display: "flex", flexDirection: "column", gap: "24px", justifyContent: "center" }}>
        <div>
          <span style={{ fontFamily: "var(--font-pixel)", fontSize: "0.7rem", color: "rgba(0,0,0,0.4)" }}>[ DATA_QUERY ]</span>
          <h2 style={{ fontFamily: "var(--font-pixel)", fontSize: "1.8rem", margin: "8px 0" }}>SEARCH THE LATTICE</h2>
        </div>
        <SearchBar
          onSearch={(query) => router.push(`/search?query=${encodeURIComponent(query)}`)}
          initialValue=""
        />
      </article>

      <article className="panel animate-reveal stagger-3" style={{ gridColumn: "span 6", background: "var(--obsidian)", color: "#fff", display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <span style={{ fontFamily: "var(--font-pixel)", fontSize: "0.7rem", color: "rgba(255,255,255,0.4)" }}>[ LIBRARY_STATUS ]</span>
          {isSwitched && <span style={{ background: "var(--neon-green)", color: "#000", padding: "4px 8px", fontSize: "0.75rem", fontWeight: 700, borderRadius: "4px", fontFamily: "var(--font-pixel)" }}>UPDATED</span>}
        </div>
        <div style={{ marginTop: "16px" }}>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", color: "var(--sun-yellow)", wordBreak: "break-all" }}>{health?.library_path ?? "AWAITING_CONNECTION_SEQUENCE..."}</p>
          <form style={{ display: "flex", gap: "10px", marginTop: "20px" }} onSubmit={handleSetup}>
            <input
              className="input--mono"
              style={{ flexGrow: 1, border: "2px solid #fff", borderRadius: "12px", padding: "0 16px", background: "rgba(255,255,255,0.1)", color: "#fff" }}
              value={libraryInput}
              onChange={(event) => setLibraryInput(event.target.value)}
              placeholder="/Volumes/Archive/Photos"
              disabled={setupSaving}
            />
            <button
              type="submit"
              className="button button--secondary"
              style={{ borderRadius: "12px", border: "2px solid #fff", minWidth: "80px" }}
              disabled={setupSaving || !libraryInput.trim()}
            >
              {setupSaving ? "..." : "MOUNT"}
            </button>
          </form>
        </div>
      </article>

      {/* Dynamic Asset Panel - Neural Texture */}
      {/* <article className="panel animate-reveal stagger-1 video-panel" style={{ gridColumn: "span 8", minHeight: "360px" }}>
         <video autoPlay loop muted playsInline>
            <source src="/animations gifs/From KlickPin CF By Antonin Waterkeyn _ Code design graphics.mp4" type="video/mp4" />
         </video>
         <div className="video-overlay">
            <span style={{ fontFamily: "var(--font-pixel)", fontSize: "0.7rem" }}>[ NEURAL_MAPPING_SEQUENCE ]</span>
            <h2 style={{ fontFamily: "var(--font-pixel)", fontSize: "2rem", textTransform: "uppercase" }}>Spatial_Intelligence</h2>
         </div>
      </article>

      <article className="panel animate-reveal stagger-2 video-panel" style={{ gridColumn: "span 4", minHeight: "360px" }}>
         <video autoPlay loop muted playsInline>
            <source src="/animations gifs/loading_fullscreen_animation.mp4" type="video/mp4" />
         </video>
         <div className="video-overlay" style={{ alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontFamily: "var(--font-pixel)", fontSize: "0.8rem", background: "var(--sun-yellow)", color: "#000", padding: "4px 8px" }}>PROCESSIING...</span>
         </div>
      </article> */}

    </div>
  );
}
