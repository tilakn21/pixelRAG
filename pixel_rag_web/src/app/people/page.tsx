// pixel_rag_web/src/app/people/page.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchIdentities } from "@/lib/api";
import type { Person } from "@/lib/types";
import PersonCard from "@/components/PersonCard";

export default function PeoplePage() {
  const [persons, setPersons] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUnnamedOnly, setShowUnnamedOnly] = useState(false);

  const loadPersons = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchIdentities();
      setPersons(data);
    } catch {
      // error silently
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPersons();
  }, [loadPersons]);

  const named = persons.filter((p) => p.confirmed);
  const unnamed = persons.filter((p) => !p.confirmed);

  // Sort unnamed by purity ascending (worst first — needs attention)
  const sortedUnnamed = [...unnamed].sort(
    (a, b) => (a.purity_score ?? 0) - (b.purity_score ?? 0)
  );

  const displayed = showUnnamedOnly ? sortedUnnamed : [...named, ...sortedUnnamed];

  return (
    <div style={{ paddingTop: "var(--space-6)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-2)" }}>
        <div>
          <h1 className="page-title">People</h1>
          <p className="page-subtitle">
            {named.length} named · {unnamed.length} unnamed
          </p>
        </div>
        <button
          className={`pill ${showUnnamedOnly ? "pill--active" : ""}`}
          onClick={() => setShowUnnamedOnly((v) => !v)}
        >
          Unnamed only
        </button>
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div>
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="skeleton"
              style={{ height: 100, marginBottom: "var(--space-3)", borderRadius: "var(--radius-lg)" }}
            />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && persons.length === 0 && (
        <div className="empty-state">
          <svg className="empty-state__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
          <div className="empty-state__title">No people found</div>
          <div className="empty-state__desc">
            Sync your photo library first. PixelRAG needs at least 3 photos of someone to identify them.
          </div>
        </div>
      )}

      {/* Person cards */}
      {!loading &&
        displayed.map((person) => (
          <PersonCard key={person.id} person={person} onUpdate={loadPersons} />
        ))}
    </div>
  );
}
