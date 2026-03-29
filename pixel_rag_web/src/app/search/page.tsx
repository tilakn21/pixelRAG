"use client";

import { Suspense, startTransition, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import AsciiField from "@/components/AsciiField";
import CategoryPills from "@/components/CategoryPills";
import PhotoGrid from "@/components/PhotoGrid";
import SearchBar from "@/components/SearchBar";
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
    <div className="route">
      <section className="route-hero route-hero--split">
        <div className="stack">
          <div className="title-block">
            <span className="eyebrow">AI Symphony</span>
            <h1 className="page-title">Search with intent, not folders.</h1>
            <p className="page-subtitle">
              Ask for people, cities, moods, dates, or scenes. PixelRAG resolves them into a precise photographic shortlist.
            </p>
          </div>

          <SearchBar
            onSearch={(query) => void handleSearch(query)}
            onImageSearch={(file) => void handleImageSearch(file)}
            loading={loading}
            initialValue={queryFromUrl}
          />

          <CategoryPills active={null} onSelect={handleCategorySelect} />
        </div>

        <AsciiField
          className="hero-ascii"
          variant="wave"
          tone="cobalt"
          caption="Retrieval field / ranked images"
          scale="hero"
        />
      </section>

      {error ? (
        <div className="status-banner status-banner--error">
          <strong>Search could not complete.</strong>
          <span>{error}</span>
        </div>
      ) : null}

      {loading ? (
        <section className="status-console">
          <div className="status-console__header">
            <div>
              <span className="status-console__label">Processing</span>
              <h2 className="panel__heading">{SEARCH_PHASES[phaseIndex]}</h2>
            </div>
            <AsciiField variant="wave" tone="silver" caption="Computational ripple" scale="inline" />
          </div>

          <div className="status-console__meta">
            <span>Search remains visually stable while the ranking layer resolves.</span>
          </div>
        </section>
      ) : null}

      {result ? (
        <section className="stack">
          <div className="panel panel--quiet">
            <div className="panel__header">
              <div>
                <span className="panel__title">Result Summary</span>
                <h2 className="panel__heading">
                  {result.total_count} result{result.total_count === 1 ? "" : "s"} for “{result.query}”
                </h2>
              </div>
              <span className="meta-pill">{result.execution_time_ms} ms</span>
            </div>

            {result.query.startsWith("Image Search match:") && result.intent.names.length > 0 ? (
              <div className="route-meta">
                <span className="meta-pill">Identity match · {result.intent.names[0]}</span>
                <span className="meta-pill">Visual verification</span>
              </div>
            ) : null}

            {intentPills.length > 0 ? (
              <div className="route-meta">
                {intentPills.map((pill) => (
                  <span key={pill} className="meta-pill">
                    {pill}
                  </span>
                ))}
              </div>
            ) : null}
          </div>

          {result.results.length > 0 ? (
            <PhotoGrid photos={result.results} />
          ) : (
            <div className="void-state">
              <span className="panel__title">No Results</span>
              <h2 className="panel__heading">Nothing matched this request.</h2>
              <p>Broaden the terms, remove a date or city constraint, or try searching by a different person.</p>
            </div>
          )}
        </section>
      ) : !loading ? (
        <div className="void-state">
          <span className="panel__title">Search Canvas</span>
          <h2 className="panel__heading">Describe a memory and let the archive answer.</h2>
          <p>Start with a person, place, season, scene category, or mood.</p>
        </div>
      ) : null}
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
