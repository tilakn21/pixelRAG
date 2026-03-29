"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import AsciiField from "@/components/AsciiField";
import CategoryPills from "@/components/CategoryPills";
import PhotoGrid from "@/components/PhotoGrid";
import { startSync, fetchHealth, fetchSyncStatus, setLibraryPath } from "@/lib/api";
import { formatLibraryLabel, formatCompactNumber } from "@/lib/display";
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
      <div className="bento-container" style={{ display: "grid", gap: "20px", gridTemplateColumns: "repeat(12, 1fr)", padding: "20px 0" }}>
        <article className="panel animate-reveal stagger-1" style={{ gridColumn: "span 12", background: "var(--electric-purple)", color: "#fff", minHeight: "300px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div className="title-block">
            <span className="eyebrow" style={{ fontFamily: "var(--font-pixel)", color: "var(--sun-yellow)" }}>[ SETUP_REQUIRED ]</span>
            <h1 className="page-title" style={{ fontFamily: "var(--font-pixel)", fontSize: "var(--text-3xl)", textTransform: "uppercase" }}>CONNECT ARCHIVE</h1>
            <p className="page-subtitle" style={{ fontSize: "var(--text-lg)", maxWidth: "600px" }}>
              PixelRAG needs an absolute path to the folder you want indexed locally.
            </p>
          </div>
        </article>

        <section className="panel animate-reveal stagger-2" style={{ gridColumn: "span 12" }}>
          <form className="form-stack" onSubmit={handleSetup} style={{ display: "flex", gap: "20px", alignItems: "center" }}>
            <input
              className="input--mono"
              style={{ flexGrow: 1, border: "var(--border-thick)", borderRadius: "12px", padding: "12px 20px", fontSize: "1rem" }}
              value={libraryInput}
              onChange={(event) => setLibraryInput(event.target.value)}
              placeholder="/Users/yourname/Photos"
              disabled={setupSaving}
            />
            <button type="submit" className="button button--primary" style={{ height: "52px", borderRadius: "12px" }} disabled={setupSaving || !libraryInput.trim()}>
              {setupSaving ? "SAVING..." : "MOUNT_INDEX"}
            </button>
          </form>
        </section>
      </div>
    );
  }

  if (health && health.photo_count === 0) {
    return (
      <div className="bento-container" style={{ display: "grid", gap: "20px", gridTemplateColumns: "repeat(12, 1fr)", padding: "20px 0" }}>
        <article className="panel animate-reveal stagger-1" style={{ gridColumn: "span 8", background: "var(--electric-blue)", color: "#fff", minHeight: "400px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div className="title-block">
            <span className="eyebrow" style={{ fontFamily: "var(--font-pixel)", color: "var(--sun-yellow)" }}>[ EMPTY_ARCHIVE ]</span>
            <h1 className="page-title" style={{ fontFamily: "var(--font-pixel)", fontSize: "var(--text-3xl)", textTransform: "uppercase" }}>THE INDEX IS EMPTY</h1>
            <p className="page-subtitle" style={{ fontSize: "var(--text-lg)", maxWidth: "500px" }}>
              Run the first sync to decode thumbnails, extract structure, and make the collection searchable.
            </p>
            <div className="hero-actions" style={{ marginTop: "32px" }}>
              <button type="button" className="button button--secondary" style={{ borderRadius: "12px", border: "var(--border-thick)" }} onClick={() => void handleSync()} disabled={syncing}>
                {syncing ? "SYNCING..." : "START_FIRST_SYNC"}
              </button>
            </div>
          </div>
        </article>
        
        <article className="panel animate-reveal stagger-2" style={{ gridColumn: "span 4", background: "var(--obsidian)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>
           <AsciiField variant="wave" tone="silver" caption="Archive warm-up" scale="hero" />
        </article>

        {syncing && syncStatus ? (
          <section className="panel" style={{ gridColumn: "span 12", background: "#f0f0f0" }}>
            <div className="status-console__header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
              <div>
                <span className="status-console__label" style={{ fontFamily: "var(--font-pixel)", opacity: 0.6 }}>SYNC_ACTIVITY</span>
                <h2 className="panel__heading" style={{ fontSize: "1.2rem", margin: "4px 0" }}>{syncStatus.current_file ?? "Processing..."}</h2>
              </div>
              <span style={{ fontFamily: "var(--font-pixel)", fontSize: "2rem" }}>{syncStatus.progress}%</span>
            </div>
            <div className="status-console__track" style={{ height: "12px", background: "#ddd", border: "var(--border-thin)", borderRadius: "6px", overflow: "hidden" }}>
              <div className="status-console__bar" style={{ width: `${syncStatus.progress}%`, height: "100%", background: "var(--electric-blue)" }} />
            </div>
          </section>
        ) : null}
      </div>
    );
  }

  return (
    <div className="bento-container" style={{ display: "grid", gap: "20px", gridTemplateColumns: "repeat(12, 1fr)", padding: "20px 0" }}>
      {/* Archive Hero */}
      <article className="panel" style={{ gridColumn: "span 9", background: "var(--electric-purple)", color: "#fff", minHeight: "360px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div className="title-block">
          <span className="eyebrow" style={{ fontFamily: "var(--font-pixel)", color: "var(--sun-yellow)" }}>[ ENDLESS_ARCHIVE ]</span>
          <h1 className="page-title" style={{ fontFamily: "var(--font-pixel)", fontSize: "var(--text-3xl)", textTransform: "uppercase", margin: "8px 0" }}>
            {formatLibraryLabel(health?.library_path).toUpperCase()}
          </h1>
          <p className="page-subtitle" style={{ fontSize: "var(--text-lg)", maxWidth: "540px", opacity: 0.9 }}>
            Browse the full index with quiet filters, inline sync visibility, and metadata only when it helps.
          </p>
        </div>

        <div className="hero-actions" style={{ marginTop: "32px", display: "flex", gap: "12px" }}>
          <button type="button" className="button button--secondary" style={{ borderRadius: "12px", border: "var(--border-thick)" }} onClick={() => void handleSync()} disabled={syncing}>
            {syncing ? "SYNCING..." : "SYNC_ARCHIVE"}
          </button>
          <button
            type="button"
            className="button button--secondary"
            style={{ borderRadius: "12px", border: "var(--border-thick)", background: "transparent", color: "#fff" }}
            onClick={() => {
              setLibraryInput(health?.library_path ?? "");
              setIsEditingFolder((value) => !value);
            }}
          >
            {isEditingFolder ? "HIDE_EDITOR" : "EDIT_PATH"}
          </button>
        </div>
      </article>

      {/* Quick Stats Grid */}
      <div style={{ gridColumn: "span 3", display: "grid", gap: "20px" }}>
        <article className="panel animate-reveal stagger-2" style={{ background: "var(--sun-yellow)", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center" }}>
          <span style={{ fontSize: "0.8rem", fontFamily: "var(--font-pixel)" }}>PHOTOS</span>
          <div style={{ fontSize: "2.5rem", fontFamily: "var(--font-pixel)" }}>{formatCompactNumber(health?.photo_count)}</div>
        </article>
        <article className="panel animate-reveal stagger-3" style={{ background: "var(--obsidian)", color: "#fff", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center" }}>
          <span style={{ fontSize: "0.8rem", fontFamily: "var(--font-pixel)" }}>PEOPLE</span>
          <div style={{ fontSize: "2.5rem", fontFamily: "var(--font-pixel)" }}>{formatCompactNumber(health?.person_count)}</div>
        </article>
      </div>

      {/* Marquee Ticker */}
      <article className="panel" style={{ gridColumn: "span 12", background: "var(--obsidian)", color: "#fff", padding: "0", display: "flex", alignItems: "center", overflow: "hidden", height: "60px" }}>
        <div className="marquee" style={{ whiteSpace: "nowrap", fontSize: "1.5rem", fontFamily: "var(--font-pixel)" }}>
          <div className="marquee-content" style={{ display: "inline-block", paddingLeft: "100%", animation: "marquee 20s linear infinite" }}>
            ARCHIVE STATUS: STABLE • ALL NODES OPERATIONAL • INDEXING COMPLETE • PIXELRAG VERSION 1.0 • SYSTEM SECURE • 
          </div>
        </div>
      </article>

      {error ? (
        <div className="status-banner status-banner--error">
          <strong>Archive issue</strong>
          <span>{error}</span>
        </div>
      ) : null}

      {syncStatus && syncing ? (
        <section className="panel" style={{ gridColumn: "span 12", background: "#f8f8f8" }}>
          <div className="status-console__header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
            <div>
              <span className="status-console__label" style={{ fontFamily: "var(--font-pixel)", opacity: 0.6 }}>PIPELINE_ACTIVITY</span>
              <h2 className="panel__heading" style={{ fontSize: "1.2rem", margin: "4px 0" }}>{syncStatus.current_file ?? "Scanning library..."}</h2>
            </div>
            <span style={{ fontFamily: "var(--font-pixel)", fontSize: "2rem" }}>{syncStatus.progress}%</span>
          </div>

          <div style={{ display: "flex", gap: "20px", fontFamily: "var(--font-mono)", fontSize: "0.8rem", marginBottom: "12px", textTransform: "uppercase" }}>
            <span>{syncStatus.photos_processed} PROCESSED</span>
            <span>{syncStatus.photos_total} TOTAL_FRAMES</span>
            <span style={{ color: "var(--electric-blue)" }}>[ {syncStatus.status} ]</span>
          </div>

          <div className="status-console__track" style={{ height: "12px", background: "#ddd", border: "var(--border-thin)", borderRadius: "6px", overflow: "hidden" }}>
            <div className="status-console__bar" style={{ width: `${syncStatus.progress}%`, height: "100%", background: "var(--electric-blue)" }} />
          </div>
        </section>
      ) : null}

      {isEditingFolder ? (
        <section className="panel" style={{ gridColumn: "span 12", background: "var(--sun-yellow)" }}>
          <span className="panel__title" style={{ fontFamily: "var(--font-pixel)", color: "#000" }}>ARCHIVE_MOUNT_EDITOR</span>
          <form className="form-inline" onSubmit={handleSetup} style={{ display: "flex", gap: "10px", marginTop: "16px" }}>
            <input
              className="input--mono"
              style={{ flex: 1, border: "var(--border-thick)", borderRadius: "12px", padding: "0 16px", background: "#fff" }}
              value={libraryInput}
              onChange={(event) => setLibraryInput(event.target.value)}
              placeholder="/Users/yourname/Photos"
              disabled={setupSaving}
            />
            <button type="submit" className="button button--primary" style={{ borderRadius: "12px" }} disabled={setupSaving || !libraryInput.trim()}>
              {setupSaving ? "SAVING..." : "COMMIT_PATH"}
            </button>
          </form>
        </section>
      ) : null}

      <section className="panel" style={{ gridColumn: "span 12", padding: "16px" }}>
        <CategoryPills active={category} onSelect={setCategory} />
      </section>

      <div style={{ gridColumn: "span 12" }}>
        <PhotoGrid key={category ?? "all"} category={category} />
      </div>
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
