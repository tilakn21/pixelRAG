"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import {
  deletePerson,
  fetchPersonFaces,
  fetchSimilarPersons,
  getFaceUrl,
  mergePersons,
  renamePerson,
  splitCluster,
} from "@/lib/api";
import { formatPurityScore } from "@/lib/display";
import type { Person } from "@/lib/types";

interface PersonCardProps {
  person: Person;
  onUpdate: () => void;
  selectable?: boolean;
  selected?: boolean;
  onSelect?: () => void;
  libHash?: string;
}

export default function PersonCard({ person, onUpdate, selectable, selected, onSelect, libHash }: PersonCardProps) {
  const [editing, setEditing] = useState(!person.confirmed);
  const [nameInput, setNameInput] = useState(person.name ?? "");
  const [saving, setSaving] = useState(false);
  const [showMore, setShowMore] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [similarPersons, setSimilarPersons] = useState<Person[]>([]);
  const [merging, setMerging] = useState(false);
  const [splitOpen, setSplitOpen] = useState(false);
  const [allFaces, setAllFaces] = useState<number[]>([]);
  const [selectedFaces, setSelectedFaces] = useState<Set<number>>(new Set());
  const [splitting, setSplitting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const badgeClass =
    person.quality === "good"
      ? "quality-badge quality-badge--good"
      : person.quality === "fair"
        ? "quality-badge quality-badge--fair"
        : "quality-badge quality-badge--poor";

  const badgeLabel =
    person.quality === "good"
      ? "Good cluster"
      : person.quality === "fair"
        ? "Review suggested"
        : "Mixed cluster";

  const handleName = useCallback(async () => {
    if (nameInput.trim().length < 2) return;

    setSaving(true);
    try {
      await renamePerson(person.id, nameInput.trim(), libHash);
      setEditing(false);
      onUpdate();
    } finally {
      setSaving(false);
    }
  }, [nameInput, onUpdate, person.id, libHash]);

  const handleMergeOpen = useCallback(async () => {
    setMergeOpen(true);
    try {
      const similar = await fetchSimilarPersons(person.id, libHash);
      setSimilarPersons(similar);
    } catch {
      setSimilarPersons([]);
    }
  }, [person.id, libHash]);

  const handleMerge = useCallback(
    async (sourceId: number) => {
      setMerging(true);
      try {
        await mergePersons(person.id, sourceId, libHash);
        setMergeOpen(false);
        onUpdate();
      } finally {
        setMerging(false);
      }
    },
    [onUpdate, person.id, libHash]
  );

  const handleSplitOpen = useCallback(async () => {
    setSplitOpen(true);
    try {
      const data = await fetchPersonFaces(person.id, libHash);
      setAllFaces(data.face_ids);
    } catch {
      setAllFaces([]);
    }
  }, [person.id, libHash]);

  const toggleFace = (faceId: number) => {
    setSelectedFaces((current) => {
      const next = new Set(current);
      if (next.has(faceId)) {
        next.delete(faceId);
      } else {
        next.add(faceId);
      }
      return next;
    });
  };

  const handleSplit = useCallback(async () => {
    if (selectedFaces.size === 0) return;

    setSplitting(true);
    try {
      await splitCluster(person.id, Array.from(selectedFaces), libHash);
      setSplitOpen(false);
      setSelectedFaces(new Set());
      onUpdate();
    } finally {
      setSplitting(false);
    }
  }, [onUpdate, person.id, selectedFaces, libHash]);

  const handleDelete = useCallback(async () => {
    if (!window.confirm(`Dissolve "${person.name || "this cluster"}"? Photos will remain, but the identity link will be removed.`)) {
      return;
    }

    setIsDeleting(true);
    try {
      await deletePerson(person.id, libHash);
      onUpdate();
    } catch {
       setIsDeleting(false);
    }
  }, [onUpdate, person.id, person.name, libHash]);

  return (
    <article className="panel" style={{ display: "flex", flexDirection: "column", gap: "20px", position: "relative", border: selected ? "2px solid var(--electric-purple)" : undefined }}>
      {selectable && (
        <button
          type="button"
          onClick={onSelect}
          style={{
            position: "absolute",
            top: "10px",
            right: "10px",
            width: "24px",
            height: "24px",
            borderRadius: "4px",
            border: "2px solid var(--obsidian)",
            background: selected ? "var(--electric-purple)" : "#fff",
            cursor: "pointer",
            zIndex: 10,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {selected && <span style={{ color: "#fff", fontFamily: "var(--font-pixel)", fontSize: "12px" }}>✓</span>}
        </button>
      )}

      <div className="person-card__header" style={{ display: "flex", gap: "20px", alignItems: "flex-start", opacity: selectable && !selected ? 0.7 : 1 }}>
        <Link href={`/people/${person.id}`} className="person-card__portrait" style={{ width: "100px", height: "100px", flexShrink: 0, border: "var(--border-thick)", borderRadius: "12px", overflow: "hidden" }}>
          {person.cover_face_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${person.cover_face_url}`}
              alt={person.name ?? "Unnamed person"}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          ) : (
            <div
              style={{ width: "100%", height: "100%", background: "var(--obsidian)", color: "var(--sun-yellow)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--font-pixel)", fontSize: "0.8rem", textAlign: "center" }}
            >
              NO_IMG
            </div>
          )}
        </Link>

        <div className="person-card__identity" style={{ flexGrow: 1 }}>
          {editing ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <input
                className="input--mono"
                style={{ border: "var(--border-thick)", borderRadius: "8px", padding: "8px 12px", width: "100%" }}
                value={nameInput}
                placeholder="WHO_IS_THIS?"
                onChange={(event) => setNameInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void handleName();
                  }
                }}
              />
              <button
                type="button"
                className="button button--primary"
                style={{ borderRadius: "8px", height: "40px", fontSize: "0.9rem" }}
                disabled={saving || nameInput.trim().length < 2}
                onClick={() => void handleName()}
              >
                {saving ? "SAVING..." : "CONFIRM_IDENTITY"}
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <Link href={`/people/${person.id}`} style={{ fontFamily: "var(--font-pixel)", fontSize: "1.4rem", textTransform: "uppercase", color: "var(--obsidian)", textDecoration: "none" }}>
                  {person.name || "UNNAMED_NODE"}
                </Link>
                <div style={{ display: "flex", gap: "8px" }}>
                  <button
                    type="button"
                    className="button button--secondary"
                    style={{ padding: "4px 8px", minHeight: "auto", fontSize: "0.7rem", borderRadius: "6px" }}
                    onClick={() => setEditing(true)}
                  >
                    RENAME
                  </button>
                  <button
                    type="button"
                    className="button button--secondary"
                    style={{ padding: "4px 8px", minHeight: "auto", fontSize: "0.7rem", borderRadius: "6px", background: "#fee2e2", color: "#991b1b" }}
                    disabled={isDeleting}
                    onClick={() => void handleDelete()}
                  >
                    {isDeleting ? "..." : "DISSOLVE"}
                  </button>
                </div>
              </div>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.6, marginTop: "4px" }}>
                {person.face_count} FRAMES • {formatPurityScore(person.purity_score)}
              </span>
              {person.quality ? (
                <span style={{ 
                  display: "inline-block",
                  marginTop: "8px",
                  fontFamily: "var(--font-pixel)", 
                  fontSize: "0.65rem", 
                  padding: "2px 6px", 
                  borderRadius: "4px", 
                  background: person.quality === "good" ? "var(--neon-green)" : "var(--sun-yellow)",
                  color: "#000",
                  textTransform: "uppercase",
                  width: "fit-content"
                }}>
                  {badgeLabel}
                </span>
              ) : null}
            </div>
          )}
        </div>
      </div>

      <div className="action-row" style={{ display: "flex", gap: "12px", marginTop: "12px" }}>
        <Link href={`/people/${person.id}`} className="button button--primary" style={{ flexGrow: 1, borderRadius: "12px" }}>
           OPEN_CLUSTER
        </Link>
        <button
          type="button"
          className="button button--secondary"
          style={{ borderRadius: "12px", minWidth: "120px" }}
          onClick={() => setShowMore((value) => !value)}
        >
          {showMore ? "HIDE_TOOLS" : "REFINE"}
        </button>
        <button
          type="button"
          className="button button--secondary"
          style={{ borderRadius: "12px", minWidth: "80px", background: selected ? "var(--electric-purple)" : undefined, color: selected ? "#fff" : undefined }}
          onClick={onSelect}
        >
          {selected ? "SELECTED" : "SELECT"}
        </button>
      </div>

      {showMore ? (
        <div className="stack" style={{ marginTop: "12px", borderTop: "var(--border-thin)", paddingTop: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
          <div className="action-row" style={{ display: "flex", gap: "10px" }}>
            <button type="button" className="button button--secondary" style={{ flexGrow: 1, borderRadius: "8px", fontSize: "0.8rem", minHeight: "40px" }} onClick={() => void handleMergeOpen()}>
              MERGE_SIMILAR
            </button>
            <button type="button" className="button button--secondary" style={{ flexGrow: 1, borderRadius: "8px", fontSize: "0.8rem", minHeight: "40px" }} onClick={() => void handleSplitOpen()}>
              SPLIT_CLUSTER
            </button>
          </div>
          {mergeOpen ? (
            <div className="panel" style={{ background: "#f8f8f8", padding: "16px" }}>
              <span className="panel__title" style={{ fontFamily: "var(--font-pixel)", fontSize: "0.6rem" }}>[ MERGE_SUGGESTIONS ]</span>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "12px" }}>
                {similarPersons.length === 0 ? (
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.6 }}>No adjacent clusters surfaced.</p>
                ) : (
                  similarPersons.map((candidate) => (
                    <button
                      key={candidate.id}
                      type="button"
                      className="button button--secondary"
                      style={{ justifyContent: "space-between", borderRadius: "8px", width: "100%" }}
                      disabled={merging}
                      onClick={() => void handleMerge(candidate.id)}
                    >
                      <span style={{ fontFamily: "var(--font-pixel)" }}>{candidate.name || `CLUSTER_${candidate.id}`}</span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.7rem" }}>{candidate.face_count}F</span>
                    </button>
                  ))
                )}
              </div>
            </div>
          ) : null}

          {splitOpen ? (
            <div className="panel" style={{ background: "#f8f8f8", padding: "16px" }}>
              <span className="panel__title" style={{ fontFamily: "var(--font-pixel)", fontSize: "0.6rem" }}>[ SPLIT_SELECTION ]</span>
              <div className="cluster-strip" style={{ display: "flex", gap: "8px", overflowX: "auto", padding: "12px 0", scrollbarWidth: "thin" }}>
                {allFaces.map((faceId) => (
                  <button
                    key={faceId}
                    type="button"
                    className="face-thumb"
                    style={{ 
                      flexShrink: 0, 
                      width: "60px", 
                      height: "60px", 
                      border: selectedFaces.has(faceId) ? "3px solid var(--electric-blue)" : "1px solid #ccc",
                      borderRadius: "8px",
                      overflow: "hidden",
                      transition: "all 0.1s"
                    }}
                    onClick={() => toggleFace(faceId)}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={getFaceUrl(faceId, libHash)}
                      alt={`Face ${faceId}`}
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                    />
                  </button>
                ))}
              </div>

              <div className="action-row" style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
                <button
                  type="button"
                  className="button button--primary"
                  style={{ borderRadius: "8px", fontSize: "0.8rem", flexGrow: 1 }}
                  disabled={splitting || selectedFaces.size === 0}
                  onClick={() => void handleSplit()}
                >
                  {splitting ? "SPLITTING..." : `SPLIT_${selectedFaces.size}_FACES`}
                </button>
                <button
                  type="button"
                  className="button button--secondary"
                  style={{ borderRadius: "8px", fontSize: "0.8rem", background: "transparent" }}
                  onClick={() => {
                    setSplitOpen(false);
                    setSelectedFaces(new Set());
                  }}
                >
                  CANCEL
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
