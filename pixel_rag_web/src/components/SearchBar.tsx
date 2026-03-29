// pixel_rag_web/src/components/SearchBar.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { fetchSearchSuggestions } from "@/lib/api";
import type { SearchSuggestions } from "@/lib/types";

interface SearchBarProps {
  onSearch: (query: string) => void;
  onImageSearch?: (file: File) => void;
  loading?: boolean;
  initialValue?: string;
}

const PROMPTS = [
  "Photos of Ananya in Mumbai during 2024",
  "Night streets, quiet interiors, and reflections",
  "Who appears near the river last winter?",
  "Architecture with blue tones and glass facades",
];

export default function SearchBar({
  onSearch,
  onImageSearch,
  loading,
  initialValue = "",
}: SearchBarProps) {
  const [value, setValue] = useState("");
  const [suggestions, setSuggestions] = useState<SearchSuggestions | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [promptIndex, setPromptIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchSearchSuggestions().then(setSuggestions).catch(() => {});
  }, []);

  useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setPromptIndex((current) => (current + 1) % PROMPTS.length);
    }, 3200);

    return () => window.clearInterval(interval);
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
      e.target.value = "";
    }
  };

  const filteredPeople =
    suggestions?.person_names?.filter(
      (n) => !value || n.toLowerCase().includes(value.toLowerCase())
    ) ?? [];
  const filteredCities =
    suggestions?.cities?.filter(
      (c) => !value || c.toLowerCase().includes(value.toLowerCase())
    ) ?? [];

  return (
    <form onSubmit={handleSubmit} className="search-shell">
      <div className="search-shell__bar">
        <div className="search-shell__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
            <circle cx="11" cy="11" r="7.25" />
            <path d="m20 20-3.6-3.6" />
          </svg>
        </div>

        <input
          ref={inputRef}
          className="search-shell__input"
          style={{ fontFamily: "var(--font-mono)", fontSize: "1.1rem", border: "none", background: "transparent", color: "var(--obsidian)" }}
          placeholder={PROMPTS[promptIndex].toUpperCase()}
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
          className="visually-hidden"
          accept="image/*"
          onChange={handleFileChange}
        />

        <div className="search-shell__actions">
          {onImageSearch ? (
            <button
              type="button"
              className="button button--secondary"
              style={{ minWidth: "52px", padding: "0", borderRadius: "12px" }}
              onClick={() => fileInputRef.current?.click()}
              title="Search by image"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} style={{ width: "22px" }}>
                <path d="M21 18.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 18.5v-9A2.5 2.5 0 0 1 5.5 7H9l1.7-2h2.6L15 7h3.5A2.5 2.5 0 0 1 21 9.5z" />
                <circle cx="12" cy="13" r="3.5" />
              </svg>
            </button>
          ) : null}

          <button type="submit" className="button button--primary" style={{ borderRadius: "12px", fontFamily: "var(--font-pixel)", fontSize: "1.2rem", padding: "0 24px" }}>
            {loading ? "ANALYZING" : "SEARCH"}
          </button>
        </div>
      </div>

      {showDropdown && (filteredPeople.length > 0 || filteredCities.length > 0) && (
        <div className="search-shell__suggestions" style={{ border: "var(--border-thick)", borderRadius: "16px", background: "var(--gallery-white)", boxShadow: "var(--shadow-panel)", marginTop: "10px", padding: "16px" }}>
          {filteredPeople.length > 0 && (
            <div className="suggestion-group">
              <div className="suggestion-heading" style={{ fontFamily: "var(--font-pixel)", color: "var(--obsidian)", opacity: 0.6 }}>
                PEOPLE_INDEX
              </div>
              {filteredPeople.slice(0, 5).map((name) => (
                <button
                  key={name}
                  type="button"
                  className="suggestion-button"
                  style={{ fontFamily: "var(--font-pixel)", fontSize: "1.1rem", borderRadius: "8px", padding: "8px 12px" }}
                  onClick={() => handleSuggestionClick(`Photos of ${name}`)}
                >
                  <span style={{ color: "var(--electric-blue)", marginRight: "8px" }}>&gt;&gt;</span>
                  <span>{name.toUpperCase()}</span>
                </button>
              ))}
            </div>
          )}
          {filteredCities.length > 0 && (
            <div className="suggestion-group" style={{ marginTop: "12px" }}>
              <div className="suggestion-heading" style={{ fontFamily: "var(--font-pixel)", color: "var(--obsidian)", opacity: 0.6 }}>
                GEOGRAPHIC_NODES
              </div>
              {filteredCities.slice(0, 5).map((city) => (
                <button
                  key={city}
                  type="button"
                  className="suggestion-button"
                  style={{ fontFamily: "var(--font-pixel)", fontSize: "1.1rem", borderRadius: "8px", padding: "8px 12px" }}
                  onClick={() => handleSuggestionClick(`Photos from ${city}`)}
                >
                  <span style={{ color: "var(--sun-yellow)", marginRight: "8px" }}>&gt;&gt;</span>
                  <span>{city.toUpperCase()}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </form>
  );
}
