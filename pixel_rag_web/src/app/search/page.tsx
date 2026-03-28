// pixel_rag_web/src/app/search/page.tsx
"use client";

import { useCallback, useState } from "react";
import { searchPhotos, searchByFace } from "@/lib/api";
import type { SearchResponse } from "@/lib/types";
import SearchBar from "@/components/SearchBar";
import CategoryPills from "@/components/CategoryPills";
import PhotoGrid from "@/components/PhotoGrid";

export default function SearchPage() {
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = useCallback(async (query: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await searchPhotos(query);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
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
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Face match failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleCategorySelect = (cat: string | null) => {
    if (cat) handleSearch(cat);
  };

  // Build intent summary
  const intentSummary = result?.intent
    ? [
        result.intent.names.length > 0
          ? result.intent.names.map((n) => `<span class="intent-pill">${n}</span>`).join(" ")
          : null,
        result.intent.city
          ? `in <span class="intent-pill">${result.intent.city}</span>`
          : null,
        result.intent.year
          ? `from <span class="intent-pill">${result.intent.year}</span>`
          : null,
        result.intent.scene_category
          ? `category: <span class="intent-pill">${result.intent.scene_category}</span>`
          : null,
      ]
        .filter(Boolean)
        .join(" ")
    : null;

  return (
    <div style={{ paddingTop: "var(--space-6)" }}>
      <h1 className="page-title">Search</h1>
      <p className="page-subtitle">Find photos using natural language</p>

      <SearchBar onSearch={handleSearch} onImageSearch={handleImageSearch} loading={loading} />

      {/* Category shortcuts */}
      <div style={{ marginTop: "var(--space-4)" }}>
        <CategoryPills active={null} onSelect={handleCategorySelect} />
      </div>

      {/* Error */}
      {error && (
        <div className="error-banner" style={{ marginTop: "var(--space-4)" }}>
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div style={{ marginTop: "var(--space-6)" }}>
          {/* Identity Match Banner for Image Search */}
          {result.query.startsWith("Image Search match:") && result.intent.names.length > 0 && (
            <div className="match-banner">
              <div className="match-banner__avatar">
                 <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth={1.5} style={{ margin: '16px' }}>
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                    <circle cx="12" cy="7" r="4" />
                 </svg>
              </div>
              <div style={{ flex: 1 }}>
                <div className="match-banner__subtitle">Identity Match Found</div>
                <div className="match-banner__title">{result.intent.names[0]}</div>
              </div>
              <div className="intent-pill">
                Verified
              </div>
            </div>
          )}

          {/* Intent summary */}
          {intentSummary && (
            <p
              style={{
                fontSize: "var(--text-sm)",
                color: "var(--text-secondary)",
                marginBottom: "var(--space-4)",
              }}
              dangerouslySetInnerHTML={{
                __html: `Showing ${result.total_count} result${result.total_count !== 1 ? "s" : ""} — ${intentSummary} (${result.execution_time_ms}ms)`,
              }}
            />
          )}

          {result.results.length > 0 ? (
            <PhotoGrid photos={result.results} />
          ) : (
            <div className="empty-state">
              <div className="empty-state__title">No results</div>
              <div className="empty-state__desc">
                No photos matched &quot;{result.query}&quot;. Try different keywords or remove some filters.
              </div>
            </div>
          )}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && !result && (
        <div className="photo-grid" style={{ marginTop: "var(--space-6)" }}>
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="photo-card skeleton" />
          ))}
        </div>
      )}
    </div>
  );
}
