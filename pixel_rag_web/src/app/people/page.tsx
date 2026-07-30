"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AsciiField from "@/components/AsciiField";
import PersonCard from "@/components/PersonCard";
import { fetchIdentities, batchDissolve, batchMergePersons, tagByPhoto, fetchHealth } from "@/lib/api";
import type { Person, TagByPhotoResponse } from "@/lib/types";

export default function PeoplePage() {
  const [persons, setPersons] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUnnamedOnly, setShowUnnamedOnly] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [batchActionRunning, setBatchActionRunning] = useState(false);
  const [libHash, setLibHash] = useState("");
  
  // Tag by Photo modal state
  const [showTagModal, setShowTagModal] = useState(false);
  const [tagFile, setTagFile] = useState<File | null>(null);
  const [tagName, setTagName] = useState("");
  const [tagLoading, setTagLoading] = useState(false);
  const [tagResult, setTagResult] = useState<TagByPhotoResponse | null>(null);
  const [tagError, setTagError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadPersons = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchIdentities(undefined, libHash);
      setPersons(data);
    } finally {
      setLoading(false);
    }
  }, [libHash]);

  useEffect(() => {
    fetchHealth()
      .then((health) => setLibHash(`${health.lib_hash}_${health.sync_version}`))
      .catch(() => {});
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

  const toggleSelection = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBatchDissolve = async () => {
    if (!window.confirm(`Dissolve ${selectedIds.size} clusters?`)) return;
    setBatchActionRunning(true);
    try {
      await batchDissolve(Array.from(selectedIds), libHash);
      setSelectedIds(new Set());
      await loadPersons();
    } finally {
      setBatchActionRunning(false);
    }
  };

  const handleBatchMerge = async () => {
    if (!window.confirm(`Merge ${selectedIds.size} clusters into one? The cluster with the most faces will absorb the rest.`)) return;
    setBatchActionRunning(true);
    try {
      const selectedPersons = persons.filter((p) => selectedIds.has(p.id));
      // Target is the one with the most faces
      const target = selectedPersons.reduce((prev, current) => 
        (current.face_count > prev.face_count) ? current : prev
      );
      const sourceIds = Array.from(selectedIds).filter((id) => id !== target.id);
      
      if (sourceIds.length > 0) {
        await batchMergePersons(target.id, sourceIds, libHash);
      }
      setSelectedIds(new Set());
      await loadPersons();
    } finally {
      setBatchActionRunning(false);
    }
  };

  const handleTagByPhoto = async () => {
    if (!tagFile || !tagName.trim()) return;
    setTagLoading(true);
    setTagError(null);
    setTagResult(null);
    try {
      const result = await tagByPhoto(tagFile, tagName.trim(), libHash);
      setTagResult(result);
      await loadPersons();
    } catch (e: unknown) {
      setTagError(e instanceof Error ? e.message : "Tag by photo failed");
    } finally {
      setTagLoading(false);
    }
  };

  const closeTagModal = () => {
    setShowTagModal(false);
    setTagFile(null);
    setTagName("");
    setTagResult(null);
    setTagError(null);
  };

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
          <button
            type="button"
            className="button button--secondary"
            style={{ 
              borderRadius: "12px", 
              border: "var(--border-thick)",
              background: "#fff",
              color: "#000"
            }}
            onClick={() => setShowTagModal(true)}
          >
            <span style={{ fontFamily: "var(--font-pixel)" }}>[ TAG_BY_PHOTO ]</span>
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
              <PersonCard 
                person={person} 
                onUpdate={loadPersons} 
                selectable={selectedIds.size > 0}
                selected={selectedIds.has(person.id)}
                onSelect={() => toggleSelection(person.id)}
                libHash={libHash}
              />
            </div>
          ))}
        </div>
      ) : null}

      {/* Action Bar for Batch Selection */}
      {selectedIds.size > 0 && (
        <div style={{
          position: "fixed",
          bottom: "24px",
          left: "50%",
          transform: "translateX(-50%)",
          background: "var(--obsidian)",
          color: "#fff",
          padding: "16px 24px",
          borderRadius: "16px",
          display: "flex",
          alignItems: "center",
          gap: "24px",
          boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
          zIndex: 100,
          fontFamily: "var(--font-pixel)",
          border: "var(--border-thick)"
        }}>
          <span style={{ fontSize: "1.2rem", color: "var(--sun-yellow)" }}>
            [{selectedIds.size} SELECTED]
          </span>
          <div style={{ display: "flex", gap: "12px" }}>
            <button
              className="button button--secondary"
              onClick={handleBatchMerge}
              disabled={batchActionRunning || selectedIds.size < 2}
              style={{ background: "#fff", color: "#000" }}
            >
              MERGE_ALL
            </button>
            <button
              className="button button--secondary"
              onClick={handleBatchDissolve}
              disabled={batchActionRunning}
              style={{ background: "#fee2e2", color: "#991b1b" }}
            >
              DISSOLVE_ALL
            </button>
            <button
              className="button button--primary"
              onClick={() => setSelectedIds(new Set())}
              disabled={batchActionRunning}
              style={{ background: "transparent", color: "#fff", textDecoration: "underline" }}
            >
              CANCEL
            </button>
          </div>
        </div>
      )}

      {/* Tag by Photo Modal */}
      {showTagModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.7)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 200,
          }}
          onClick={(e) => { if (e.target === e.currentTarget) closeTagModal(); }}
        >
          <div
            style={{
              background: "#fff",
              borderRadius: "20px",
              padding: "32px",
              maxWidth: "480px",
              width: "90%",
              border: "var(--border-thick)",
              boxShadow: "8px 8px 0 var(--obsidian)",
            }}
          >
            <h2 style={{ fontFamily: "var(--font-pixel)", fontSize: "1.3rem", marginBottom: "8px" }}>TAG_BY_PHOTO</h2>
            <p style={{ fontSize: "0.9rem", color: "#666", marginBottom: "20px" }}>
              Upload a photo of someone and type their name. All matching clusters will be merged and named automatically.
            </p>

            {/* Drop Zone */}
            <div
              style={{
                border: "3px dashed #ccc",
                borderRadius: "12px",
                padding: "24px",
                textAlign: "center",
                cursor: "pointer",
                background: tagFile ? "#f0fdf4" : "#fafafa",
                marginBottom: "16px",
                transition: "background 0.2s",
              }}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
              onDrop={(e) => {
                e.preventDefault();
                e.stopPropagation();
                const file = e.dataTransfer.files[0];
                if (file && file.type.startsWith("image/")) setTagFile(file);
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                style={{ display: "none" }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) setTagFile(file);
                }}
              />
              {tagFile ? (
                <div>
                  <span style={{ fontFamily: "var(--font-pixel)", color: "#16a34a" }}>✓ {tagFile.name}</span>
                </div>
              ) : (
                <span style={{ fontFamily: "var(--font-pixel)", color: "#999" }}>DROP_IMAGE_HERE or CLICK_TO_BROWSE</span>
              )}
            </div>

            {/* Name Input */}
            <input
              type="text"
              placeholder="Person's name (e.g. Tilak)"
              value={tagName}
              onChange={(e) => setTagName(e.target.value)}
              style={{
                width: "100%",
                padding: "12px 16px",
                borderRadius: "10px",
                border: "var(--border-thick)",
                fontFamily: "var(--font-pixel)",
                fontSize: "1rem",
                marginBottom: "16px",
                boxSizing: "border-box",
              }}
              onKeyDown={(e) => { if (e.key === "Enter") handleTagByPhoto(); }}
            />

            {/* Error */}
            {tagError && (
              <div style={{ color: "#dc2626", fontFamily: "var(--font-pixel)", fontSize: "0.85rem", marginBottom: "12px" }}>
                ⚠ {tagError}
              </div>
            )}

            {/* Result */}
            {tagResult && (
              <div style={{
                background: "#f0fdf4",
                border: "2px solid #16a34a",
                borderRadius: "10px",
                padding: "12px 16px",
                marginBottom: "16px",
                fontFamily: "var(--font-pixel)",
                fontSize: "0.85rem",
                color: "#15803d",
              }}>
                ✓ {tagResult.message}
              </div>
            )}

            {/* Actions */}
            <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end" }}>
              <button
                className="button button--secondary"
                onClick={closeTagModal}
                style={{ background: "transparent", border: "var(--border-thick)", borderRadius: "10px" }}
              >
                <span style={{ fontFamily: "var(--font-pixel)" }}>CANCEL</span>
              </button>
              <button
                className="button button--primary"
                onClick={handleTagByPhoto}
                disabled={!tagFile || !tagName.trim() || tagLoading}
                style={{
                  background: "var(--electric-purple)",
                  color: "#fff",
                  border: "var(--border-thick)",
                  borderRadius: "10px",
                  opacity: (!tagFile || !tagName.trim() || tagLoading) ? 0.5 : 1,
                }}
              >
                <span style={{ fontFamily: "var(--font-pixel)" }}>
                  {tagLoading ? "TAGGING..." : "TAG_PERSON"}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
