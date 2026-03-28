// pixel_rag_web/src/components/PersonCard.tsx
"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import {
  getFaceUrl,
  renamePerson,
  fetchSimilarPersons,
  mergePersons,
  fetchPersonFaces,
  splitCluster,
} from "@/lib/api";
import type { Person } from "@/lib/types";

interface PersonCardProps {
  person: Person;
  onUpdate: () => void;
}

export default function PersonCard({ person, onUpdate }: PersonCardProps) {
  const [editing, setEditing] = useState(!person.confirmed);
  const [nameInput, setNameInput] = useState(person.name ?? "");
  const [saving, setSaving] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const [showMore, setShowMore] = useState(false);

  // Merge state
  const [mergeOpen, setMergeOpen] = useState(false);
  const [similarPersons, setSimilarPersons] = useState<Person[]>([]);
  const [merging, setMerging] = useState(false);

  // Split state
  const [splitOpen, setSplitOpen] = useState(false);
  const [allFaces, setAllFaces] = useState<number[]>([]);
  const [selectedFaces, setSelectedFaces] = useState<Set<number>>(new Set());
  const [splitting, setSplitting] = useState(false);

  const handleName = useCallback(async () => {
    if (!nameInput.trim() || nameInput.trim().length < 2) return;
    setSaving(true);
    try {
      await renamePerson(person.id, nameInput.trim());
      setShowSuccess(true);
      setTimeout(() => {
        setShowSuccess(false);
        setEditing(false);
        onUpdate();
      }, 1200);
    } catch {
      // error silently
    } finally {
      setSaving(false);
    }
  }, [nameInput, person.id, onUpdate]);

  const handleMergeOpen = useCallback(async () => {
    setMergeOpen(true);
    try {
      const similar = await fetchSimilarPersons(person.id);
      setSimilarPersons(similar);
    } catch {
      setSimilarPersons([]);
    }
  }, [person.id]);

  const handleMerge = useCallback(
    async (sourceId: number) => {
      setMerging(true);
      try {
        await mergePersons(person.id, sourceId);
        setMergeOpen(false);
        onUpdate();
      } catch {
        // error silently
      } finally {
        setMerging(false);
      }
    },
    [person.id, onUpdate]
  );

  const handleSplitOpen = useCallback(async () => {
    setSplitOpen(true);
    try {
      const data = await fetchPersonFaces(person.id);
      setAllFaces(data.face_ids);
    } catch {
      setAllFaces([]);
    }
  }, [person.id]);

  const toggleFace = (faceId: number) => {
    setSelectedFaces((prev) => {
      const next = new Set(prev);
      if (next.has(faceId)) next.delete(faceId);
      else next.add(faceId);
      return next;
    });
  };

  const handleSplit = useCallback(async () => {
    if (selectedFaces.size === 0) return;
    setSplitting(true);
    try {
      await splitCluster(person.id, Array.from(selectedFaces));
      setSplitOpen(false);
      setSelectedFaces(new Set());
      onUpdate();
    } catch {
      // error silently
    } finally {
      setSplitting(false);
    }
  }, [person.id, selectedFaces, onUpdate]);

  const badgeClass =
    person.quality === "good"
      ? "badge--good"
      : person.quality === "fair"
        ? "badge--fair"
        : "badge--poor";

  const badgeLabel =
    person.quality === "good"
      ? "Good match"
      : person.quality === "fair"
        ? "Review suggested"
        : "Likely mixed";

  return (
    <div className="person-card glass">
      {/* Header row */}
      <div className="person-card__header">
        {/* Face thumbnails */}
        <div className="person-card__faces">
          {person.cover_face_url && (
            <Link href={`/people/${person.id}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                className="person-card__face"
                src={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${person.cover_face_url}`}
                alt="face"
              />
            </Link>
          )}
        </div>

        {/* Info */}
        <div className="person-card__info">
          {person.confirmed && !editing ? (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
              <Link href={`/people/${person.id}`} className="person-card__name">
                {person.name}
              </Link>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setEditing(true);
                }}
                style={{ color: "var(--text-tertiary)", padding: "var(--space-1)" }}
                title="Edit name"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
              <input
                className="input"
                placeholder="Who is this?"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleName()}
                style={{ flex: 1, padding: "var(--space-2) var(--space-3)" }}
              />
              <button
                className="btn btn--primary"
                onClick={handleName}
                disabled={saving || nameInput.trim().length < 2}
                style={{ padding: "var(--space-2) var(--space-4)", whiteSpace: "nowrap" }}
              >
                {showSuccess ? "✓" : saving ? "..." : "Confirm"}
              </button>
            </div>
          )}
          <span className="person-card__meta">
            {person.face_count} photo{person.face_count !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Badge */}
        {person.quality && (
          <span className={`person-card__badge ${badgeClass}`}>
            {badgeLabel}
          </span>
        )}
      </div>

      {/* Expandable more options */}
      <div style={{ marginTop: "var(--space-3)" }}>
        <button
          onClick={() => setShowMore((v) => !v)}
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--text-tertiary)",
            display: "flex",
            alignItems: "center",
            gap: "var(--space-1)",
          }}
        >
          {showMore ? "▾" : "▸"} More options
        </button>

        {showMore && (
          <div style={{ marginTop: "var(--space-3)", display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
            <button className="btn btn--secondary" onClick={handleMergeOpen}>
              🔗 Merge with similar
            </button>
            <button className="btn btn--secondary" onClick={handleSplitOpen}>
              ✂️ Split cluster
            </button>
          </div>
        )}
      </div>

      {/* Merge modal */}
      {mergeOpen && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <div style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", marginBottom: "var(--space-3)" }}>
            Select a cluster to merge into this person:
          </div>
          {similarPersons.length === 0 ? (
            <div style={{ fontSize: "var(--text-sm)", color: "var(--text-tertiary)" }}>
              No similar clusters found.
            </div>
          ) : (
            similarPersons.map((sp) => (
              <button
                key={sp.id}
                className="btn btn--secondary"
                style={{ marginBottom: "var(--space-2)", width: "100%", justifyContent: "flex-start" }}
                onClick={() => handleMerge(sp.id)}
                disabled={merging}
              >
                {sp.name || `Cluster ${sp.id}`} ({sp.face_count} faces)
                {sp.purity_score !== null && ` · ${sp.purity_score.toFixed(2)}`}
              </button>
            ))
          )}
          <button
            className="btn btn--secondary"
            style={{ marginTop: "var(--space-2)" }}
            onClick={() => setMergeOpen(false)}
          >
            Cancel
          </button>
        </div>
      )}

      {/* Split modal */}
      {splitOpen && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <div style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", marginBottom: "var(--space-3)" }}>
            Select faces to split into a new person:
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
            {allFaces.map((faceId) => (
              <div
                key={faceId}
                onClick={() => toggleFace(faceId)}
                style={{
                  cursor: "pointer",
                  border: selectedFaces.has(faceId)
                    ? "3px solid var(--accent-primary)"
                    : "3px solid transparent",
                  borderRadius: "var(--radius-md)",
                  overflow: "hidden",
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={getFaceUrl(faceId)}
                  alt={`Face ${faceId}`}
                  width={80}
                  height={80}
                  style={{ objectFit: "cover" }}
                />
              </div>
            ))}
          </div>
          <div style={{ marginTop: "var(--space-3)", display: "flex", gap: "var(--space-2)" }}>
            <button
              className="btn btn--primary"
              onClick={handleSplit}
              disabled={splitting || selectedFaces.size === 0}
            >
              {splitting
                ? "Splitting..."
                : `Split ${selectedFaces.size} face${selectedFaces.size !== 1 ? "s" : ""}`}
            </button>
            <button
              className="btn btn--secondary"
              onClick={() => {
                setSplitOpen(false);
                setSelectedFaces(new Set());
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
