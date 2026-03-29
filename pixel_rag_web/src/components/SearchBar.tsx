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
          placeholder={PROMPTS[promptIndex]}
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
              className="button button--ghost button--icon"
              onClick={() => fileInputRef.current?.click()}
              title="Search by image"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
                <path d="M21 18.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 18.5v-9A2.5 2.5 0 0 1 5.5 7H9l1.7-2h2.6L15 7h3.5A2.5 2.5 0 0 1 21 9.5z" />
                <circle cx="12" cy="13" r="3.5" />
              </svg>
            </button>
          ) : null}

          <button type="submit" className="button button--primary">
            {loading ? "Analyzing" : "Search"}
          </button>
        </div>
      </div>

      {showDropdown && (filteredPeople.length > 0 || filteredCities.length > 0) && (
        <div className="search-shell__suggestions">
          {filteredPeople.length > 0 && (
            <div className="suggestion-group">
              <div className="suggestion-heading">
                People
              </div>
              {filteredPeople.slice(0, 5).map((name) => (
                <button
                  key={name}
                  type="button"
                  className="suggestion-button"
                  onClick={() => handleSuggestionClick(`Photos of ${name}`)}
                >
                  <span className="chip__mark">ID</span>
                  <span>{name}</span>
                </button>
              ))}
            </div>
          )}
          {filteredCities.length > 0 && (
            <div className="suggestion-group">
              <div className="suggestion-heading">
                Places
              </div>
              {filteredCities.slice(0, 5).map((city) => (
                <button
                  key={city}
                  type="button"
                  className="suggestion-button"
                  onClick={() => handleSuggestionClick(`Photos from ${city}`)}
                >
                  <span className="chip__mark">CT</span>
                  <span>{city}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </form>
  );
}
