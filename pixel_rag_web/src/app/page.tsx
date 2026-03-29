"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AsciiField from "@/components/AsciiField";
import SearchBar from "@/components/SearchBar";
import { fetchHealth, setLibraryPath } from "@/lib/api";
import { formatCompactNumber, formatLibraryLabel } from "@/lib/display";
import type { HealthResponse } from "@/lib/types";

const NAVIGATORS = [
  {
    href: "/search",
    mark: "Search",
    title: "AI Symphony",
    description: "Search the archive in natural language and let intent resolve into imagery.",
  },
  {
    href: "/photos",
    mark: "Archive",
    title: "Endless Archive",
    description: "Move through the full image index with quiet chrome and deeper metadata on demand.",
  },
  {
    href: "/people",
    mark: "Faces",
    title: "Canvas of Faces",
    description: "Review identities, resolve mixed clusters, and refine the people index with care.",
  },
  {
    href: "/gallery",
    mark: "Curate",
    title: "Curated Exhibition",
    description: "Browse the collection by composed chapters instead of flat utility categories.",
  },
];

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
    <div className="route">
      <section className="route-hero">
        {isSwitched ? (
          <div className="status-banner">
            <strong>Library updated.</strong>
            <span className="mono">The archive context has been refreshed for this workspace.</span>
          </div>
        ) : null}

        {error ? (
          <div className="status-banner status-banner--error">
            <strong>Connection issue</strong>
            <span>{error}</span>
          </div>
        ) : null}

        <div className="hero-grid">
          <div className="stack">
            <div className="title-block">
              <span className="eyebrow">Silent Index</span>
              <h1 className="page-title">A quieter way to search memory.</h1>
              <p className="page-subtitle">
                PixelRAG now reads like a gallery-lab: light, exact, and led by the image instead of the interface.
              </p>
            </div>

            <SearchBar
              onSearch={(query) => router.push(`/search?query=${encodeURIComponent(query)}`)}
              initialValue=""
            />

            <div className="route-meta">
              <span className="meta-pill">Local-first intelligence</span>
              <span className="meta-pill">Photography remains the hero</span>
              <span className="meta-pill">Structured around search and curation</span>
            </div>
          </div>

          <AsciiField
            className="hero-ascii"
            variant="iris"
            tone="cobalt"
            caption="Optical field / live archive"
            scale="hero"
          />
        </div>
      </section>

      <section className="metric-grid">
        <article className="metric-card">
          <span className="metric-card__label">Photos</span>
          <div className="metric-card__value">{formatCompactNumber(health?.photo_count)}</div>
          <div className="metric-card__foot">Indexed frames inside the active library</div>
        </article>

        <article className="metric-card">
          <span className="metric-card__label">Identified People</span>
          <div className="metric-card__value">{formatCompactNumber(health?.person_count)}</div>
          <div className="metric-card__foot">Clusters ready for review and naming</div>
        </article>
      </section>

      <section className="surface-grid">
        <article className="panel panel--accent">
          <div className="panel__header">
            <div>
              <span className="panel__title">Connected Library</span>
              <h2 className="panel__heading">{formatLibraryLabel(health?.library_path)}</h2>
            </div>
            <span className="meta-pill">Active archive</span>
          </div>

          <div className="stack">
            <p className="mono">{health?.library_path ?? "No library connected yet."}</p>

            <form className="form-stack" onSubmit={handleSetup}>
              <input
                className="input input--mono"
                value={libraryInput}
                onChange={(event) => setLibraryInput(event.target.value)}
                placeholder="/Users/yourname/Photos"
                disabled={setupSaving}
              />
              <div className="action-row">
                <button
                  type="submit"
                  className="button button--primary"
                  disabled={setupSaving || !libraryInput.trim()}
                >
                  {setupSaving ? "Switching" : "Switch library"}
                </button>
                <button
                  type="button"
                  className="button button--secondary"
                  onClick={() => router.push("/photos")}
                >
                  Open archive
                </button>
              </div>
            </form>
          </div>
        </article>

        <article className="panel panel--quiet">
          <span className="panel__title">System View</span>
          <h2 className="panel__heading">Everything orbits around search.</h2>
          <p>
            The redesigned product keeps the photography central, reduces chrome, and lets metadata appear only when it clarifies meaning.
          </p>
          <div className="route-meta">
            <span className="meta-pill">Search is the emotional anchor</span>
            <span className="meta-pill">Metadata lives in calm monospace</span>
            <span className="meta-pill">ASCII acts as signal, not decoration</span>
          </div>
        </article>
      </section>

      <section className="cta-grid">
        {NAVIGATORS.map((item) => (
          <button
            key={item.href}
            type="button"
            className="cta-card"
            onClick={() => router.push(item.href)}
          >
            <span className="cta-card__mark">{item.mark}</span>
            <h3>{item.title}</h3>
            <p>{item.description}</p>
          </button>
        ))}
      </section>
    </div>
  );
}
