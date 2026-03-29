"use client";

import { useEffect, useState } from "react";
import { fetchHealth, setLibraryPath } from "@/lib/api";
import { HealthResponse } from "@/lib/types";
import { formatLibraryLabel } from "@/lib/display";

export default function LibrarySelector() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => { });
  }, []);

  const handleSwitch = async (path: string) => {
    if (!path || path === health?.library_path) return;
    try {
      await setLibraryPath(path);
      // Hard reload to clear all caches.
      window.location.href = "/?switched=true";
    } catch {
      alert("Failed to switch library. Ensure the path is valid.");
    }
  };

  const [isOpen, setIsOpen] = useState(false);

  if (!health) {
    return <div className="library-indicator" style={{ fontFamily: "var(--font-pixel)", fontSize: "0.9rem", color: "var(--obsidian)", opacity: 0.6 }}>[ CONNECTING... ]</div>;
  }

  if (health.known_libraries?.length <= 1) {
    return (
      <div className="library-indicator" style={{ border: "var(--border-thick)", borderRadius: "12px", background: "var(--sun-yellow)", color: "#000", fontFamily: "var(--font-mono)", fontSize: "0.75rem", padding: "4px 12px", height: "32px", display: "flex", alignItems: "center" }}>
        {formatLibraryLabel(health.library_path).toUpperCase()}
      </div>
    );
  }

  return (
    <div className="custom-dropdown" onMouseLeave={() => setIsOpen(false)}>
      <span style={{ fontFamily: "var(--font-pixel)", fontSize: "0.6rem", position: "absolute", top: "-14px", left: "8px", background: "var(--gallery-white)", padding: "0 4px", color: "var(--obsidian)", zIndex: 10 }}></span>

      <button
        className="custom-dropdown__trigger"
        onClick={() => setIsOpen(!isOpen)}
        type="button"
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "140px" }}>
          {health.library_path.split("/").pop()?.toUpperCase() || "ROOT"}
        </span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" style={{ transform: isOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {isOpen && (
        <div className="custom-dropdown__menu">
          {health.known_libraries.map((lib) => (
            <button
              key={lib}
              className={`custom-dropdown__item ${lib === health.library_path ? "custom-dropdown__item--active" : ""}`}
              onClick={() => handleSwitch(lib)}
            >
              {lib.split("/").pop()?.toUpperCase() || lib}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
