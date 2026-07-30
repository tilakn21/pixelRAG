import { useEffect, useState, useRef } from "react";
import { fetchHealth, setLibraryPath, deleteLibrary } from "@/lib/api";
import { HealthResponse } from "@/lib/types";
import { formatLibraryLabel } from "@/lib/display";

export default function LibrarySelector() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => { });
  }, []);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
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
    return <div className="library-indicator" style={{ fontFamily: "var(--font-pixel)", fontSize: "0.9rem", color: "var(--obsidian)", opacity: 0.6 }}>[ CONNECTING... ]</div>;
  }

  return (
    <div className="custom-dropdown" ref={containerRef}>
      <span style={{ 
        fontFamily: "var(--font-pixel)", 
        fontSize: "0.65rem", 
        position: "absolute", 
        top: "-12px", 
        left: "12px", 
        background: "var(--gallery-white)", 
        padding: "0 6px", 
        color: "var(--obsidian)", 
        zIndex: 11,
        border: "var(--border-thick)",
        borderRadius: "4px",
        boxShadow: "1px 1px 0 #000"
      }}>
        [ CHANGE_FOLDER ]
      </span>

      <button
        className="custom-dropdown__trigger"
        onClick={() => setIsOpen(!isOpen)}
        type="button"
        style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: "180px", justifyContent: "space-between" }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "160px" }}>
          {health.library_path.split("/").pop()?.toUpperCase() || "ROOT"}
        </span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" style={{ transform: isOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {isOpen && (
        <div className="custom-dropdown__menu" style={{ width: "240px" }}>
          {health.known_libraries.map((lib) => (
            <button
              key={lib}
              className={`custom-dropdown__item ${lib === health.library_path ? "custom-dropdown__item--active" : ""}`}
              onClick={() => {
                handleSwitch(lib);
                setIsOpen(false);
              }}
            >
              {lib.split("/").pop()?.toUpperCase() || lib}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
