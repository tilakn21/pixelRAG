"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import {
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
}

export default function PersonCard({ person, onUpdate }: PersonCardProps) {
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
      await renamePerson(person.id, nameInput.trim());
      setEditing(false);
      onUpdate();
    } finally {
      setSaving(false);
    }
  }, [nameInput, onUpdate, person.id]);

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
      } finally {
        setMerging(false);
      }
    },
    [onUpdate, person.id]
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
      await splitCluster(person.id, Array.from(selectedFaces));
      setSplitOpen(false);
      setSelectedFaces(new Set());
      onUpdate();
    } finally {
      setSplitting(false);
    }
  }, [onUpdate, person.id, selectedFaces]);

  return (
    <article className="person-card">
      <div className="person-card__header">
        <div className="person-card__lead">
          <Link href={`/people/${person.id}`} className="person-card__portrait">
            {person.cover_face_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${person.cover_face_url}`}
                alt={person.name ?? "Unnamed person"}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            ) : (
              <div
                className="ascii-field ascii-field--silver"
                style={{ width: "100%", height: "100%", padding: 14, placeContent: "center" }}
              >
                <pre aria-hidden="true">{". : :\n: + +\n+ # #\n: + +\n. : :"}</pre>
              </div>
            )}
          </Link>

          <div className="person-card__identity">
            {editing ? (
              <div className="form-inline">
                <input
                  className="input"
                  value={nameInput}
                  placeholder="Who is this?"
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
                  disabled={saving || nameInput.trim().length < 2}
                  onClick={() => void handleName()}
                >
                  {saving ? "Saving" : "Confirm"}
                </button>
              </div>
            ) : (
              <>
                <div className="form-inline" style={{ justifyContent: "space-between" }}>
                  <Link href={`/people/${person.id}`} className="person-card__name">
                    {person.name}
                  </Link>
                  <button
                    type="button"
                    className="button button--ghost"
                    onClick={() => setEditing(true)}
                  >
                    Rename
                  </button>
                </div>
                <span className="person-card__meta">
                  {person.face_count} photo{person.face_count !== 1 ? "s" : ""} · {formatPurityScore(person.purity_score)}
                </span>
              </>
            )}
          </div>
        </div>

        {person.quality ? <span className={badgeClass}>{badgeLabel}</span> : null}
      </div>

      <div className="action-row">
        <Link href={`/people/${person.id}`} className="button button--secondary">
          Open cluster
        </Link>
        <button
          type="button"
          className="button button--ghost"
          onClick={() => setShowMore((value) => !value)}
        >
          {showMore ? "Hide tools" : "Refine cluster"}
        </button>
      </div>

      {showMore ? (
        <div className="stack">
          <div className="action-row">
            <button type="button" className="button button--secondary" onClick={() => void handleMergeOpen()}>
              Merge with similar
            </button>
            <button type="button" className="button button--secondary" onClick={() => void handleSplitOpen()}>
              Split cluster
            </button>
          </div>

          {mergeOpen ? (
            <div className="panel panel--quiet">
              <span className="panel__title">Merge Suggestions</span>
              <div className="stack">
                {similarPersons.length === 0 ? (
                  <p>No adjacent clusters surfaced for this identity.</p>
                ) : (
                  similarPersons.map((candidate) => (
                    <button
                      key={candidate.id}
                      type="button"
                      className="button button--secondary"
                      style={{ justifyContent: "space-between" }}
                      disabled={merging}
                      onClick={() => void handleMerge(candidate.id)}
                    >
                      <span>{candidate.name || `Cluster ${candidate.id}`}</span>
                      <span className="mono">{candidate.face_count} frames</span>
                    </button>
                  ))
                )}
              </div>
            </div>
          ) : null}

          {splitOpen ? (
            <div className="panel panel--quiet">
              <span className="panel__title">Split Selection</span>
              <div className="cluster-strip">
                {allFaces.map((faceId) => (
                  <button
                    key={faceId}
                    type="button"
                    className={`face-thumb ${selectedFaces.has(faceId) ? "face-thumb--active" : ""}`}
                    onClick={() => toggleFace(faceId)}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={getFaceUrl(faceId)}
                      alt={`Face ${faceId}`}
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                    />
                  </button>
                ))}
              </div>

              <div className="action-row">
                <button
                  type="button"
                  className="button button--primary"
                  disabled={splitting || selectedFaces.size === 0}
                  onClick={() => void handleSplit()}
                >
                  {splitting ? "Splitting" : `Split ${selectedFaces.size} face${selectedFaces.size === 1 ? "" : "s"}`}
                </button>
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={() => {
                    setSplitOpen(false);
                    setSelectedFaces(new Set());
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
