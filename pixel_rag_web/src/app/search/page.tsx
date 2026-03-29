"use client";

import { Suspense, startTransition, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import AsciiField from "@/components/AsciiField";
import CategoryPills from "@/components/CategoryPills";
import PhotoGrid from "@/components/PhotoGrid";
import SearchBar from "@/components/SearchBar";
import FullscreenLoader from "@/components/FullscreenLoader";
import { searchByFace, searchPhotos } from "@/lib/api";
import { formatSceneCategory } from "@/lib/display";
import type { SearchResponse } from "@/lib/types";

const SEARCH_PHASES = [
  "> Analyzing intent",
  "> Isolating pixels",
  "> Mapping visual clusters",
  "> Ranking matching frames",
];

function SearchContent() {
  const searchParams = useSearchParams();
  const queryFromUrl = searchParams.get("query") ?? "";
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phaseIndex, setPhaseIndex] = useState(0);

  const handleSearch = useCallback(async (query: string) => {
    setLoading(true);
    setError(null);

    try {
      const data = await searchPhotos(query);
      startTransition(() => {
        setResult(data);
      });
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Search failed.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleImageSearch = useCallback(async (file: File) => {
    setLoading(true);
    setError(null);

    try {
      const data = await searchByFace(file);
      startTransition(() => {
        setResult(data);
      });
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Face search failed.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!queryFromUrl) return;
    void handleSearch(queryFromUrl);
  }, [handleSearch, queryFromUrl]);

  useEffect(() => {
    if (!loading) {
      setPhaseIndex(0);
      return;
    }

    const interval = window.setInterval(() => {
      setPhaseIndex((current) => (current + 1) % SEARCH_PHASES.length);
    }, 900);

    return () => window.clearInterval(interval);
  }, [loading]);

  const handleCategorySelect = (category: string | null) => {
    if (!category) {
      setResult(null);
      return;
    }

    void handleSearch(category);
  };

  const intentPills = result
    ? [
        ...result.intent.names.map((name) => `Identity · ${name}`),
        result.intent.city ? `City · ${result.intent.city}` : null,
        result.intent.year ? `Year · ${result.intent.year}` : null,
        result.intent.scene_category ? `Scene · ${formatSceneCategory(result.intent.scene_category)}` : null,
      ].filter(Boolean)
    : [];

  return (
    <div className="bento-container" style={{ display: "grid", gap: "20px", gridTemplateColumns: "repeat(12, 1fr)", padding: "20px 0" }}>
      {/* Search Hero */}
      <article className="panel animate-reveal stagger-1" style={{ gridColumn: "span 12", background: "var(--electric-purple)", color: "#fff", minHeight: "360px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div className="title-block">
          <span className="eyebrow" style={{ fontFamily: "var(--font-pixel)", color: "var(--sun-yellow)" }}>[ AI_SYMPHONY ]</span>
          <h1 className="page-title" style={{ fontFamily: "var(--font-pixel)", fontSize: "var(--text-3xl)", textTransform: "uppercase", margin: "8px 0" }}>
            SEARCH_WITH_INTENT
          </h1>
          <p className="page-subtitle" style={{ fontSize: "var(--text-lg)", maxWidth: "600px", opacity: 0.9 }}>
            Ask for people, cities, moods, dates, or scenes. PixelRAG resolves them into a precise photographic shortlist.
          </p>
        </div>

        <div style={{ marginTop: "32px", maxWidth: "800px" }}>
          <SearchBar
            onSearch={(query) => void handleSearch(query)}
            onImageSearch={(file) => void handleImageSearch(file)}
            loading={loading}
            initialValue={queryFromUrl}
          />
        </div>
      </article>

      {/* Categories Toolbar */}
      <section className="panel animate-reveal stagger-2" style={{ gridColumn: "span 12", padding: "16px" }}>
        <CategoryPills active={null} onSelect={handleCategorySelect} />
      </section>

      {error ? (
        <div className="status-banner status-banner--error">
          <strong>Search could not complete.</strong>
          <span>{error}</span>
        </div>
      ) : null}

      <FullscreenLoader isLoading={loading} phase={SEARCH_PHASES[phaseIndex]} />


      {result ? (
        <article className="panel" style={{ gridColumn: "span 12", background: "var(--sun-yellow)", color: "#000" }}>
          <div className="panel__header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <span className="panel__title" style={{ fontFamily: "var(--font-pixel)" }}>[ RESULT_SUMMARY ]</span>
              <h2 className="panel__heading" style={{ fontFamily: "var(--font-pixel)", fontSize: "1.8rem", margin: "8px 0" }}>
                {result.total_count} MATCHES FOR "{result.query.toUpperCase()}"
              </h2>
            </div>
            <span style={{ fontFamily: "var(--font-pixel)", fontSize: "1.2rem" }}>{result.execution_time_ms} MS</span>
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginTop: "16px" }}>
            {result.query.startsWith("Image Search match:") && result.intent.names.length > 0 ? (
              <>
                <span style={{ background: "var(--electric-blue)", color: "#fff", padding: "4px 10px", borderRadius: "6px", fontFamily: "var(--font-mono)", fontSize: "0.75rem" }}>IDENTITY_MATCH: {result.intent.names[0].toUpperCase()}</span>
                <span style={{ background: "var(--obsidian)", color: "#fff", padding: "4px 10px", borderRadius: "6px", fontFamily: "var(--font-mono)", fontSize: "0.75rem" }}>VISUAL_VERIFICATION_COMPLETE</span>
              </>
            ) : null}

            {intentPills.map((pill) => (
              <span key={pill} style={{ background: "rgba(0,0,0,0.1)", color: "#000", padding: "4px 10px", borderRadius: "6px", fontFamily: "var(--font-mono)", fontSize: "0.75rem", border: "1px solid rgba(0,0,0,0.1)" }}>
                {pill?.toUpperCase()}
              </span>
            ))}
          </div>
        </article>
      ) : null}

      <div style={{ gridColumn: "span 12" }}>
        {result ? (
          result.results.length > 0 ? (
            <PhotoGrid photos={result.results} />
          ) : (
            <div className="panel" style={{ background: "#f8f8f8", textAlign: "center", padding: "60px 20px" }}>
              <span className="panel__title" style={{ fontFamily: "var(--font-pixel)" }}>[ VOID_RESPONSE ]</span>
              <h2 className="panel__heading" style={{ fontFamily: "var(--font-pixel)", fontSize: "2rem", margin: "12px 0" }}>ZERO_RESULTS_RETURNED</h2>
              <p style={{ maxWidth: "500px", margin: "0 auto", opacity: 0.6 }}>Broaden the terms, remove a date or city constraint, or try searching by a different person.</p>
            </div>
          )
        ) : !loading ? (
          <div className="panel" style={{ background: "#f8f8f8", textAlign: "center", padding: "60px 20px" }}>
            <span className="panel__title" style={{ fontFamily: "var(--font-pixel)" }}>[ SEARCH_CANVAS ]</span>
            <h2 className="panel__heading" style={{ fontFamily: "var(--font-pixel)", fontSize: "2rem", margin: "12px 0" }}>READY_FOR_INPUT</h2>
            <p style={{ maxWidth: "500px", margin: "0 auto", opacity: 0.6 }}>Describe a memory and let the archive answer. Start with a person, place, season, scene category, or mood.</p>
          </div>
        ) : null}
      </div>

      {/* Marquee Ticker */}
      <article className="panel" style={{ gridColumn: "span 12", background: "var(--obsidian)", color: "#fff", padding: "0", display: "flex", alignItems: "center", overflow: "hidden", height: "60px" }}>
        <div className="marquee" style={{ whiteSpace: "nowrap", fontSize: "1.5rem", fontFamily: "var(--font-pixel)" }}>
          <div className="marquee-content" style={{ display: "inline-block", paddingLeft: "100%", animation: "marquee 40s linear infinite" }}>
            SEARCH ENGINE ONLINE • RANKING RESOLVED • SEMANTIC MAPPING COMPLETE • PIXELRAG V1.0 • 
          </div>
        </div>
      </article>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="spinner" style={{ margin: "40px auto" }} />}>
      <SearchContent />
    </Suspense>
  );
}
