"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import AsciiField from "@/components/AsciiField";
import CategoryPills from "@/components/CategoryPills";
import PhotoGrid from "@/components/PhotoGrid";
import { fetchHealth, fetchSyncStatus, setLibraryPath, startSync } from "@/lib/api";
import { formatLibraryLabel } from "@/lib/display";
import type { HealthResponse, SyncStatus } from "@/lib/types";

function ArchiveContent() {
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

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => {
        setError("PixelRAG could not reach the backend. Start the FastAPI service, then refresh.");
      });
  }, []);

  useEffect(() => {
    if (!syncing) return;

    const interval = window.setInterval(async () => {
      try {
        const status = await fetchSyncStatus();
        setSyncStatus(status);

        if (status.status === "complete" || status.status === "error") {
          setSyncing(false);
          if (status.status === "complete") {
            const refreshed = await fetchHealth();
            setHealth(refreshed);
          }
        }
      } catch {
        setSyncing(false);
      }
    }, 2000);

    return () => window.clearInterval(interval);
  }, [syncing]);

  const handleSync = useCallback(async () => {
    setError(null);
    try {
      await startSync();
      setSyncing(true);
      setSyncStatus({
        status: "running",
        progress: 0,
        current_file: "Initializing pipeline",
        photos_processed: 0,
        photos_total: 0,
        error_message: null,
        logs: ["Preparing archive scan...", "Activating indexing pipeline..."],
      });
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Sync could not start.");
    }
  }, []);

  const handleSetup = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!libraryInput.trim()) return;

    setSetupSaving(true);
    setError(null);
    try {
      await setLibraryPath(libraryInput.trim());
      const newHealth = await fetchHealth();
      setHealth(newHealth);
      setIsEditingFolder(false);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Failed to set library.");
    } finally {
      setSetupSaving(false);
    }
  };

  if (error && !health) {
    return (
      <div className="route">
        <div className="status-banner status-banner--error">
          <strong>Connection issue</strong>
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (health && health.status === "setup_required") {
    return (
      <div className="route">
        <section className="route-hero route-hero--split">
          <div className="title-block">
            <span className="eyebrow">Endless Archive</span>
            <h1 className="page-title">Connect a photo library to begin.</h1>
            <p className="page-subtitle">
              PixelRAG needs an absolute path to the folder you want indexed locally.
            </p>
          </div>
          <AsciiField className="hero-ascii" variant="horizon" tone="silver" caption="Awaiting source imagery" scale="hero" />
        </section>

        <section className="panel panel--accent">
          <form className="form-stack" onSubmit={handleSetup}>
            <input
              className="input input--mono"
              value={libraryInput}
              onChange={(event) => setLibraryInput(event.target.value)}
              placeholder="/Users/yourname/Photos"
              disabled={setupSaving}
            />
            <button type="submit" className="button button--primary" disabled={setupSaving || !libraryInput.trim()}>
              {setupSaving ? "Saving" : "Set library path"}
            </button>
          </form>
        </section>
      </div>
    );
  }

  if (health && health.photo_count === 0) {
    return (
      <div className="route">
        <section className="route-hero route-hero--split">
          <div className="title-block">
            <span className="eyebrow">Endless Archive</span>
            <h1 className="page-title">The archive is connected but still empty.</h1>
            <p className="page-subtitle">
              Run the first sync to decode thumbnails, extract structure, and make the collection searchable.
            </p>
            <div className="hero-actions">
              <button type="button" className="button button--primary" onClick={() => void handleSync()} disabled={syncing}>
                {syncing ? "Syncing" : "Start first sync"}
              </button>
            </div>
          </div>
          <AsciiField className="hero-ascii" variant="wave" tone="cobalt" caption="Archive warm-up / decode pass" scale="hero" />
        </section>

        {syncing && syncStatus ? (
          <section className="status-console">
            <div className="status-console__header">
              <div>
                <span className="status-console__label">Sync activity</span>
                <h2 className="panel__heading">{syncStatus.current_file ?? "Processing"}</h2>
              </div>
              <span className="meta-pill">{syncStatus.progress}%</span>
            </div>
            <div className="status-console__track">
              <div className="status-console__bar" style={{ width: `${syncStatus.progress}%` }} />
            </div>
            <div className="status-console__log">
              {(syncStatus.logs ?? []).slice(-10).reverse().map((log) => (
                <span key={log}>{log}</span>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    );
  }

  return (
    <div className="route">
      <section className="route-hero route-hero--split">
        <div className="stack">
          <div className="title-block">
            <span className="eyebrow">Endless Archive</span>
            <h1 className="page-title">{formatLibraryLabel(health?.library_path)}</h1>
            <p className="page-subtitle">
              Browse the full index with quiet filters, inline sync visibility, and metadata only when it helps.
            </p>
          </div>

          <div className="route-meta">
            <span className="meta-pill">{health?.photo_count ?? 0} photos</span>
            <span className="meta-pill">{health?.person_count ?? 0} people</span>
            {category ? <span className="meta-pill">Category · {category}</span> : null}
          </div>

          <div className="hero-actions">
            <button type="button" className="button button--primary" onClick={() => void handleSync()} disabled={syncing}>
              {syncing ? "Syncing archive" : "Sync archive"}
            </button>
            <button
              type="button"
              className="button button--secondary"
              onClick={() => {
                setLibraryInput(health?.library_path ?? "");
                setIsEditingFolder((value) => !value);
              }}
            >
              {isEditingFolder ? "Hide library editor" : "Edit library path"}
            </button>
          </div>
        </div>

        <AsciiField className="hero-ascii" variant="wave" tone="silver" caption="Live archive / infinite sequence" scale="hero" />
      </section>

      {error ? (
        <div className="status-banner status-banner--error">
          <strong>Archive issue</strong>
          <span>{error}</span>
        </div>
      ) : null}

      {syncStatus && syncing ? (
        <section className="status-console">
          <div className="status-console__header">
            <div>
              <span className="status-console__label">Pipeline Activity</span>
              <h2 className="panel__heading">{syncStatus.current_file ?? "Scanning library"}</h2>
            </div>
            <span className="meta-pill">{syncStatus.progress}%</span>
          </div>

          <div className="status-console__meta">
            <span>{syncStatus.photos_processed} processed</span>
            <span>{syncStatus.photos_total} total frames</span>
            <span>{syncStatus.status}</span>
          </div>

          <div className="status-console__track">
            <div className="status-console__bar" style={{ width: `${syncStatus.progress}%` }} />
          </div>

          <div className="status-console__log">
            {(syncStatus.logs ?? []).slice(-12).reverse().map((log) => (
              <span key={log}>{log}</span>
            ))}
          </div>
        </section>
      ) : null}

      {isEditingFolder ? (
        <section className="panel panel--quiet">
          <span className="panel__title">Library Editor</span>
          <form className="form-inline" onSubmit={handleSetup}>
            <input
              className="input input--mono"
              value={libraryInput}
              onChange={(event) => setLibraryInput(event.target.value)}
              placeholder="/Users/yourname/Photos"
              disabled={setupSaving}
              style={{ flex: 1, minWidth: 280 }}
            />
            <button type="submit" className="button button--primary" disabled={setupSaving || !libraryInput.trim()}>
              {setupSaving ? "Saving" : "Save path"}
            </button>
          </form>
        </section>
      ) : null}

      <section className="archive-toolbar">
        <CategoryPills active={category} onSelect={setCategory} />
      </section>

      <PhotoGrid key={category ?? "all"} category={category} />
    </div>
  );
}

export default function GalleryPage() {
  return (
    <Suspense fallback={<div className="spinner" style={{ margin: "40px auto" }} />}>
      <ArchiveContent />
    </Suspense>
  );
}
