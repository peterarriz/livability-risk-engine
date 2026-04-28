"use client";
import { useEffect, useRef, useState, useCallback } from "react";

import { fetchAddressSuggestions } from "@/lib/api";
import type { AddressSuggestion } from "@/lib/address-types";

const COVERED_CITIES = [
  "chicago", "new york", "los angeles", "austin", "seattle", "denver",
  "portland", "nashville", "phoenix", "dallas", "houston", "philadelphia",
  "san francisco", "minneapolis", "columbus", "san antonio", "fort worth",
  "charlotte", "detroit", "milwaukee", "baltimore", "boston",
  "washington", "atlanta", "tampa", "miami", "pittsburgh",
  "cincinnati", "kansas city", "mesa", "tucson", "tulsa",
  "arlington", "wichita", "raleigh", "colorado springs",
  "omaha", "virginia beach", "oakland", "richmond",
  "boise", "des moines", "chattanooga", "knoxville",
  "providence", "buffalo", "norfolk", "chandler", "gilbert",
  "scottsdale", "glendale", "henderson", "greensboro", "durham",
  "winston-salem", "new orleans", "lexington", "lincoln", "madison",
];

function getCoverage(description: string): "covered" | "partial" {
  const lower = description.toLowerCase();
  for (const city of COVERED_CITIES) {
    if (lower.includes(city)) return "covered";
  }
  return "partial";
}

type Props = {
  defaultValue?: string;
  placeholder?: string;
  onSelect: (suggestion: AddressSuggestion) => void;
  onChange?: (value: string) => void;
  ariaLabel?: string;
  inputStyle?: React.CSSProperties;
  dropdownDark?: boolean;
};

export default function AddressAutocomplete({
  defaultValue = "",
  placeholder = "Enter any US address",
  onSelect,
  onChange,
  ariaLabel,
  inputStyle,
  dropdownDark = false,
}: Props) {
  const [value, setValue] = useState(defaultValue);
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setValue(defaultValue);
  }, [defaultValue]);

  const fetchSuggestions = useCallback(async (input: string) => {
    const q = input.trim();
    if (!q || q.length < 3) {
      setSuggestions([]);
      setShowDropdown(false);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const results = await fetchAddressSuggestions(q, { limit: 5 });
      if (controller.signal.aborted) return;
      setSuggestions(results);
      setShowDropdown(results.length > 0);
      setActiveIndex(-1);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setSuggestions([]);
        setShowDropdown(false);
      }
    }
  }, []);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const v = e.target.value;
      setValue(v);
      onChange?.(v);
      setActiveIndex(-1);
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => fetchSuggestions(v), 300);
    },
    [onChange, fetchSuggestions],
  );

  const handleSelect = useCallback(
    (suggestion: AddressSuggestion) => {
      setValue(suggestion.display_address);
      onSelect(suggestion);
      setSuggestions([]);
      setShowDropdown(false);
    },
    [onSelect],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!showDropdown || suggestions.length === 0) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % suggestions.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => (i - 1 + suggestions.length) % suggestions.length);
      } else if (e.key === "Enter" && activeIndex >= 0) {
        e.preventDefault();
        handleSelect(suggestions[activeIndex]);
      } else if (e.key === "Escape") {
        setShowDropdown(false);
      }
    },
    [showDropdown, suggestions, activeIndex, handleSelect],
  );

  // Close dropdown on outside click.
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const dark = dropdownDark;

  return (
    <div ref={containerRef} style={{ position: "relative", flex: 1 }}>
      <input
        type="text"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        style={inputStyle}
        autoComplete="off"
        role="combobox"
        aria-expanded={showDropdown && suggestions.length > 0}
        aria-autocomplete="list"
      />
      {showDropdown && suggestions.length > 0 && (
        <ul
          role="listbox"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            margin: "4px 0 0",
            padding: 0,
            listStyle: "none",
            background: dark ? "#1a2236" : "#FFFFFF",
            border: `1px solid ${dark ? "rgba(255,255,255,0.1)" : "#E5E7EB"}`,
            borderRadius: "8px",
            boxShadow: dark ? "0 8px 24px rgba(0,0,0,0.3)" : "0 4px 12px rgba(0,0,0,0.08)",
            zIndex: 9999,
            maxHeight: "240px",
            overflow: "auto",
          }}
        >
          {suggestions.map((pred, i) => {
            const coverage = getCoverage(pred.display_address);
            return (
              <li
                key={pred.canonical_id ? `canonical-${pred.canonical_id}` : `${pred.display_address}-${i}`}
                role="option"
                aria-selected={i === activeIndex}
                onMouseDown={() => handleSelect(pred)}
                onMouseEnter={() => setActiveIndex(i)}
                style={{
                  padding: "10px 14px",
                  cursor: "pointer",
                  color: dark ? "#e2e8f0" : "#374151",
                  background:
                    i === activeIndex
                      ? dark
                        ? "rgba(96,165,250,0.1)"
                        : "#F9FAFB"
                      : "transparent",
                  borderTop:
                    i > 0
                      ? `1px solid ${dark ? "rgba(255,255,255,0.05)" : "#F3F4F6"}`
                      : "none",
                }}
              >
                <div style={{ fontSize: "14px" }}>{pred.display_address}</div>
                <div style={{ fontSize: "11px", marginTop: "2px", display: "flex", alignItems: "center", gap: "4px" }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: coverage === "covered" ? "#22C55E" : "#F59E0B", display: "inline-block", flexShrink: 0 }} />
                  <span style={{ color: coverage === "covered" ? "#16A34A" : "#D97706" }}>
                    {coverage === "covered" ? "Full coverage" : "Neighborhood data only"}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
