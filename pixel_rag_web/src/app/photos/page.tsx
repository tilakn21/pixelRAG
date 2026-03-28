// pixel_rag_web/src/app/page.tsx
"use client";

import { useCallback, useEffect, useState, Suspense } from "react";
import { fetchHealth, fetchSyncStatus, startSync, setLibraryPath } from "@/lib/api";
import { useSearchParams } from "next/navigation";
import type { HealthResponse, SyncStatus } from "@/lib/types";
import CategoryPills from "@/components/CategoryPills";
import PhotoGrid from "@/components/PhotoGrid";

function GalleryContent() {
  const searchParams = useSearchParams();
  const initialCategory = searchParams.get("category");
  
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<string | null>(initialCategory);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [libraryInput, setLibraryInput] = useState("");
  const [setupSaving, setSetupSaving] = useState(false);
  const [isEditingFolder, setIsEditingFolder] = useState(false);

  // Fetch health on mount
  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setError("Backend is not running. Start the FastAPI server and refresh."));
  }, []);

  // Poll sync status while syncing
  useEffect(() => {
    if (!syncing) return;
    const interval = setInterval(async () => {
      try {
        const status = await fetchSyncStatus();
        setSyncStatus(status);
        if (status.status === "complete" || status.status === "error") {
          setSyncing(false);
          if (status.status === "complete") {
            // Refresh health to get updated counts
            fetchHealth().then(setHealth);
          }
        }
      } catch {
        // ignore polling errors
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [syncing]);

  const handleSync = useCallback(async () => {
    try {
      await startSync();
      setSyncing(true);
      setSyncStatus({ status: "running", progress: 0, current_file: null, photos_processed: 0, photos_total: 0, error_message: null });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Sync failed";
      setError(msg);
    }
  }, []);

  const handleSetup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!libraryInput.trim()) return;
    setSetupSaving(true);
    setError(null);
    try {
      await setLibraryPath(libraryInput.trim());
      const newHealth = await fetchHealth();
      setHealth(newHealth);
      setIsEditingFolder(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to set library path");
    } finally {
      setSetupSaving(false);
    }
  };

  const libraryName = health?.library_path ? health.library_path.split("/").pop() : "Library";

  // Error state: backend unreachable
  if (error) {
    return (
      <div style={{ paddingTop: "var(--space-8)" }}>
        <div className="error-banner">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {error}
          <button className="btn btn--secondary" style={{ marginLeft: "auto" }} onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Setup required state
  if (health && health.status === "setup_required") {
    return (
      <div className="empty-state">
        <svg className="empty-state__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          <line x1="12" y1="11" x2="12" y2="17" />
          <line x1="9" y1="14" x2="15" y2="14" />
        </svg>
        <div className="empty-state__title">Setup Required</div>
        <div className="empty-state__desc">
          Please enter the absolute path to the directory containing your photos.
        </div>
        <form onSubmit={handleSetup} style={{ width: "100%", maxWidth: 400, marginTop: "var(--space-4)" }}>
          <input
            className="input"
            value={libraryInput}
            onChange={(e) => setLibraryInput(e.target.value)}
            placeholder="/Users/tilakneema/Photos..."
            style={{ marginBottom: "var(--space-3)" }}
            disabled={setupSaving}
          />
          <button type="submit" className="btn btn--primary" style={{ width: "100%", justifyContent: "center" }} disabled={setupSaving}>
            {setupSaving ? "Saving..." : "Set Library Path"}
          </button>
        </form>
        {error && (
          <div className="error-banner" style={{ marginTop: "var(--space-4)", width: "100%", maxWidth: 400 }}>
            {error}
          </div>
        )}
      </div>
    );
  }

  // Empty state: no photos
  if (health && health.photo_count === 0) {
    return (
      <div className="empty-state">
        <svg className="empty-state__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21 15 16 10 5 21" />
        </svg>
        <div className="empty-state__title">No photos yet</div>
        <div className="empty-state__desc">
          Your photo directory has been targeted. Sync to start exploring.
        </div>
        <button className="btn btn--primary" onClick={handleSync} disabled={syncing}>
          {syncing ? (
            <><div className="spinner" /> Syncing...</>
          ) : (
            "Start Sync"
          )}
        </button>
      </div>
    );
  }

  return (
    <div style={{ paddingTop: "var(--space-6)" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-2)" }}>
        <div>
          <h1 className="page-title" style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
            {libraryName}
            <button 
              onClick={() => {
                setLibraryInput(health?.library_path ?? "");
                setIsEditingFolder(!isEditingFolder);
              }}
              style={{ color: "var(--text-tertiary)", padding: "4px", display: "flex" }}
              title="Change Folder"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
              </svg>
            </button>
          </h1>
          <p className="page-subtitle">
            {health?.photo_count ?? "—"} photos · {health?.person_count ?? 0} people
          </p>
        </div>
        <button className="btn btn--primary" onClick={handleSync} disabled={syncing}>
          {syncing ? (
            <><div className="spinner" /> Syncing</>
          ) : (
            <>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
              Sync
            </>
          )}
        </button>
      </div>

      {/* Sync progress */}
      {syncing && syncStatus && (
        <div className="glass-subtle" style={{ padding: "var(--space-3) var(--space-4)", marginBottom: "var(--space-4)", fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
          {syncStatus.current_file ?? `Syncing... ${syncStatus.progress}%`}
        </div>
      )}

      {/* Edit Folder Form */}
      {isEditingFolder && (
        <form onSubmit={handleSetup} style={{ marginBottom: "var(--space-4)", padding: "var(--space-4)", background: "var(--bg-glass-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border-subtle)" }}>
          <label style={{ display: "block", marginBottom: "var(--space-2)", fontSize: "var(--text-sm)", color: "var(--text-secondary)", fontWeight: "var(--weight-medium)" }}>
            Absolute Path to Photo Directory
          </label>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <input
              className="input"
              value={libraryInput}
              onChange={(e) => setLibraryInput(e.target.value)}
              placeholder="/Users/yourname/Photos..."
              disabled={setupSaving}
              style={{ flex: 1 }}
            />
            <button type="submit" className="btn btn--primary" disabled={setupSaving}>
              {setupSaving ? "Saving..." : "Save"}
            </button>
          </div>
          {error && <div className="error-banner" style={{ marginTop: "var(--space-2)" }}>{error}</div>}
        </form>
      )}

      {/* Category pills */}
      <CategoryPills active={category} onSelect={setCategory} />

      {/* Photo grid */}
      <div style={{ marginTop: "var(--space-4)" }}>
        <PhotoGrid key={category ?? "all"} category={category} />
      </div>
    </div>
  );
}

export default function GalleryPage() {
  return (
    <Suspense fallback={<div className="spinner" style={{margin: "40px auto"}}></div>}>
      <GalleryContent />
    </Suspense>
  );
}
