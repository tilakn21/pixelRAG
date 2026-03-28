// pixel_rag_web/src/components/SearchBar.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { fetchSearchSuggestions } from "@/lib/api";
import type { SearchSuggestions } from "@/lib/types";

interface SearchBarProps {
  onSearch: (query: string) => void;
  onImageSearch?: (file: File) => void;
  loading?: boolean;
}

export default function SearchBar({ onSearch, onImageSearch, loading }: SearchBarProps) {
  const [value, setValue] = useState("");
  const [suggestions, setSuggestions] = useState<SearchSuggestions | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch suggestions once on mount
  useEffect(() => {
    fetchSearchSuggestions().then(setSuggestions).catch(() => {});
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim()) {
      setShowDropdown(false);
      onSearch(value.trim());
    }
  };

  const handleFocus = () => {
    if (!value.trim()) setShowDropdown(true);
  };

  const handleSuggestionClick = (text: string) => {
    setValue(text);
    setShowDropdown(false);
    onSearch(text);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onImageSearch) {
      onImageSearch(file);
    }
  };

  // Filter suggestions client-side
  const filteredPeople =
    suggestions?.person_names?.filter(
      (n) => !value || n.toLowerCase().includes(value.toLowerCase())
    ) ?? [];
  const filteredCities =
    suggestions?.cities?.filter(
      (c) => !value || c.toLowerCase().includes(value.toLowerCase())
    ) ?? [];

  return (
    <form onSubmit={handleSubmit} style={{ position: "relative" }}>
      <div className="search-bar-wrapper glass">
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth={2}>
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={inputRef}
            className="search-bar"
            placeholder="Photos of Tilak in Mumbai during 2023..."
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              if (e.target.value) setShowDropdown(false);
            }}
            onFocus={handleFocus}
            onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
          />

          <input
            type="file"
            ref={fileInputRef}
            style={{ display: "none" }}
            accept="image/*"
            onChange={handleFileChange}
          />
          
          <button
            type="button"
            className="btn--icon"
            onClick={() => fileInputRef.current?.click()}
            title="Search by Image"
            style={{ padding: "8px", color: "var(--text-tertiary)" }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
          </button>

          {loading && <div className="spinner" style={{ marginLeft: "var(--space-2)" }} />}
        </div>
      </div>

      {/* Suggestions dropdown */}
      {showDropdown && (filteredPeople.length > 0 || filteredCities.length > 0) && (
        <div
          className="glass"
          style={{
            position: "absolute",
            top: "calc(100% + var(--space-2))",
            left: 0,
            right: 0,
            padding: "var(--space-3)",
            zIndex: 100,
          }}
        >
          {filteredPeople.length > 0 && (
            <>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", padding: "var(--space-1) var(--space-2)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                People
              </div>
              {filteredPeople.slice(0, 5).map((name) => (
                <button
                  key={name}
                  type="button"
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "var(--space-2) var(--space-3)",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "var(--text-sm)",
                  }}
                  onClick={() => handleSuggestionClick(`Photos of ${name}`)}
                >
                  👤 {name}
                </button>
              ))}
            </>
          )}
          {filteredCities.length > 0 && (
            <>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", padding: "var(--space-2) var(--space-2) var(--space-1)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Places
              </div>
              {filteredCities.slice(0, 5).map((city) => (
                <button
                  key={city}
                  type="button"
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "var(--space-2) var(--space-3)",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "var(--text-sm)",
                  }}
                  onClick={() => handleSuggestionClick(`Photos from ${city}`)}
                >
                  📍 {city}
                </button>
              ))}
            </>
          )}
        </div>
      )}
    </form>
  );
}
