// pixel_rag_web/src/app/page.tsx
"use client";

import { useEffect, useState } from "react";
import { fetchHealth, setLibraryPath } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";
import { useRouter } from "next/navigation";
import SearchBar from "@/components/SearchBar";

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSwitched, setIsSwitched] = useState(false);
  const [libraryInput, setLibraryInput] = useState("");
  const [setupSaving, setSetupSaving] = useState(false);
  const router = useRouter();

  useEffect(() => {
    // Check if we just swapped library
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (url.searchParams.get("switched") === "true") {
        setIsSwitched(true);
        // Clear param without reload
        window.history.replaceState({}, "", "/");
      }
    }

    fetchHealth()
      .then(setHealth)
      .catch(() => setError("Unable to connect to PixelRAG Backend. Ensure the FastAPI server is running."));
  }, []);

  const handleSetup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!libraryInput.trim()) return;
    setSetupSaving(true);
    setError(null);
    try {
      await setLibraryPath(libraryInput.trim());
      // A hard reload is the safest way to clear all browser caches (lists, thumbs) 
      // when the entire backend database context has swapped.
      window.location.href = "/?switched=true";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to set library path");
    } finally {
      setSetupSaving(false);
    }
  };

  const libraryName = health?.library_path ? health.library_path : "No folder connected";

  return (
    <div style={{ paddingTop: "var(--space-10)", paddingBottom: "var(--space-10)", maxWidth: 800, margin: "0 auto", textAlign: "center" }}>
      
      {/* Success Notification */}
      {isSwitched && (
        <div style={{ 
          margin: "0 auto var(--space-6)", maxWidth: 500, padding: "var(--space-4)", 
          background: "var(--accent-glow)", border: "1px solid var(--accent-primary)",
          borderRadius: "var(--radius-md)", color: "var(--accent-primary)", fontWeight: "bold",
          display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "center", gap: "var(--space-2)"
        }}>
          ✅ Library Updated! 
          {health?.photo_count === 0 && (
            <button 
              onClick={() => router.push("/sync")} 
              style={{ textDecoration: "underline", background: "none", border: "none", color: "inherit", cursor: "pointer", fontWeight: "inherit" }}
            >
               Run your first sync to index photos →
            </button>
          )}
        </div>
      )}

      {/* Hero Section */}
      <h1 className="page-title" style={{ fontSize: "3rem", marginBottom: "var(--space-2)" }}>Your Life in Focus.</h1>
      <p className="page-subtitle" style={{ fontSize: "1.25rem", maxWidth: 500, margin: "0 auto var(--space-8)" }}>
        Private AI Photo Intelligence. Search, index, and explore your photo libraries, 100% offline.
      </p>

      {/* Central Interactive Block */}
      <div style={{ padding: "0 var(--space-4)", marginBottom: "var(--space-10)" }}>
        {/* Simple Search Shortcut */}
        <div style={{ marginBottom: "var(--space-6)" }}>
           <button 
             onClick={() => router.push("/search")}
             style={{
               width: "100%", maxWidth: "600px", background: "white", padding: "16px 24px", 
               borderRadius: "var(--radius-full)", border: "1px solid var(--border-medium)",
               display: "flex", alignItems: "center", gap: "var(--space-3)", 
               color: "var(--text-tertiary)", fontSize: "var(--text-lg)",
               boxShadow: "0 8px 24px rgba(62, 39, 35, 0.08)", cursor: "text"
             }}
           >
             <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
             </svg>
             Search your memories... 
           </button>
        </div>

        <button 
          className="btn btn--primary" 
          onClick={() => router.push("/gallery")}
          style={{ padding: "16px 40px", fontSize: "var(--text-lg)", borderRadius: "var(--radius-full)" }}
        >
          Open Gallery Hub
        </button>
      </div>

      <div style={{ borderTop: "1px solid var(--border-medium)", margin: "var(--space-8) 0", opacity: 0.5 }} />

      {/* Folders & System Status */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "var(--space-4)", textAlign: "left" }}>
        
        {/* Connected Library */}
        <div className="glass" style={{ padding: "var(--space-6)", borderRadius: "var(--radius-md)" }}>
          <h2 style={{ fontSize: "var(--text-lg)", marginBottom: "var(--space-2)" }}>Connected Library</h2>
          
          <div style={{ 
            fontFamily: "monospace", padding: "var(--space-3)", 
            background: "var(--bg-secondary)", borderRadius: "var(--radius-sm)",
            fontSize: "var(--text-sm)", color: "var(--text-secondary)", marginBottom: "var(--space-4)",
            wordBreak: "break-all"
          }}>
            📁 {libraryName}
          </div>

          <form onSubmit={handleSetup} style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
            <input
              className="input"
              value={libraryInput}
              onChange={(e) => setLibraryInput(e.target.value)}
              placeholder="/Users/yourname/Photos..."
              style={{ flex: 1, minWidth: 200 }}
              disabled={setupSaving}
            />
            <button type="submit" className="btn btn--secondary" disabled={setupSaving || !libraryInput.trim()}>
              {setupSaving ? "Switching..." : "Add / Switch Folder"}
            </button>
          </form>
          {error && <div className="error-banner" style={{ marginTop: "var(--space-2)" }}>{error}</div>}
        </div>

        {/* Quick Stats Summary */}
        <div className="glass" style={{ padding: "var(--space-6)", borderRadius: "var(--radius-md)" }}>
          <h2 style={{ fontSize: "var(--text-lg)", marginBottom: "var(--space-4)" }}>Library Analytics</h2>
          {health ? (
             <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap" }}>
                <div style={{ flex: 1, background: "var(--bg-primary)", padding: "var(--space-4)", borderRadius: "var(--radius-sm)", textAlign: "center", border: "1px solid var(--border-subtle)" }}>
                   <div style={{ fontSize: "var(--text-2xl)", fontWeight: "bold", color: "var(--accent-red)" }}>{health.photo_count}</div>
                   <div style={{ fontSize: "var(--text-xs)", textTransform: "uppercase", color: "var(--text-secondary)", fontWeight: "bold", letterSpacing: "1px" }}>Photos</div>
                </div>
                <div style={{ flex: 1, background: "var(--bg-primary)", padding: "var(--space-4)", borderRadius: "var(--radius-sm)", textAlign: "center", border: "1px solid var(--border-subtle)" }}>
                   <div style={{ fontSize: "var(--text-2xl)", fontWeight: "bold", color: "var(--accent-yellow)" }}>{health.person_count}</div>
                   <div style={{ fontSize: "var(--text-xs)", textTransform: "uppercase", color: "var(--text-secondary)", fontWeight: "bold", letterSpacing: "1px" }}>Identities</div>
                </div>
             </div>
          ) : (
            <div style={{ color: "var(--text-tertiary)" }}>Loading metrics...</div>
          )}
          <br/>
          <button className="btn btn--secondary" style={{ width: "100%" }} onClick={() => router.push("/photos")}>
             View All Photos
          </button>
        </div>

      </div>

    </div>
  );
}
