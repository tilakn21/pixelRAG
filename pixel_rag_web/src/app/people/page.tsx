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
    <div className="route">
      <section className="route-hero route-hero--split">
        <div className="stack">
          <div className="title-block">
            <span className="eyebrow">Canvas of Faces</span>
            <h1 className="page-title">Review identity with space and clarity.</h1>
            <p className="page-subtitle">
              Named people stay calm and prominent. Ambiguous clusters surface separately so corrective work feels deliberate, not buried.
            </p>
          </div>

          <div className="route-meta">
            <span className="meta-pill">{named.length} named</span>
            <span className="meta-pill">{unnamed.length} unnamed</span>
          </div>

          <div className="action-row">
            <button
              type="button"
              className={`chip ${showUnnamedOnly ? "chip--active" : ""}`}
              onClick={() => setShowUnnamedOnly((value) => !value)}
            >
              <span className="chip__mark">Filter</span>
              <span>{showUnnamedOnly ? "Showing unnamed only" : "Show unnamed only"}</span>
            </button>
          </div>
        </div>

        <AsciiField className="hero-ascii" variant="swirl" tone="cobalt" caption="Identity lattice / face clusters" scale="hero" />
      </section>

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
        <section className="people-grid">
          {displayed.map((person) => (
            <PersonCard key={person.id} person={person} onUpdate={loadPersons} />
          ))}
        </section>
      ) : null}
    </div>
  );
}
