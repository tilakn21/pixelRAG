"use client";

import { useEffect, useState } from "react";
import { fetchHealth, setLibraryPath } from "@/lib/api";
import { HealthResponse } from "@/lib/types";
import { formatLibraryLabel } from "@/lib/display";

export default function LibrarySelector() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => {});
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

  if (!health) {
    return <div className="library-indicator">Connecting archive</div>;
  }

  if (health.known_libraries?.length <= 1) {
    return <div className="library-indicator">{formatLibraryLabel(health.library_path)}</div>;
  }

  return (
    <label className="library-selector">
      <span className="library-selector__label">Library</span>
      <select
        value={health.library_path}
        onChange={(e) => handleSwitch(e.target.value)}
        title={health.library_path}
      >
        {health.known_libraries?.map(lib => (
          <option key={lib} value={lib}>
            {lib.split("/").pop() || lib}
          </option>
        ))}
      </select>
      <span className="library-selector__arrow" aria-hidden="true">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </span>
    </label>
  );
}
