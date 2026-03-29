"use client";

import { useCallback, useEffect, useState } from "react";
import AsciiField from "@/components/AsciiField";
import PersonCard from "@/components/PersonCard";
import { fetchIdentities } from "@/lib/api";
import type { Person } from "@/lib/types";

export default function PeoplePage() {
  const [persons, setPersons] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUnnamedOnly, setShowUnnamedOnly] = useState(false);

  const loadPersons = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchIdentities();
      setPersons(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPersons();
  }, [loadPersons]);

  const named = persons.filter((person) => person.confirmed);
  const unnamed = persons.filter((person) => !person.confirmed);
  const sortedUnnamed = [...unnamed].sort(
    (a, b) => (a.purity_score ?? 0) - (b.purity_score ?? 0)
  );
  const displayed = showUnnamedOnly ? sortedUnnamed : [...named, ...sortedUnnamed];

  return (
    <div className="bento-container" style={{ display: "grid", gap: "20px", gridTemplateColumns: "repeat(12, 1fr)", padding: "20px 0" }}>
      {/* People Hero */}
      <article className="panel animate-reveal stagger-1" style={{ gridColumn: "span 9", background: "var(--electric-purple)", color: "#fff", minHeight: "360px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div className="title-block">
          <span className="eyebrow" style={{ fontFamily: "var(--font-pixel)", color: "var(--sun-yellow)" }}>[ IDENTITY_LATTICE ]</span>
          <h1 className="page-title" style={{ fontFamily: "var(--font-pixel)", fontSize: "var(--text-3xl)", textTransform: "uppercase", margin: "8px 0" }}>
            CANVAS OF FACES
          </h1>
          <p className="page-subtitle" style={{ fontSize: "var(--text-lg)", maxWidth: "540px", opacity: 0.9 }}>
            Named people stay calm and prominent. Ambiguous clusters surface separately so corrective work feels deliberate, not buried.
          </p>
        </div>

        <div className="action-row" style={{ marginTop: "32px", display: "flex", gap: "12px" }}>
          <button
            type="button"
            className="button button--secondary"
            style={{ 
              borderRadius: "12px", 
              border: "var(--border-thick)",
              background: showUnnamedOnly ? "var(--sun-yellow)" : "#fff",
              color: "#000"
            }}
            onClick={() => setShowUnnamedOnly((value) => !value)}
          >
            <span style={{ fontFamily: "var(--font-pixel)" }}>{showUnnamedOnly ? "[ SHOWING_UNNAMED_ONLY ]" : "[ FILTER_UNNAMED ]"}</span>
          </button>
        </div>
      </article>

      {/* Quick Identity Stats */}
      <div style={{ gridColumn: "span 3", display: "grid", gap: "20px" }}>
        <article className="panel animate-reveal stagger-2" style={{ background: "var(--sun-yellow)", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center" }}>
          <span style={{ fontSize: "0.8rem", fontFamily: "var(--font-pixel)" }}>NAMED</span>
          <div style={{ fontSize: "2.5rem", fontFamily: "var(--font-pixel)" }}>{named.length}</div>
        </article>
        <article className="panel animate-reveal stagger-3" style={{ background: "var(--obsidian)", color: "#fff", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center" }}>
          <span style={{ fontSize: "0.8rem", fontFamily: "var(--font-pixel)" }}>UNNAMED</span>
          <div style={{ fontSize: "2.5rem", fontFamily: "var(--font-pixel)" }}>{unnamed.length}</div>
        </article>
      </div>

      {/* Marquee Ticker */}
      <article className="panel animate-reveal stagger-4" style={{ gridColumn: "span 12", background: "var(--obsidian)", color: "#fff", padding: "0", display: "flex", alignItems: "center", overflow: "hidden", height: "60px" }}>
        <div className="marquee" style={{ whiteSpace: "nowrap", fontSize: "1.5rem", fontFamily: "var(--font-pixel)" }}>
          <div className="marquee-content" style={{ display: "inline-block", paddingLeft: "100%", animation: "marquee 25s linear infinite" }}>
            IDENTITY RESOLUTION ENGINE ACTIVE • CLUSTERING PROCESSED • FACIAL BIOMETRICS MAPPED • MANUAL ARCHIVE CURATION REQUIRED • 
          </div>
        </div>
      </article>

      {loading ? (
        <section className="people-grid">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="person-card skeleton" style={{ minHeight: 240 }} />
          ))}
        </section>
      ) : null}

      {!loading && persons.length === 0 ? (
        <div className="void-state">
          <span className="panel__title">No People Yet</span>
          <h2 className="panel__heading">The archive has not resolved any usable face clusters.</h2>
          <p>Run a sync first, then return here to review identities after the analysis pass completes.</p>
        </div>
      ) : null}

      {!loading && displayed.length > 0 ? (
        <div style={{ gridColumn: "span 12", display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: "24px" }}>
          {displayed.map((person, index) => (
            <div key={person.id} className={`animate-reveal stagger-${(index % 4) + 1}`}>
              <PersonCard person={person} onUpdate={loadPersons} />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
