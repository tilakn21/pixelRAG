import { useEffect, useState } from "react";
import { fetchHealth, setLibraryPath } from "@/lib/api";
import { HealthResponse } from "@/lib/types";

export default function LibrarySelector() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    fetchHealth().then(setHealth);
  }, []);

  const handleSwitch = async (path: string) => {
    if (!path || path === health?.library_path) return;
    try {
      await setLibraryPath(path);
      // Hard reload to clear all caches.
      window.location.href = "/?switched=true";
    } catch (e) {
      alert("Failed to switch library. Ensure the path is valid.");
    }
  };

  if (!health || health.known_libraries?.length <= 1) return null;

  return (
    <div className="library-selector">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: "var(--space-2)", opacity: 0.6 }}>
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
      </svg>
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
      <div className="library-selector__arrow">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </div>
    </div>
  );
}
